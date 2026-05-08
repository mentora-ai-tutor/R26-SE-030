from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

import httpx
from bson import ObjectId
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import GITHUB_API_URL, INTERNAL_SERVICE_KEY, USER_SERVICE_INTERNAL_URL
from app.db.database import get_database
from app.services.llm import Task, get_router
from app.services.llm.base import LLMAuthError

logger = logging.getLogger(__name__)

SEED_VERSION = "review-v1"
MAX_REPOS = 5
MAX_SOURCE_FILES = 12
MAX_FILE_BYTES = 6_000
MAX_BUNDLE_BYTES = 128_000
MAX_TREE_PATHS = 160
PER_REPO_TIMEOUT_SECONDS = 75

SOURCE_EXT_PRIORITY = {
    ".java": 0,
    ".py": 1,
    ".ts": 2,
    ".tsx": 3,
    ".js": 4,
    ".jsx": 5,
}

SKIP_PATH_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}

SKIP_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
}


class RepoError(BaseModel):
    severity: Literal["low", "medium", "high"]
    file: str = Field(..., max_length=260)
    line: int | None = Field(default=None, ge=1)
    why: str = Field(..., max_length=240)
    fix_hint: str = Field(..., max_length=240)


class RepoReview(BaseModel):
    repo: str
    summary: str = Field(..., max_length=500)
    java_signals: dict[str, Any] = Field(default_factory=dict)
    errors: list[RepoError] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class RepoSummary(BaseModel):
    full_name: str
    name: str
    private: bool
    fork: bool = False
    archived: bool = False
    size: int = 0
    language: str | None = None
    default_branch: str = "main"
    html_url: str | None = None
    description: str | None = None
    updated_at: str | None = None


class ReviewRepoResult(BaseModel):
    full_name: str
    status: Literal["queued", "running", "done", "error"]
    review: RepoReview | None = None
    error: str | None = None


@dataclass(frozen=True)
class StudentContext:
    id: str
    student_id: str
    name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class GithubCredential:
    access_token: str
    gh_login: str
    scopes: list[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def serialize_job(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    out = _json_safe(doc)
    if "_id" in out:
        out["job_id"] = str(out.pop("_id"))
    return out


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be Bearer <token>",
        )
    return token.strip()


def _require_internal_key() -> str:
    if not INTERNAL_SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Knowledge-analysis INTERNAL_SERVICE_KEY is not configured",
        )
    return INTERNAL_SERVICE_KEY


async def verify_student_from_authorization(authorization: str | None) -> StudentContext:
    token = _extract_bearer_token(authorization)
    internal_key = _require_internal_key()

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.post(
                f"{USER_SERVICE_INTERNAL_URL}/internal/auth/verify",
                headers={"X-Internal-Key": internal_key},
                json={"token": token},
            )
        except httpx.RequestError as exc:
            logger.warning("user-service token verify request failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User service is unavailable",
            ) from exc

    body = resp.json() if resp.content else {}
    if resp.status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=body.get("error", "Token invalid"))
    if resp.status_code == 403:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=body.get("error", "Forbidden"))
    if resp.status_code >= 400 or not body.get("valid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=body.get("error", "Token invalid"))

    student = body.get("student") or {}
    student_object_id = student.get("id")
    public_student_id = student.get("student_id")
    if not student_object_id or not public_student_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="User service token verification response is missing student ids",
        )

    return StudentContext(
        id=student_object_id,
        student_id=public_student_id,
        name=student.get("name"),
        email=student.get("email"),
    )


async def get_student_github_credential(student: StudentContext) -> GithubCredential:
    internal_key = _require_internal_key()

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get(
                f"{USER_SERVICE_INTERNAL_URL}/internal/github/credential/{student.id}",
                headers={"X-Internal-Key": internal_key},
            )
        except httpx.RequestError as exc:
            logger.warning("user-service github credential request failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User service is unavailable",
            ) from exc

    body = resp.json() if resp.content else {}
    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub is not linked for this student",
        )
    if resp.status_code >= 400 or not body.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=body.get("error", "Could not read GitHub credential"),
        )

    data = body.get("data") or {}
    token = data.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="User service returned an empty GitHub token",
        )

    return GithubCredential(
        access_token=token,
        gh_login=data.get("gh_login") or "",
        scopes=data.get("scopes") or [],
    )


class GithubApiClient:
    def __init__(self, token: str):
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_URL,
            timeout=httpx.Timeout(20.0, connect=8.0),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Mentora-Knowledge-Analysis",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        resp = await self._client.get(path, params=params)
        if resp.status_code in (401, 403):
            detail = "GitHub token is invalid, expired, or missing required repo scope"
            try:
                detail = resp.json().get("message", detail)
            except ValueError:
                pass
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        if resp.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GitHub resource not found")
        if resp.status_code >= 400:
            detail = f"GitHub API request failed with HTTP {resp.status_code}"
            try:
                detail = resp.json().get("message", detail)
            except ValueError:
                pass
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
        return resp.json()

    async def list_user_repos(self) -> list[RepoSummary]:
        repos: list[RepoSummary] = []
        for page in range(1, 6):
            data = await self._get(
                "/user/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    "visibility": "all",
                    "affiliation": "owner,collaborator",
                    "sort": "updated",
                },
            )
            if not data:
                break
            repos.extend(RepoSummary.model_validate(item) for item in data)
            if len(data) < 100:
                break

        return [
            repo for repo in repos
            if not repo.fork and not repo.archived and repo.size > 0
        ]

    async def repo_bundle(self, repo: RepoSummary) -> str:
        owner, name = repo.full_name.split("/", 1)
        branch = repo.default_branch

        languages_task = self._get(f"/repos/{owner}/{name}/languages")
        commits_task = self._get(
            f"/repos/{owner}/{name}/commits",
            params={"per_page": 10, "sha": branch},
        )
        tree_task = self._get(
            f"/repos/{owner}/{name}/git/trees/{quote(branch, safe='')}",
            params={"recursive": "1"},
        )

        languages, commits, tree = await asyncio.gather(
            languages_task,
            commits_task,
            tree_task,
            return_exceptions=True,
        )

        if isinstance(languages, Exception):
            logger.info("Could not fetch languages for %s: %s", repo.full_name, languages)
            languages = {}
        if isinstance(commits, Exception):
            logger.info("Could not fetch commits for %s: %s", repo.full_name, commits)
            commits = []
        if isinstance(tree, Exception):
            logger.info("Could not fetch tree for %s: %s", repo.full_name, tree)
            tree = {"tree": []}

        tree_items = tree.get("tree", []) if isinstance(tree, dict) else []
        source_paths = self._select_source_paths(tree_items)
        source_files = await self._fetch_source_files(owner, name, branch, source_paths)

        payload = {
            "repo": repo.model_dump(),
            "languages": languages,
            "recent_commits": [
                {
                    "sha": c.get("sha"),
                    "message": (c.get("commit") or {}).get("message"),
                    "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
                }
                for c in commits[:10]
                if isinstance(c, dict)
            ],
            "tree_sample": [
                item.get("path")
                for item in tree_items[:MAX_TREE_PATHS]
                if isinstance(item, dict) and item.get("path")
            ],
            "source_files": source_files,
        }

        bundle = json.dumps(payload, indent=2, ensure_ascii=False)
        encoded = bundle.encode("utf-8", errors="replace")
        if len(encoded) > MAX_BUNDLE_BYTES:
            bundle = encoded[:MAX_BUNDLE_BYTES].decode("utf-8", errors="ignore")
        return bundle

    def _select_source_paths(self, tree_items: list[dict[str, Any]]) -> list[str]:
        candidates: list[tuple[int, int, str]] = []
        for item in tree_items:
            if item.get("type") != "blob":
                continue

            path = item.get("path") or ""
            if not path or _skip_path(path):
                continue

            ext = _file_ext(path)
            if ext not in SOURCE_EXT_PRIORITY:
                continue

            size = int(item.get("size") or 0)
            if size <= 0 or size > 200_000:
                continue

            candidates.append((SOURCE_EXT_PRIORITY[ext], size, path))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return [path for _, _, path in candidates[:MAX_SOURCE_FILES]]

    async def _fetch_source_files(
        self,
        owner: str,
        name: str,
        branch: str,
        paths: list[str],
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        total_bytes = 0

        for path in paths:
            if total_bytes >= MAX_BUNDLE_BYTES:
                break

            try:
                content = await self._get(
                    f"/repos/{owner}/{name}/contents/{quote(path, safe='/')}",
                    params={"ref": branch},
                )
            except HTTPException as exc:
                logger.info("Skipping unreadable file %s/%s: %s", name, path, exc.detail)
                continue

            if content.get("type") != "file" or content.get("encoding") != "base64":
                continue

            try:
                raw = base64.b64decode(content.get("content") or "", validate=False)
            except (ValueError, TypeError):
                continue

            if b"\x00" in raw:
                continue

            truncated = raw[:MAX_FILE_BYTES]
            total_bytes += len(truncated)
            files.append(
                {
                    "path": path,
                    "size": content.get("size"),
                    "truncated": len(raw) > len(truncated),
                    "content": truncated.decode("utf-8", errors="replace"),
                }
            )

        return files


def _file_ext(path: str) -> str:
    lowered = path.lower()
    dot = lowered.rfind(".")
    return lowered[dot:] if dot != -1 else ""


def _skip_path(path: str) -> bool:
    lowered = path.lower()
    filename = lowered.rsplit("/", 1)[-1]
    if filename in SKIP_FILENAMES:
        return True
    return any(part in SKIP_PATH_PARTS for part in lowered.split("/"))


def pick_repos(repos: list[RepoSummary], student: StudentContext) -> list[RepoSummary]:
    if not repos:
        return []

    seed_key = (INTERNAL_SERVICE_KEY or "mentora-dev-review-seed").encode("utf-8")
    seed_msg = f"{student.id}:{SEED_VERSION}".encode("utf-8")
    seed = int(hmac.new(seed_key, seed_msg, hashlib.sha256).hexdigest(), 16)
    rng = random.Random(seed)

    java = sorted([r for r in repos if r.language == "Java"], key=lambda r: r.full_name.lower())
    others = sorted([r for r in repos if r.language != "Java"], key=lambda r: r.full_name.lower())

    chosen: list[RepoSummary] = []
    if java:
        chosen.extend(rng.sample(java, k=min(3, len(java))))
    if len(chosen) < MAX_REPOS and others:
        chosen.extend(rng.sample(others, k=min(MAX_REPOS - len(chosen), len(others))))

    rng.shuffle(chosen)
    return chosen[:MAX_REPOS]


def _review_prompt(bundle: str) -> str:
    schema = json.dumps(RepoReview.model_json_schema(), indent=2)
    return (
        "SYSTEM: You are a strict Java/software-engineering code reviewer for university students.\n"
        "You will receive one repository's metadata, recent commits, tree sample, and selected source files.\n"
        "Output ONLY a JSON object validating the schema. No prose. No markdown fences.\n"
        "Prefer concrete defects over vague advice. If line numbers are not visible, set line to null.\n\n"
        f"SCHEMA:\n{schema}\n\n"
        f"USER REPOSITORY BUNDLE:\n{bundle}"
    )


async def review_repo(github: GithubApiClient, repo: RepoSummary) -> ReviewRepoResult:
    try:
        bundle = await github.repo_bundle(repo)
        if not bundle.strip():
            return ReviewRepoResult(
                full_name=repo.full_name,
                status="error",
                error="Repository bundle is empty",
            )

        raw = await get_router().generate_json(
            prompt=_review_prompt(bundle),
            schema=RepoReview,
            task=Task.REPO_REVIEW,
            temperature=0.2,
        )
        review = RepoReview.model_validate(raw)
        if review.repo != repo.full_name:
            review = review.model_copy(update={"repo": repo.full_name})
        return ReviewRepoResult(full_name=repo.full_name, status="done", review=review)
    except LLMAuthError:
        raise
    except Exception as exc:  # noqa: BLE001 - per-repo failures should not kill the whole job
        logger.exception("Repo review failed for %s", repo.full_name)
        return ReviewRepoResult(full_name=repo.full_name, status="error", error=str(exc))


async def ensure_review_indexes() -> None:
    db = get_database()
    await db.repo_review_jobs.create_index([("student_id", 1), ("created_at", -1)])
    await db.repo_review_jobs.create_index([("status", 1), ("updated_at", -1)])


async def build_repo_selection(student: StudentContext, credential: GithubCredential) -> dict[str, Any]:
    github = GithubApiClient(credential.access_token)
    try:
        repos = await github.list_user_repos()
    finally:
        await github.aclose()

    selected = pick_repos(repos, student)
    return {
        "seed_version": SEED_VERSION,
        "eligible_count": len(repos),
        "selected": [repo.model_dump() for repo in selected],
        "repos": [repo.model_dump() for repo in repos],
    }


async def start_review_job(
    *,
    student: StudentContext,
    credential: GithubCredential,
    selected_full_names: list[str] | None,
) -> tuple[dict[str, Any], list[RepoSummary]]:
    await ensure_review_indexes()
    db = get_database()
    github = GithubApiClient(credential.access_token)

    try:
        repos = await github.list_user_repos()
        repo_by_name = {repo.full_name: repo for repo in repos}

        if selected_full_names:
            if len(selected_full_names) > MAX_REPOS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Select at most {MAX_REPOS} repositories",
                )
            missing = [name for name in selected_full_names if name not in repo_by_name]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Selected repositories are not accessible: {', '.join(missing)}",
                )
            selected = [repo_by_name[name] for name in selected_full_names]
        else:
            selected = pick_repos(repos, student)

        if not selected:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No eligible GitHub repositories were found",
            )

        now = _utcnow()
        job = {
            "student_id": student.id,
            "public_student_id": student.student_id,
            "gh_login": credential.gh_login,
            "seed_version": SEED_VERSION,
            "status": "running",
            "repos": [
                {"full_name": repo.full_name, "status": "queued", "review": None, "error": None}
                for repo in selected
            ],
            "created_at": now,
            "updated_at": now,
        }
        insert = await db.repo_review_jobs.insert_one(job)
        created = await db.repo_review_jobs.find_one({"_id": insert.inserted_id})
        return serialize_job(created) or {}, selected
    finally:
        await github.aclose()


async def process_review_job(
    *,
    job_id: str | ObjectId,
    credential: GithubCredential,
    selected_repos: list[RepoSummary],
) -> dict[str, Any]:
    await ensure_review_indexes()
    db = get_database()
    job_object_id = ObjectId(job_id) if isinstance(job_id, str) else job_id
    github = GithubApiClient(credential.access_token)

    try:
        semaphore = asyncio.Semaphore(3)

        async def one(repo: RepoSummary) -> ReviewRepoResult:
            async with semaphore:
                await db.repo_review_jobs.update_one(
                    {"_id": job_object_id, "repos.full_name": repo.full_name},
                    {
                        "$set": {
                            "repos.$.status": "running",
                            "updated_at": _utcnow(),
                        }
                    },
                )
                try:
                    result = await asyncio.wait_for(
                        review_repo(github, repo),
                        timeout=PER_REPO_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    result = ReviewRepoResult(
                        full_name=repo.full_name,
                        status="error",
                        error=f"Review timed out after {PER_REPO_TIMEOUT_SECONDS}s",
                    )

                await db.repo_review_jobs.update_one(
                    {"_id": job_object_id, "repos.full_name": repo.full_name},
                    {
                        "$set": {
                            "repos.$.status": result.status,
                            "repos.$.review": result.review.model_dump() if result.review else None,
                            "repos.$.error": result.error,
                            "repos.$.finished_at": _utcnow(),
                            "updated_at": _utcnow(),
                        }
                    },
                )
                return result

        try:
            results = await asyncio.gather(*(one(repo) for repo in selected_repos))
        except LLMAuthError as exc:
            await db.repo_review_jobs.update_one(
                {"_id": job_object_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": "LLM service account or Vertex AI authorization failed",
                        "updated_at": _utcnow(),
                    }
                },
            )
            logger.exception("Repo review job failed because LLM auth failed: %s", exc)
            return serialize_job(await db.repo_review_jobs.find_one({"_id": job_object_id})) or {}
        except Exception as exc:  # noqa: BLE001 - background work must persist failure state
            await db.repo_review_jobs.update_one(
                {"_id": job_object_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": str(exc),
                        "updated_at": _utcnow(),
                    }
                },
            )
            logger.exception("Repo review background job failed: %s", exc)
            return serialize_job(await db.repo_review_jobs.find_one({"_id": job_object_id})) or {}

        done_count = sum(1 for result in results if result.status == "done")
        final_status = "done" if done_count == len(results) else "partial" if done_count else "failed"

        java_level = None
        evidence = None
        for result in results:
            if result.review and result.review.java_signals:
                java_level = result.review.java_signals.get("level")
                evidence = result.review.java_signals.get("evidence")
                break

        await db.repo_review_jobs.update_one(
            {"_id": job_object_id},
            {
                "$set": {
                    "status": final_status,
                    "java_level_inferred": java_level,
                    "signals_evidence": evidence,
                    "updated_at": _utcnow(),
                }
            },
        )

        return serialize_job(await db.repo_review_jobs.find_one({"_id": job_object_id})) or {}
    finally:
        await github.aclose()


async def run_review_job(
    *,
    student: StudentContext,
    credential: GithubCredential,
    selected_full_names: list[str] | None,
) -> dict[str, Any]:
    job, selected = await start_review_job(
        student=student,
        credential=credential,
        selected_full_names=selected_full_names,
    )
    return await process_review_job(
        job_id=job["job_id"],
        credential=credential,
        selected_repos=selected,
    )


async def run_single_repo_rereview(
    *,
    student: StudentContext,
    credential: GithubCredential,
    repo_full_name: str,
) -> dict[str, Any]:
    return await run_review_job(
        student=student,
        credential=credential,
        selected_full_names=[repo_full_name],
    )
