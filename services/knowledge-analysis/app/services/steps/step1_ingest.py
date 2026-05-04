from datetime import datetime

from app.models.schemas import LearnerInput


def step1_ingest(data: LearnerInput) -> dict:
    mode = "full" if (data.github_enabled and data.github_commits) else "reduced"
    return {
        "student_id": data.student_id,
        "mode": mode,
        "quiz_count": len(data.quiz_sessions),
        "sandbox_count": len(data.sandbox_sessions),
        "commit_count": len(data.github_commits) if data.github_commits else 0,
        "ingested_at": datetime.utcnow().isoformat(),
    }
