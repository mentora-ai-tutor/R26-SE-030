"""The LLM 'explain the prediction' layer.

The NumPy model has ALREADY decided role/fit/gaps. Gemini only turns those numbers into a
student-facing narrative via the existing schema-constrained ``generate_json`` mechanism
(``Task.CAREER_NARRATIVE``). It cannot change the decision — we validate the headline names
the predicted role, else we fall back to a deterministic template (mirrors the quiz seed
fallback in ``quiz_generator``). An LLM outage never blocks a prediction.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.models.career import CareerNarrative

logger = logging.getLogger(__name__)


def _facts_prompt(facts: Dict[str, Any]) -> str:
    gaps = ", ".join(f"{g['axis_name']} (you {g['your_score']:.2f} vs needed {g['required_score']:.2f})"
                     for g in facts.get("missing_competencies", [])) or "none significant"
    matched = ", ".join(facts.get("matched_competencies", [])) or "the basics"
    asp = facts.get("aspiration")
    asp_line = ""
    if asp:
        asp_line = (f"\nThe student ASPIRES to be a '{asp['stated_role']}' (current fit "
                    f"{asp['fit_to_stated']:.0%}, ~{asp['est_hours_to_ready']}h to get competitive).")
    return (
        "You are a supportive software-career mentor. A calibrated model has ALREADY decided "
        "the student's best-fit role from their measured Java competencies. Write an encouraging, "
        "honest explanation — do NOT change the role or invent numbers.\n\n"
        f"Best-fit role (FIXED): {facts['best_fit_role']} (fit {facts['fit_score']:.0%}, "
        f"readiness: {facts['readiness_level']}).\n"
        f"Strengths that support it: {matched}.\n"
        f"Competency gaps to close: {gaps}.{asp_line}\n\n"
        "Return JSON: headline (one sentence, MUST name the best-fit role), why_fit (2-4 short "
        "bullet strings), gap_plan (2-4 short actionable bullets), encouragement (one sentence)."
    )


async def build_narrative(facts: Dict[str, Any]) -> CareerNarrative:
    """LLM narrative with a deterministic template fallback."""
    try:
        # Imported lazily so the model path has no hard dependency on the LLM stack.
        from app.services.llm import Task, get_router

        raw = await get_router().generate_json(
            prompt=_facts_prompt(facts),
            schema=CareerNarrative,
            task=Task.CAREER_NARRATIVE,
            temperature=0.5,
        )
        narrative = CareerNarrative.model_validate(raw)
        # Guard: the LLM must reference the model's decision, not override it.
        if facts["best_fit_role"].split(" ")[0].lower() in narrative.headline.lower():
            return narrative
        logger.warning("Career narrative did not reference predicted role; using template.")
    except Exception as exc:  # pragma: no cover - any LLM/router/validation failure
        logger.warning("Career narrative LLM failed (%s); using template.", exc)
    return _template_narrative(facts)


def _template_narrative(facts: Dict[str, Any]) -> CareerNarrative:
    role = facts["best_fit_role"]
    matched: List[str] = facts.get("matched_competencies", [])
    gaps = facts.get("missing_competencies", [])
    asp: Optional[Dict[str, Any]] = facts.get("aspiration")

    why = [f"Your strongest areas — {', '.join(matched[:3])} — line up with what {role}s rely on."] if matched else \
          [f"Your overall profile is closest to {role}."]
    why.append(f"Current readiness: {facts['readiness_level']} (fit {facts['fit_score']:.0%}).")

    plan = [f"Strengthen {g['axis_name']} (you're at {g['your_score']:.0%}, the role wants ~{g['required_score']:.0%})."
            for g in gaps[:3]] or ["Keep practising across topics to lock in your strengths."]

    enc = "You're on a solid track — close these gaps and you'll be a strong candidate."
    if asp:
        enc = (f"You aspire to {asp['stated_role']} — you're {asp['fit_to_stated']:.0%} of the way; "
               f"about {asp['est_hours_to_ready']}h of focused practice closes the gap.")

    return CareerNarrative(
        headline=f"Your profile best fits a {role}.",
        why_fit=why, gap_plan=plan, encouragement=enc,
    )
