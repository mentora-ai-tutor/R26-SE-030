# n8n Workflow API Documentation - Assessment Agent

This document outlines the webhook endpoints provided by the n8n agentic workflow for the Assessment and Mastery Evaluation (AME) system.

## Base URL
All endpoints are relative to the n8n webhook base URL:
`http://<n8n-instance>/webhook/`

---

## Endpoints

### 1. POST `ame/start-session` — Initialize Assessment

**Purpose:** Starts a new adaptive assessment session for a student based on their mastery profile.

**Request Body:**
```json
{
  "student_id": "STU-123",
  "mastery_profile": {
    "overall_mastery_score": 65,
    "knowledge_gaps": [
      {
        "topic": "Recursion",
        "gap_type": "FUNDAMENTAL_GAP",
        "misconceptions": ["Infinite recursion", "Base case missing"],
        "observed_error_patterns": {
          "sandbox": ["StackOverflowError"]
        }
      }
    ]
  },
  "recommendations": {
    "priority_order": ["Recursion"]
  }
}
```

**Workflow Logic:**
- Validates the mastery profile.
- Sorts topics by priority.
- Selects the first topic and determines starting difficulty (Easy for `FUNDAMENTAL_GAP`, Medium for `PARTIAL_GAP`).
- Generates the first adaptive question using Ollama (Gemma4).
- Saves the session state to MongoDB (`ame_sessions`).

**Success Response (200):**
```json
{
  "success": true,
  "session_id": "SESSION_1715587200000_STU-123",
  "learner_id": "STU-123",
  "message": "Session started. Here is your first question.",
  "question": {
    "question_id": "Q_1715587200000_abc123",
    "question_text": "What is the primary purpose of a base case in recursion?",
    "question_type": "mcq",
    "options": {
      "A": "To call the function again",
      "B": "To stop the recursive calls",
      "C": "To increase the stack size",
      "D": "To handle multiple parameters"
    },
    "correct_answer": "B",
    "evaluation_criteria": "The learner must identify that the base case prevents infinite recursion."
  },
  "session_info": {
    "topic": "Recursion",
    "difficulty": "easy",
    "question_number": 1,
    "mastery_score": 0,
    "mastery_threshold": 85,
    "topics_remaining": 1
  }
}
```

---

### 2. POST `ame/submit-answer` — Submit and Evaluate Answer

**Purpose:** Evaluates a learner's answer, updates mastery scores, and provides the next adaptive question.

**Request Body:**
```json
{
  "session_id": "SESSION_1715587200000_STU-123",
  "learner_id": "STU-123",
  "question_id": "Q_1715587200000_abc123",
  "answer": "B"
}
```

**Workflow Logic:**
- Fetches session state and question details from MongoDB.
- Evaluates the answer (Direct comparison for MCQ, LLM-based for open-ended).
- Calculates new mastery score using weighted difficulty and rubric scores.
- Determines next step:
  - **Remediation**: Triggered if mastery is low after several questions.
  - **Topic Mastery**: Moves to next topic if threshold (85%) is met.
  - **Next Question**: Adjusts Bloom's level based on consecutive correct/wrong answers.
- Generates a personalized feedback report if the session is complete.

**Success Response (200):**
```json
{
  "success": true,
  "session_id": "SESSION_1715587200000_STU-123",
  "evaluation": {
    "is_correct": true,
    "correctness_score": 100,
    "evaluation_summary": "Correct answer selected."
  },
  "feedback": {
    "immediate_feedback": "Well done!",
    "concept_explanation": "Recursion requires a base case to terminate execution...",
    "encouragement": "Great start, keep it up!"
  },
  "mastery_update": {
    "topic": "Recursion",
    "previous_mastery": 0,
    "current_mastery": 15,
    "topic_mastered": false,
    "session_complete": false
  },
  "next_question": {
    "question_id": "Q_1715587205000_xyz789",
    "question_text": "Complete this recursive function to calculate factorial...",
    "question_type": "code_completion",
    "difficulty": "medium",
    "code_snippet": "public int fact(int n) { if(n <= 1) return 1; return n * [?] ; }"
  },
  "session_progress": {
    "question_number": 2,
    "current_topic": "Recursion",
    "current_difficulty": "medium",
    "topics_remaining": 0,
    "overall_accuracy": 100
  }
}
```

---

## Database Collections Used
- `ame_sessions`: Stores initial session configuration.
- `ame_questions`: Bank of all generated questions.
- `ame_answers`: History of learner attempts and evaluations.
- `ame_session_updates`: Latest state of each session (mastery, progress).
- `ame_feedback_reports`: Final reports generated upon session completion.
