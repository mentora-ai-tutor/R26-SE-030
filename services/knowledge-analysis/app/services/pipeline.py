from app.models.schemas import LearnerInput
from app.services.steps.step1_ingest import step1_ingest
from app.services.steps.step2_preprocess import step2_preprocess
from app.services.steps.step3_features import step3_extract_features
from app.services.steps.step4_analysis import step4_analyse
from app.services.steps.step5_mode import step5_mode_execution
from app.services.steps.step6_cluster import step6_cluster
from app.services.steps.step7_scoring import step7_score
from app.services.steps.step8_profile import step8_build_profile
from app.services.steps.step9_validation import step9_validate
from app.services.steps.step10_output import step10_output


def run_full_pipeline(data: LearnerInput) -> dict:
    ingestion = step1_ingest(data)
    preprocessed = step2_preprocess(data)
    features = step3_extract_features(data, preprocessed)
    analysis = step4_analyse(features)
    mode_result = step5_mode_execution(data, features, analysis)
    clusters = step6_cluster(mode_result["enriched_analysis"])
    scored = step7_score(data, features, mode_result)
    profile = step8_build_profile(data.student_id, scored, clusters, mode_result, features)
    validation = step9_validate(profile, data)
    output = step10_output(profile, validation)

    return {
        "pipeline": {
            "step1_ingestion": ingestion,
            "step2_preprocessing": {
                "quiz_topics": list(preprocessed["quiz_scores_normalised"].keys()),
                "sandbox_topics": list(preprocessed["sandbox_metrics_normalised"].keys()),
            },
            "step3_features": {t: list(f.keys()) for t, f in features.items()},
            "step4_analysis": {t: v["issues"] for t, v in analysis.items()},
            "step5_mode": mode_result["mode"],
            "step6_clusters": clusters,
            "step7_scores": {t: v["mastery_score"] for t, v in scored.items()},
            "step8_profile_summary": {
                "weak": profile["weak_topics"],
                "medium": profile["medium_topics"],
                "strong": profile["strong_topics"],
            },
            "step9_validation": validation,
            "step10_output": output,
        },
        "final_output": output,
    }
