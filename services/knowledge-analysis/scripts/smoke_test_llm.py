"""
Smoke test for the LLM provider layer.

Usage (from services/knowledge-analysis/):
    export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/secrets/gcp-sa.json
    export GCP_PROJECT=chapmanvoice
    export GCP_LOCATION=us-central1
    python -m scripts.smoke_test_llm

What it does:
    1. Boot-probes every tier (one tiny call each), prints a status table.
    2. Runs a real REPO_REVIEW-shaped JSON-mode call against the chain and
       prints the validated result.

Exit codes:
    0  primary tier OR a fallback succeeded for the real call
    1  no tier succeeded
    2  auth misconfiguration (SA missing role, project mismatch, etc.)
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from typing import Literal

from pydantic import BaseModel, Field


def _add_repo_root_to_path() -> None:
    """Allow `python -m scripts.smoke_test_llm` from the service dir."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    if root not in sys.path:
        sys.path.insert(0, root)


_add_repo_root_to_path()

from app.services.llm import get_router, Task                       # noqa: E402
from app.services.llm.base import LLMAuthError, LLMError             # noqa: E402


# --- A tiny schema that mirrors RepoReview shape (without the full bundle) ---
class _Signal(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    evidence: str = Field(..., max_length=240)


class _Mini(BaseModel):
    summary: str = Field(..., max_length=240)
    java_signals: _Signal


_PROMPT = (
    "You are reviewing a Java student's tiny project.\n"
    "Project: a class with one main method that prints 'Hello, world'.\n"
    "Return JSON only — no prose, no fences."
)


def _print_table(rows: list[tuple[str, str]]) -> None:
    width_k = max(len(k) for k, _ in rows)
    print()
    print(f"{'tier'.ljust(width_k)}  status")
    print(f"{'-' * width_k}  ------")
    for k, v in rows:
        print(f"{k.ljust(width_k)}  {v}")
    print()


async def main() -> int:
    router = get_router()

    # --- Boot probe -----------------------------------------------------------
    print("Probing tiers...")
    try:
        probe = await router.boot_probe()
    except LLMAuthError as e:
        print(f"AUTH ERROR during probe: {e}", file=sys.stderr)
        print(
            "Hint: confirm GOOGLE_APPLICATION_CREDENTIALS points at a valid "
            "SA JSON, and the SA has roles/aiplatform.user on the project.",
            file=sys.stderr,
        )
        return 2

    rows = [(k, "ALIVE" if v else "dead") for k, v in probe.items()]
    _print_table(rows)

    if not any(probe.values()):
        print("No live tier — cannot run real call.", file=sys.stderr)
        return 1

    # --- Real JSON call -------------------------------------------------------
    print("Running JSON-mode call against the chain (task=REPO_REVIEW)...")
    try:
        result = await router.generate_json(
            prompt=_PROMPT,
            schema=_Mini,
            task=Task.REPO_REVIEW,
            temperature=0.2,
        )
    except LLMAuthError as e:
        print(f"AUTH ERROR: {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"All tiers failed: {e}", file=sys.stderr)
        return 1

    print("OK. Validated output:\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
