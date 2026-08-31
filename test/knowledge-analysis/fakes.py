"""Shared test doubles for the KAA test suite.

Everything here is importable by unit/integration/performance tests via
``import fakes`` (conftest.py puts this directory on sys.path). No real
MongoDB, gateway or LLM connectivity is ever created.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from bson import ObjectId

# Internal (object) id + public student id used by the fake auth context.
STUDENT_OBJECT_ID = "507f1f77bcf86cd799439011"
PUBLIC_STUDENT_ID = "IT22201232"

AUTH_HEADER = {"Authorization": "Bearer test.jwt.token.example"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _InsertResult:
    def __init__(self, inserted_id: Any | None = None, inserted_ids: list | None = None):
        self.inserted_id = inserted_id
        self.inserted_ids = inserted_ids if inserted_ids is not None else []


class FakeCursor:
    """Minimal stand-in for a Motor cursor (find(...).sort().limit().to_list())."""

    def __init__(self, docs: list):
        self._docs = list(docs)
        self._limit_n: int | None = None

    def sort(self, *args, **kwargs) -> "FakeCursor":
        return self

    def limit(self, n: int) -> "FakeCursor":
        self._limit_n = n
        return self

    async def to_list(self, length: int | None = None) -> list:
        n = length if length is not None else self._limit_n
        docs = list(self._docs)
        return docs[:n] if n is not None else docs


class FakeCollection:
    """In-memory collection that supports the calls the endpoints actually make.

    ``find``/``find_one``/``count_documents`` do exact-match filtering on the
    top-level query keys — enough for the read signatures used in the app.
    ``sort`` is honored for the common ``[("created_at", -1)]`` style.
    """

    def __init__(self, docs: Optional[list] = None):
        self.docs: list = list(docs or [])
        self.indexes: list = []

    def _matches(self, doc: dict, query: dict) -> bool:
        if not query:
            return True
        for key, value in query.items():
            if doc.get(key) != value:
                return False
        return True

    def find(self, query: Optional[dict] = None, *args, **kwargs) -> FakeCursor:
        return FakeCursor([d for d in self.docs if self._matches(d, query or {})])

    async def find_one(
        self, query: Optional[dict] = None, sort: Optional[list] = None, *args, **kwargs
    ) -> Optional[dict]:
        matched = [d for d in self.docs if self._matches(d, query or {})]
        if not matched:
            return None
        if sort:
            for key, direction in reversed(list(sort)):
                matched.sort(
                    key=lambda doc, k=key: doc.get(k) or "",
                    reverse=(direction == -1),
                )
        return matched[0]

    async def count_documents(self, query: Optional[dict] = None) -> int:
        return sum(1 for d in self.docs if self._matches(d, query or {}))

    async def insert_one(self, doc: dict) -> _InsertResult:
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc)
        return _InsertResult(inserted_id=doc["_id"])

    async def insert_many(self, docs: list, ordered: bool = False, *args, **kwargs) -> _InsertResult:
        ids: list = []
        for doc in docs:
            ids.append((await self.insert_one(doc)).inserted_id)
        return _InsertResult(inserted_ids=ids)

    async def update_one(self, *args, **kwargs) -> None:
        return None

    async def create_index(self, *args, **kwargs) -> str:
        return "index-created"


class FakeDatabase:
    """Stand-in for AsyncIOMotorDatabase; unknown collections appear on demand."""

    def __init__(self):
        self.repo_review_jobs = FakeCollection()
        self.sandbox_attempts = FakeCollection()
        self.quiz_results = FakeCollection()
        self.quiz_sessions = FakeCollection()
        self.quiz_question_bank = FakeCollection()
        self.mastery_profiles = FakeCollection()
        self.sandbox_challenges = FakeCollection()
        self.career_predictions = FakeCollection()

    def __getattr__(self, name: str) -> FakeCollection:
        col = FakeCollection()
        setattr(self, name, col)
        return col


class FakeLLMRouter:
    """Async stand-in for LLMRouter.generate_json.

    Configured with either an immutable ``result`` (returned as-is), an
    ``error`` (raised on every call), or neither (returns a schema stub).
    Every invocation is recorded on ``calls`` so tests can assert the LLM path
    was actually exercised (and overridden).
    """

    def __init__(
        self,
        result: Any = None,
        error: Optional[Exception] = None,
    ):
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    async def generate_json(self, *, prompt: str, schema: type, task=None, **kwargs) -> Any:
        self.calls.append(
            {"task": getattr(task, "value", str(task)), "prompt": prompt, "kwargs": kwargs}
        )
        if self.result is not None:
            return self.result
        if self.error is not None:
            raise self.error
        return schema.model_json_schema()

    async def boot_probe(self) -> dict:
        return {}


def make_fake_verify() -> Callable:
    """Return an async verifier returning a fixed StudentContext.

    The routes ``await`` this function, so it must return an awaitable.
    """

    async def _verify(authorization: Optional[str] = None):
        from app.services.github_review_service import StudentContext

        return StudentContext(
            id=STUDENT_OBJECT_ID,
            student_id=PUBLIC_STUDENT_ID,
            name="Test Student",
            email="student@mentora.test",
        )

    return _verify


def patch_database(monkeypatch, fdb: FakeDatabase) -> None:
    """Point every ``get_database`` binding used by the app at the fake DB.

    The route/service modules do ``from app.db.database import get_database``,
    which binds the name at import time — so the fake must be installed in each
    module namespace, not only in ``app.db.database``.
    """
    import app.db.database as db_mod
    import app.api.knowledge_profile_routes as kp_mod
    import app.api.github_review_routes as groutes_mod
    import app.services.mastery_profile_store as mps_mod
    import app.services.quiz_store as qs_mod
    import app.services.career.store as cs_mod
    import app.services.sandbox_challenge_generator as scg_mod
    import app.services.github_review_service as grs_mod
    import app.services.mastery_from_reviews as mfr_mod

    monkeypatch.setattr(db_mod, "get_client", lambda: None)
    monkeypatch.setattr(db_mod, "get_database", lambda: fdb)
    for mod in (
        kp_mod,
        groutes_mod,
        mps_mod,
        qs_mod,
        cs_mod,
        scg_mod,
        grs_mod,
        mfr_mod,
    ):
        monkeypatch.setattr(mod, "get_database", lambda: fdb)


def patch_auth(monkeypatch, verify: Optional[Callable] = None) -> None:
    """Replace ``verify_student_from_authorization`` in every route module."""
    import app.api.routes as routes_mod
    import app.api.knowledge_profile_routes as kp_mod
    import app.api.sandbox_routes as sandbox_mod
    import app.api.quiz_routes as quiz_mod
    import app.api.github_review_routes as groutes_mod

    fake = verify or make_fake_verify()
    for mod in (routes_mod, kp_mod, sandbox_mod, quiz_mod, groutes_mod):
        monkeypatch.setattr(mod, "verify_student_from_authorization", fake)