"""Career-fit prediction orchestration: features -> NumPy model -> LLM narrative -> persist.

The model makes the decision (deterministic, calibrated). The LLM only narrates. Reads the
existing canonical mastery profile + latest quiz result; never recomputes the pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models.career import CareerPrediction
from app.services.career import featurizer
from app.services.career.model import load_model, readiness_level
from app.services.career.narrative import build_narrative
from app.services.career.store import get_latest_career_prediction, save_career_prediction
from app.services.mastery_profile_store import get_latest_mastery_profile
from app.services.quiz_store import get_latest_result

_CACHE_SECONDS = 1800  # re-use an existing prediction if it's under 30 minutes old

CAREER_SCHEMA_VERSION = "kaa-career-v1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _match_role(target: str, roles: list[str]) -> Optional[str]:
    """Map a free-text ambition onto one of our role labels (keyword/substring)."""
    t = target.lower()
    for r in roles:
        if t in r.lower() or r.lower() in t:
            return r
    keywords = {
        "backend": "Junior Java / Backend Developer", "back-end": "Junior Java / Backend Developer",
        "algorithm": "DSA / Algorithms-focused Engineer", "dsa": "DSA / Algorithms-focused Engineer",
        "competitive": "DSA / Algorithms-focused Engineer",
        "system": "Systems / Concurrency Engineer", "concurren": "Systems / Concurrency Engineer",
        "qa": "QA / Test Automation Engineer", "test": "QA / Test Automation Engineer",
        "software engineer": "General Software Engineer", "full": "General Software Engineer",
    }
    for k, r in keywords.items():
        if k in t and r in roles:
            return r
    return None


async def predict_career(student_id: str, target_role: Optional[str] = None) -> Dict[str, Any]:
    # Return cached prediction if recent enough and no specific target_role requested
    if not target_role:
        cached = await get_latest_career_prediction(student_id)
        if cached:
            created_raw = cached.get("created_at")
            if created_raw:
                try:
                    # Strip timezone suffix so fromisoformat always gives a naive datetime
                    clean = str(created_raw).split("+")[0].rstrip("Z")
                    created_dt = datetime.fromisoformat(clean)
                    age_s = (datetime.utcnow() - created_dt).total_seconds()
                    if age_s < _CACHE_SECONDS:
                        return cached
                except (ValueError, TypeError):
                    pass

    profile = await get_latest_mastery_profile(student_id)
    quiz = await get_latest_result(student_id)

    if not profile and not quiz:
        pred = CareerPrediction(
            schema_version=CAREER_SCHEMA_VERSION, student_id=student_id, generated_at=_now(),
            evidence_sufficient=False, evidence={"topics_covered": 0, "questions_answered": 0},
            note="No quiz or analysis found yet — take the Java skill check first.",
        )
        return pred.model_dump()

    model = load_model()
    x = featurizer.featurize(profile, quiz, model.feature_axes)
    evidence = featurizer.evidence(profile, quiz)

    ranked = model.rank(x)
    best_role, best_fit = ranked[0]
    missing = model.gaps_for(x, best_role)
    matched = model.matched_for(x, best_role)
    difficulty = (quiz or {}).get("difficulty_reached", "medium")
    overall = (profile or {}).get("overall_mastery_score")
    if overall is None:
        overall = (quiz or {}).get("score_percent")
    readiness = readiness_level(overall, difficulty)

    aspiration = None
    if target_role:
        matched_role = _match_role(target_role, model.roles)
        if matched_role:
            proba = model.predict_proba(x)
            fit_to_stated = float(proba[model.roles.index(matched_role)])
            gap_to_stated = model.gaps_for(x, matched_role)
            total_gap = sum(g["gap"] for g in gap_to_stated)
            aspiration = {
                "stated_role": matched_role,
                "fit_to_stated": round(fit_to_stated, 4),
                "gap_to_stated": gap_to_stated,
                "est_hours_to_ready": int(round(total_gap * 40)),  # ~4h per 0.1 competency point
            }

    facts = {
        "best_fit_role": best_role, "fit_score": best_fit, "readiness_level": readiness,
        "matched_competencies": matched, "missing_competencies": missing, "aspiration": aspiration,
    }
    narrative = await build_narrative(facts)

    pred = CareerPrediction(
        schema_version=CAREER_SCHEMA_VERSION, student_id=student_id, generated_at=_now(),
        model_version=model.model_version,
        evidence_sufficient=bool(evidence["sufficient"]), evidence=evidence,
        best_fit_role=best_role, readiness_level=readiness,
        ranked_roles=[{"role": r, "fit_score": round(p, 4), "confidence": round(p, 4)} for r, p in ranked[:3]],
        matched_competencies=matched, missing_competencies=missing,
        aspiration_alignment=aspiration, narrative=narrative,
        note=None if evidence["sufficient"] else
        "Limited evidence so far — answer more topics for a more confident prediction.",
    )
    out = pred.model_dump()
    try:
        await save_career_prediction(dict(out))
    except Exception:  # persistence is best-effort; never block the response
        pass
    return out
