# N8N Workflow Integration - API Reference

## Overview

The LMG Service communicates with the N8N Agentic AI Workflow via webhooks to trigger learning material generation.

## N8N Workflow: MENTORA V17 Agentic AI

### Configuration

Set these environment variables to match your n8n setup:

```env
N8N_BASE_URL=http://localhost:5678
N8N_WEBHOOK_LEARNER_PROFILE=http://localhost:5678/webhook/learner-profile
N8N_WEBHOOK_GET_MATERIALS=http://localhost:5678/webhook/materials
N8N_TIMEOUT_MS=600000
```

## Webhook Endpoints

### 1. POST `/webhook/learner-profile` — Trigger Material Generation

**Purpose:** Receives learner mastery profile and triggers the full agentic AI pipeline.

**Request Body:**
```json
{
  "student_id": "STU-2026-0428",
  "analysis_timestamp": "2026-04-28T10:00:00.000Z",
  "mastery_profile": {
    "overall_mastery_score": 45,
    "knowledge_gaps": [
      {
        "topic": "Recursion",
        "topic_id": "java-recursion-001",
        "gap_type": "FUNDAMENTAL_GAP",
        "misconceptions": [
          "Thinks the base case is optional",
          "Confuses stack frame with heap allocation"
        ],
        "observed_error_patterns": {
          "missing_base_case": 8,
          "infinite_recursion": 5
        },
        "evidence_summary": "Student scored 18/60 on Recursion quiz",
        "prerequisite_topics": ["Methods and return values"],
        "related_topics": ["Binary search", "Tree traversal"]
      }
    ],
    "strengths": ["Basic syntax understanding"]
  },
  "recommendations": { "priority": "high" },
  "data_sources": { "quiz_results": "2026-04-28" }
}
```

**Success Response (200):**
```json
{
  "status": "success",
  "message": "Learning materials generated successfully (Agentic AI V17)",
  "material_id": "STU-2026-0428_java-recursion-001_1776269325449",
  "student_id": "STU-2026-0428",
  "topic": "Recursion",
  "agentic_summary": {
    "quality_score": 90,
    "validation_score": 100,
    "overall_score": 95,
    "agent_decision": "ACCEPT",
    "retries_used": 0,
    "patches_applied": false
  },
  "generated_at": "2026-04-15T16:08:45.449Z",
  "needs_review": true
}
```

**Error Response (500):**
```json
{
  "status": "error",
  "message": "Material generation failed",
  "error_id": "err_1776269325449",
  "details": "Error description"
}
```

### 2. GET `/webhook/materials/:studentId` — Fetch Materials

**Purpose:** Retrieves all learning materials for a student from MongoDB.

**Response:**
```json
[
  {
    "structured_material": {
      "material_id": "STU-2026-0428_java-recursion-001_1776269325449",
      "student_id": "STU-2026-0428",
      "topic": "Recursion",
      "topic_id": "java-recursion-001",
      "gap_type": "FUNDAMENTAL_GAP",
      "generated_at": "2026-04-15T16:08:45.449Z",
      "lesson": { ... },
      "assessment": { ... }
    }
  }
]
```

## Workflow Pipeline (V17 Agentic AI)

```
Learner Profile Webhook
        │
        ▼
┌───────────────────────┐
│  Schema Validator     │ ← Validates required fields
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Profile Processing   │ ← Maps interventions, content types
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Split by Knowledge Gap│ ← Parallel processing per gap
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Prompt Construction  │ ← Builds LLM + SLM prompts
└───────────────────────┘
        │
        ├──────────────────┐
        ▼                  ▼
┌───────────────┐   ┌───────────────┐
│ LLM (Gemma4)  │   │ SLM (Mistral) │
│ Lesson +      │   │ Quiz +        │
│ Tutorial      │   │ Assessment    │
└───────────────┘   └───────────────┘
        │                  │
        ▼                  ▼
┌───────────────┐   ┌───────────────┐
│ Parse LLM     │   │ Parse SLM     │
│ Response      │   │ Response      │
└───────────────┘   └───────────────┘
        │                  │
        ▼                  ▼
┌───────────────┐   ┌───────────────┐
│ 🤖 Quality    │   │ 🤖 Content    │
│ Review Agent  │   │ Validation    │
│ (Accept/Re    │   │ Agent         │
│  try/Patch)   │   │ (Auto-patch)  │
└───────────────┘   └───────────────┘
        │                  │
        │                  │
        └────────┬─────────┘
                 ▼
        ┌─────────────────┐
        │ Merge LLM+SLM   │
        └─────────────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ Content         │
        │ Structuring     │
        └─────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌───────────────┐  ┌───────────────┐
│ MongoDB       │  │ Model         │
│ learning_     │  │ Comparison    │
│ materials     │  │ Logs          │
└───────────────┘  └───────────────┘
        │
        ▼
   HTTP Response
```

## Agentic AI Components

### Quality Review Agent
- **Purpose:** Evaluates LLM output quality (0-100 score)
- **10 Quality Checks:**
  - has_title, has_introduction, has_concept, has_syntax
  - has_examples, has_steps, has_debug_exercise
  - has_mistakes, no_parse_fail, no_empty_codes
- **Decisions:**
  - `ACCEPT` (≥80 score)
  - `RETRY` (<80 score, max 2 retries)
  - `ACCEPT_WITH_PATCH` (max retries exhausted)

### Content Validation Agent
- **Purpose:** Validates SLM (assessment) output
- **7 Validation Checks:**
  - has_quiz, has_quiz_explanations, has_concept_summary
  - has_practice, has_starter_code, has_self_check
  - no_parse_fail
- **Auto-patches missing content:**
  - Quiz questions
  - Concept summary
  - Practice challenge
  - Self-check items

## Ollama Models Used

| Model | Purpose | Endpoint |
|-------|---------|----------|
| `gemma4:latest` | LLM - Lesson generation | `http://192.168.1.102:11434/api/chat` |
| `mistral:latest` | SLM - Assessment generation | `http://192.168.1.102:11434/api/chat` |

## MongoDB Collections Written by N8N

### `learning_materials`
```javascript
{
  structured_material: {
    material_id: "STU-2026-0428_java-recursion-001_...",
    student_id: "STU-2026-0428",
    topic: "Recursion",
    gap_type: "FUNDAMENTAL_GAP",
    lesson: { page_title, introduction, concept_explained, ... },
    assessment: { quiz, concept_summary, practice_challenge, ... },
    agentic_metadata: { quality_review_agent, content_validation_agent },
    quality_flags: { needs_review, overall_quality_score, ... }
  }
}
```

### `model_comparison_logs`
```javascript
{
  log_id: "comp_STU-2026-0428_java-recursion-001_...",
  student_id: "STU-2026-0428",
  llm_model: "gemma4:latest",
  slm_model: "mistral:latest",
  agent_quality_score: 90,
  content_validation_score: 100,
  agent_retry_count: 0,
  llm_parse_error: null,
  slm_parse_error: null
}
```

## Gap Type to Difficulty Mapping

| Gap Type | Difficulty Level |
|----------|-----------------|
| `FUNDAMENTAL_GAP` | beginner |
| `PARTIAL_GAP` | intermediate |
| `SURFACE_GAP` | intermediate |

## Testing the Integration

### 1. Start n8n
```bash
cd /path/to/n8n-workflows
npx n8n start
```

### 2. Activate the workflow
- Open http://localhost:5678
- Open "MENTORA V17 Agentic AI" workflow
- Click "Activate" toggle

### 3. Test the webhook
```bash
curl -X POST http://localhost:5678/webhook/learner-profile \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "STU-2026-0428",
    "mastery_profile": {
      "overall_mastery_score": 45,
      "knowledge_gaps": [{
        "topic": "Recursion",
        "topic_id": "java-recursion-001",
        "gap_type": "FUNDAMENTAL_GAP",
        "misconceptions": ["Thinks the base case is optional"]
      }]
    }
  }'
```

### 4. Check MongoDB
```javascript
db.learning_materials.find({}).sort({ "structured_material.generated_at": -1 }).limit(1)
```