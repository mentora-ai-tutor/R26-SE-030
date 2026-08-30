from fastapi import APIRouter, Depends

from app.api.student_routes import get_latest_student_analysis, verify_jwt_student
from app.services.mongodb import save_content_recommendation

router = APIRouter(prefix="/api/content", tags=["Content Recommendation Agent"])


@router.post(
    "/recommend", summary="Recommend Remedial Learning Resources (RAG)"
)
def recommend_content(token_student_id: str = Depends(verify_jwt_student)):
    analysis = get_latest_student_analysis(token_student_id)
    gaps = analysis.get("knowledge_gaps") or analysis.get("mastery_profile", {}).get("knowledge_gaps") or []
    first_gap = gaps[0] if gaps else {}
    weak_subskills = first_gap.get("weak_subskills") or []
    first_subskill = weak_subskills[0] if weak_subskills else {}
    target_subskill = (
        first_subskill.get("subskill")
        or first_gap.get("suggested_intervention", {}).get("primary")
        or "General Concepts"
    )
    topic = first_gap.get("topic")

    result = {
        "status": "success",
        "student_id": token_student_id,
        "topic": topic,
        "target_subskill": target_subskill,
        "recommendations": [
            {
                "title": f"Understanding {target_subskill} in Java",
                "type": "Interactive Tutorial",
                "estimated_minutes": 15,
                "link": f"https://java-platform.org/learn/{target_subskill.lower().replace(' ', '-')}",
            }
        ],
    }

    # Save the content recommendation to MongoDB
    save_content_recommendation({
        "student_id": token_student_id,
        "topic": topic,
        "weak_subskill": target_subskill,
        "subskill": target_subskill,
        "target_subskill": target_subskill,
        "recommendations": result["recommendations"],
        "result": result,
    })

    return result