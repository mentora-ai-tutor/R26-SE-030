import random
import string
from datetime import datetime
from typing import Optional
import ulid


def generate_session_id() -> str:
    """Generate a unique session ID in PS-XXXXXXXX format."""
    return f"PS-{ulid.new().str[:8].upper()}"


def generate_group_session_id() -> str:
    """Generate a unique group session ID in GS-XXXXXXXX format."""
    return f"GS-{ulid.new().str[:8].upper()}"


def generate_question_id() -> str:
    """Generate a unique question ID in Q-XXXXXXXX format."""
    return f"Q-{ulid.new().str[:8].upper()}"


def generate_notification_id() -> str:
    """Generate a unique notification ID in N-XXXXXXXX format."""
    return f"N-{ulid.new().str[:8].upper()}"


def generate_queue_id() -> str:
    """Generate a unique queue entry ID."""
    return f"WQ-{ulid.new().str[:8].upper()}"


def generate_batch_id() -> str:
    """Generate a unique batch ID."""
    return f"BATCH-{ulid.new().str[:8].upper()}"


def mastery_level_to_score(level: str) -> float:
    """Convert mastery level string to numeric score."""
    mapping = {
        "advanced": 90.0,
        "proficient": 70.0,
        "beginner": 40.0,
    }
    return mapping.get(level.lower(), 50.0)


def mastery_level_to_compatibility(level: str) -> float:
    """Convert mastery level to compatibility score component."""
    mapping = {
        "advanced": 100.0,
        "proficient": 80.0,
        "beginner": 50.0,
    }
    return mapping.get(level.lower(), 50.0)


def gap_type_to_score(gap_type: str) -> float:
    """Convert gap type to severity score."""
    if gap_type == "FUNDAMENTAL_GAP":
        return 100.0
    return 70.0


def calculate_compatibility_score(
    teacher_confidence: float,
    teacher_mastery_level: str,
    gap_type: str,
    learner_mastery_score: float,
    learner_confidence: float,
) -> float:
    """
    Calculate compatibility score (0-100) between learner and teacher.
    Weights:
        Teacher confidence      25%
        Teacher mastery level   25%
        Gap severity            20%
        Gap magnitude           15%
        Learner inverse conf    15%
    """
    teacher_conf_component = teacher_confidence * 100 * 0.25
    teacher_mastery_component = mastery_level_to_compatibility(teacher_mastery_level) * 0.25
    gap_severity_component = gap_type_to_score(gap_type) * 0.20
    gap_magnitude_component = (100 - learner_mastery_score) * 0.15
    learner_inv_conf_component = (1 - learner_confidence) * 100 * 0.15

    score = (
        teacher_conf_component
        + teacher_mastery_component
        + gap_severity_component
        + gap_magnitude_component
        + learner_inv_conf_component
    )
    return min(100.0, max(0.0, score))


def calculate_learner_score(
    correct_answers: int,
    total_questions: int,
    hints_used: int,
    help_requests: int,
) -> float:
    """Calculate learner performance score."""
    if total_questions == 0:
        return 0.0
    base_accuracy = (correct_answers / total_questions) * 100
    penalty = (hints_used * 5) + (help_requests * 10)
    return max(0.0, base_accuracy - penalty)


def calculate_teacher_score(initial_mastery: float, final_mastery: float) -> float:
    """Calculate teacher effectiveness score."""
    if (100 - initial_mastery) == 0:
        return 100.0
    improvement = (final_mastery - initial_mastery) / (100 - initial_mastery)
    return max(0.0, min(100.0, improvement * 100))


def calculate_updated_mastery_score(
    previous_score: float,
    is_correct: bool,
    bloom_level: int,
    consecutive_correct: int,
    consecutive_incorrect: int,
    time_taken_seconds: Optional[int] = None
) -> float:
    """Calculate updated mastery score dynamically after each question."""
    # Base change based on correctness
    base_change = 5.0 if is_correct else -3.0
    
    # Difficulty modifier
    difficulty_multiplier = 1.0 + (bloom_level * 0.1)  # Higher bloom = more points or bigger penalty
    
    # Consistency modifier
    consistency_multiplier = 1.0
    if is_correct and consecutive_correct > 1:
        consistency_multiplier += (consecutive_correct * 0.1)
    elif not is_correct and consecutive_incorrect > 1:
        consistency_multiplier += (consecutive_incorrect * 0.1)
        
    # Time penalty/bonus (assume expected time is ~60 seconds)
    time_modifier = 1.0
    if time_taken_seconds:
        if is_correct and time_taken_seconds < 30:
            time_modifier = 1.1 # Quick correct answer bonus
        elif not is_correct and time_taken_seconds < 10:
            time_modifier = 1.2 # Rushed incorrect answer penalty

    change = base_change * difficulty_multiplier * consistency_multiplier * time_modifier
    
    new_score = previous_score + change
    return min(100.0, max(0.0, new_score))



def calculate_role_score(
    task_completion: float,
    collaboration: float,
    communication: float,
) -> float:
    """Calculate individual role score in group session."""
    return (task_completion * 0.50) + (collaboration * 0.30) + (communication * 0.20)


def calculate_priority_score(
    gap_type: str,
    waiting_since: datetime,
    attempts: int,
) -> float:
    """Calculate waiting queue priority score."""
    base = 50.0 if gap_type == "FUNDAMENTAL_GAP" else 25.0
    waiting_minutes = (datetime.utcnow() - waiting_since).total_seconds() / 60
    return base + waiting_minutes + (attempts * 20)


def sort_knowledge_gaps(gaps: list) -> list:
    """Sort gaps: FUNDAMENTAL_GAP first, then PARTIAL_GAP; by confidence descending."""
    order = {"FUNDAMENTAL_GAP": 0, "PARTIAL_GAP": 1}
    return sorted(
        gaps,
        key=lambda g: (order.get(g.get("gap_type", "PARTIAL_GAP"), 1), -g.get("confidence", 0)),
    )


def get_next_bloom_level(current: int, consecutive_correct: int, consecutive_incorrect: int) -> int:
    """Determine next Bloom's taxonomy level."""
    if consecutive_correct >= 2 and current < 6:
        return current + 1
    if consecutive_incorrect >= 1 and current > 1:
        return current - 1
    return current


def is_mastery_achieved(bloom_level: int, current_mastery_score: float) -> bool:
    """Check if mastery is achieved (score >= 85 and reached at least level 5)."""
    return current_mastery_score >= 85.0 and bloom_level >= 5


def rotate_group_roles(members: list, session_number: int) -> list:
    """
    Rotate roles each session.
    Session 1: index 0=EXPLAINER, 1=SOLVER, 2=REVIEWER
    Session 2: index 1=EXPLAINER, 2=SOLVER, 0=REVIEWER
    Session 3: index 2=EXPLAINER, 0=SOLVER, 1=REVIEWER
    """
    roles = ["EXPLAINER", "SOLVER", "REVIEWER"]
    offset = (session_number - 1) % 3
    result = []
    for i, member in enumerate(members):
        role_index = (i - offset) % 3
        result.append({**member, "role": roles[role_index]})
    return result


def assign_initial_group_roles(members_sorted_by_mastery: list) -> list:
    """Assign initial roles: highest=EXPLAINER, middle=SOLVER, lowest=REVIEWER."""
    roles = ["EXPLAINER", "SOLVER", "REVIEWER"]
    return [
        {**m, "role": roles[i]} for i, m in enumerate(members_sorted_by_mastery[:3])
    ]
