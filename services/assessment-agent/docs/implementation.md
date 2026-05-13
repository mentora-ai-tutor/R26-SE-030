# Implementation Details - Mentora AME Agent

This document outlines the core algorithms and implementations within the Assessment and Mastery Evaluation (AME) Agent.

## Grouping & Analytics Algorithms

The AME Agent leverages complex MongoDB aggregation pipelines and JavaScript-based logic to "group" and analyze learner performance.

### 1. Mastery Distribution Algorithm
- **Purpose**: Groups learners into performance tiers to visualize the cohort's overall progress.
- **Logic**: Iterates through the latest session updates and buckets the `current_topic_mastery` into five tiers:
  - `0-20%`: Critical Gaps
  - `21-40%`: Significant Gaps
  - `41-60%`: Developing
  - `61-84%`: Proficient
  - `85-100%`: Mastered

### 2. Topic Performance Grouping
- **Purpose**: Analyzes which topics are hardest for learners.
- **Logic**: Groups `ame_session_updates` by topic. It calculates:
  - `avg_mastery`: Mean score per topic.
  - `mastery_rate`: Percentage of learners achieving >85%.
  - `avg_questions_needed`: Number of questions asked before completion/mastery.
  - `remediation_count`: Frequency of remediation triggered for the topic.

### 3. Question Statistics & Taxonomy
- **Purpose**: Groups the question bank by metadata for balanced assessment generation.
- **Logic**: Uses MongoDB `$group` stages to categorize questions by:
  - `question_type`: (e.g., MCQ, Code Analysis)
  - `difficulty`: (Easy, Medium, Hard)
  - Topic Subject matter area.
  - `blooms_level`: Cognitive complexity (1-6).

### 4. Cohort Mastery Heatmap
- **Purpose**: Provides a high-level view of mastery across all topics for the entire cohort.
- **Logic**: Collects all `topic_scores` from session updates, groups them by topic name, and calculates the average mastery for every subject area in the curriculum.

### 5. Remediation Success Algorithm
- **Purpose**: Evaluates the effectiveness of remediation loops.
- **Logic**: Groups updates by `session_id` where `remediation_entered` is true. It tracks:
  - Success rate (Percentage of learners who exited remediation vs. those still stuck).
  - Improvement delta (Mastery before vs. after remediation).

### 6. Misconception Frequency Analysis
- **Purpose**: Groups identified misconceptions to inform curriculum adjustments.
- **Logic**: Parses `feedback_reports`, extracts the `misconceptions_to_address` array, and performs a frequency count to identify the most common conceptual hurdles.

---

## Core Implementations Done Up To Now

### 1. Session Management
- **Start Session**: Initializes a new AME session by sending the learner's `mastery_profile` and `knowledge_gaps` to an n8n workflow.
- **Submit Answer**: Handles real-time answer submission, routing the data through n8n for LLM-based evaluation and state updates.
- **State Recovery**: Retrieves the latest session state from `ame_session_updates` to allow learners to resume assessments.

### 2. n8n Integration Layer
- **Webhook Bridge**: A dedicated `n8nService` that manages long-timeout requests to the n8n agentic workflows.
- **Payload Formatting**: Ensures consistency between the Backend DB schema and the expected n8n input schemas.

### 3. Comprehensive Analytics Service
- **MongoService**: A centralized service containing over 20 specialized aggregation queries for the Admin/Teacher dashboard (currently implemented but awaiting route exposure).
- **Dashboard Stats**: Real-time calculation of active sessions, total questions generated, and average cohort mastery.

### 4. Security & Middleware
- **JWT Authentication**: Secure route protection with learner identity injection (`req.user.student_id`).
- **Global Error Handling**: Standardized JSON error responses for all API failures.
