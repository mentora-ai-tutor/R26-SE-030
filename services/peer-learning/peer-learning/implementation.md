# Peer Learning Backend Implementation Summary

This document summarizes the current state of the Mentora Peer Learning service, focusing on the implemented grouping algorithms and the overall architectural components completed up to now.

## Grouping Algorithms

### 1. Basic Rule-Based Pairing Algorithm
**Location:** `backend/services/pairing_service.py` -> `start_pairing_for_student`
- **Purpose:** On-demand matching of a learner to a teacher for their weakest topic.
- **Logic:** 
  1. Identifies the learner's current weakest topic (with `FUNDAMENTAL_GAP` prioritized).
  2. Queries the MongoDB `students` collection to find a student who is strong in this topic (`mastery_level`), has `can_teach_others` flagged as true, is not currently in an active session, and is not the learner themselves.
  3. Immediately forms a Pair Session (`PS-xxxx`) with the returned teacher.

### 2. Hungarian Algorithm (Optimal Bipartite Matching)
**Location:** `backend/services/pairing_service.py` -> `match_students_using_hungarian`
- **Purpose:** Batch matching of multiple learners and teachers to globally optimize compatibility and maximize the total number of quality matches.
- **Logic:**
  1. Extracts a pool of learners (based on their primary gaps) and teachers (based on their teachable strengths).
  2. Calculates a **Compatibility Score** between any learner-teacher pair using `_compatibility_score`. Score favors when the teacher's strength topic matches the learner's gap topic, adding bonuses for `advanced` mastery levels and heavily prioritizing `FUNDAMENTAL_GAP` learners.
  3. Constructs a cost matrix (where `cost = max_cost - compatibility_score`).
  4. Runs the Hungarian matching algorithm `_hungarian_algorithm(cost_matrix)` to find an optimal set of assignments with minimal matching cost.

### 3. Trigger-based Group Session Algorithm
**Location:** `backend/services/group_service.py` -> `trigger_group_session`
- **Purpose:** Transitions students who have improved in a 1-on-1 pairing into a 3-person peer learning group.
- **Logic:**
  1. Triggered when a student successfully achieves a `>= 90%` score in a Pair Session and enters the `improved` pool for a topic.
  2. The system queries the `topic_pools` collection to check if $\ge 3$ students are now in the `improved` pool for the same topic.
  3. If true, randomly picks 3 students from this pool.
  4. Assigns three specific roles randomly: `explainer`, `solver`, and `reviewer`.
  5. Randomly selects a session format: `coding`, `debugging`, or `mini_project`.
  6. Removes the three students from the `improved` pool and inserts them into a Group Session (`GS-xxx`) backed by an LLM-generated collaborative problem matching the topic and session format.

---

## Everything Else Done Up To Now

### Import & State Management
- **`import_service.py`**: Integrates with the Knowledge Analysis Agent by ingesting student mastery profiles. It automatically sorts weaknesses to place `FUNDAMENTAL_GAP` first and initializes the student in MongoDB.
- **Topic Pools**: Implements a transition system (`improved` and `verified` pools) to track student mastery progression out of individual learning into peer review.

### Real-Time Interaction (WebSockets)
- **`routers/sessions.py`**: Complex WebSocket-based routing logic for real-time interaction.
  - **Pair Flow:** Features `run_learner_flow` managing LLM timeouts, step-by-step hinting, and correct/incorrect answer submittal. Also contains `run_teacher_standby` allowing the learner to execute `ASK_TEACHER`, initiating a WebSocket handoff to the designated teacher in the session, allowing the teacher to intervene.
  - **Group Flow:** Allows the explainer, solver, and reviewer to request role-specific hints and collaborate.

### LLM Integration for Content Generation
- **`question_service.py`**: Uses local `Ollama` (running `llama3` by default) to dynamically generate adaptive questions based on the exact misconceptions listed in a learner's mastery profile. Provides hints scaling from vague to direct answers.
- **`question_service.py` (Evaluate):** Uses LLM to check natural language and coding answers provided by learners to automatically deduce partial credit and immediate feedback.
- **`group_service.py` (Generate Group Problem):** LLM-generated bespoke 3-man tasks including `explainer_guide`, `solver_starter` and `reviewer_checklist` targeting the specific subject to solve.

### Performance and Next-Step Routing
- **`performance_service.py`**: Mathematical scoring module: `score = base_accuracy - (Hints * 5 + HelpRequests * 10)`. Employs automatic thresholds:
  - `>= 90%`: `MASTERED` -> Promotes to `improved` topic pool. Move to next weakness.
  - `< 50%`: `REGROUP` -> Penalizes current teacher tracking (preventing them from teaching this topic safely again), and cancels the pairing.
  - `Moderate`: `CONTINUE`.
