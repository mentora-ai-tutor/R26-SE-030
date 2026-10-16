# INDIVIDUAL THESIS

*[Note: the front matter below was regenerated after a file-handling error
destroyed the original. Chapters 1 to 8 are current. Please verify the front
matter against your own copy before submission.]*

## Design, Implementation and Evaluation of an Agentic Peer-Learning Service for Evidence-Based Java Programming Instruction

**[Student full name]**
**([Student ID])**

Individual component: Peer-Learning Service - Java Multi-Agent Pedagogy Platform
Group ID: **[Group ID]**

Report submitted in partial fulfilment of the requirements for the
**Bachelor of Information Technology (Honours) / Bachelor of Information Technology**
**Computer Networking and Technology / Software Engineering / Data Science [SELECT]**

Department of **[Department name]**
Sri Lanka Institute of Information Technology
Sri Lanka
**[Month Year]**

---

## DECLARATION AND SUPERVISOR CERTIFICATION

### Candidate declaration

I declare that this thesis is my own work, that all sources of information have
been properly acknowledged, and that the work has not been submitted for another
qualification at this or any other institution. Where the work of others has
been used, it has been clearly identified and cited.

I confirm that this thesis contains no material that infringes the copyright of
any other person, and that all third-party material used has been properly
attributed.

### Academic integrity and AI disclosure

I have disclosed all use of generative AI and other automated tools in accordance
with the module policy. I remain responsible for the accuracy, originality,
citations, code, data, analyses and conclusions in this thesis. A full disclosure
of AI-assisted workflows appears in Appendix B.

| Student name | Student ID | Signature | Date |
|---|---|---|---|
| [Full name] | [Student ID] | ______________________ | ____________ |

### Supervisor certification

The above candidate carried out this research for the bachelor's degree thesis
under my supervision.

| Role and name | Signature | Date |
|---|---|---|
| Supervisor: [Name] | | |
| Co-supervisor: [Name] | | |

---

## ABSTRACT

Peer-assisted learning is among the best-evidenced interventions in higher
education, yet its implementation in practice is typically unstructured:
students are paired without regard to complementary expertise, sessions have no
diagnosed focus, and progression is not governed by evidence. This thesis
addresses a specific gap in agentic-AI-driven programming education: existing
large-language-model (LLM) tutoring systems individualise *content* but produce
no verifiable evidence that the learner can actually construct, repair and
refactor code, and they systematically remove the peer-explanation step that
underpins the largest measured active-learning gains. The individual contribution
reported here is the **peer-learning service** of the Mentora platform, a
FastAPI microservice that converts an externally computed Java mastery analysis
into gap-targeted evidence of learning. The service implements eight specialised
agents - diagnostic task generation, deterministic Java validation, AI grading,
content recommendation, complementary peer matching, real-time collaboration,
discussion moderation and support - over a server-authoritative state machine in
which a task advances only when native `javac` compilation and criterion-based
LLM grading both succeed. The evaluation protocol is specified as a design-science
artefact using a mixed-methods design comprising a 120-submission Java corpus to
be expert-marked for grader agreement (precision, recall, Cohen's kappa), a
within-cohort pre/post design measuring normalised learning gain in the targeted
subskill, and a comparison of complementary against non-complementary pairing,
supplemented by a system-usability instrument and ISO/IEC 25010 quality
measurement. The service comprises 4,978 lines of Python across 38 modules and
exposes 25 REST and 2 WebSocket endpoints over 13 indexed MongoDB collections,
with deterministic degraded-mode fallbacks for every LLM dependency. The
contribution claimed in this thesis is the design and its artefact evidence; the
empirical evaluation is specified but not yet executed, and no empirical results
are claimed here. The threats to validity and the conditions under which the
design claims would be falsified are reported in full.

**Keywords:** peer-assisted learning, large language models, formative
assessment, Java programming education, agentic AI, real-time collaborative
coding

---

## ACKNOWLEDGEMENTS

I would like to express my sincere gratitude to **[Supervisor name]** for the
guidance, critical feedback and patience throughout this project, which shaped
Chapter 3 considerably. I am grateful to the **Department of [Department name]**
at the Sri Lanka Institute of Information Technology for the academic
environment, laboratory access and the teaching that made this work possible.

I am grateful to **[team or group members, if any]** for their collaboration
within the wider Mentora project, particularly for the interface contracts
described in Section 5.3. I thank the Java teaching laboratory instructors for
their willingness to discuss the pedagogical basis of the task sequence.

Finally, I acknowledge the ecosystems on which this work depends - FastAPI,
Pydantic, PyMongo, LangChain, LangGraph, python-socketio and NumPy - and the
authors of the Java documentation corpus used to ground the retrieval component.

---

## TABLE OF CONTENTS
*[Guidance — delete before submission: In Microsoft Word, press Ctrl+A and then
F9 to update the table of contents, all lists, cross-references and page numbers
before submission. The chapter and section numbering below must match the
headings used in the body of this document.]*

1 INTRODUCTION
 1.1 Overall project context
 1.2 Individual component context
 1.3 Problem statement
 1.4 Research gap
 1.5 Aim and objectives
 1.6 Research questions or hypotheses
 1.7 Scope limitations and assumptions
 1.8 Individual contribution
 1.9 Thesis structure
2 LITERATURE REVIEW AND RELATED WORK
 2.1 Review method and scope
 2.2 Domain and theoretical foundations
 2.3 Related research
 2.4 Existing systems products and techniques
 2.5 Gap synthesis and conceptual framework
3 RESEARCH METHODOLOGY
 3.1 Research design
 3.2 Data participants or study materials
 3.3 Experimental or study procedure
 3.4 Measures and evaluation metrics
 3.5 Data analysis
 3.6 Ethics privacy security and responsible AI
 3.7 Reproducibility and research artefacts
4 PRODUCT AND SOLUTION DESIGN
 4.1 Requirements
 4.2 Component architecture within the complete solution
 4.3 Design alternatives and decisions
 4.4 Detailed design
 4.5 Standards and professional practice
 4.6 Design traceability
 4.7 Interface and API design
 4.8 Mapping objectives to design sections
 4.9 Summary of the design decisions
5 IMPLEMENTATION INTEGRATION AND TESTING
 5.1 Development environment and technology stack
 5.2 Component implementation
 5.3 Integration with the other components
 5.4 Verification and software testing
 5.5 Deployment and operation
6 RESULTS AND VALIDATION
 6.1 Research results
 6.2 Product and technical results
 6.3 User or stakeholder validation
 6.4 Integration results
 6.5 Summary of findings
7 DISCUSSION
 7.1 Interpretation of findings
 7.2 Comparison with literature baselines and existing solutions
 7.3 Research contribution
 7.4 Product contribution
 7.5 Limitations and threats to validity
 7.6 Implications
8 CONCLUSION AND FUTURE DIRECTIONS
 8.1 Conclusion
 8.2 Achievement of objectives
 8.3 Individual research and product contributions
 8.4 Future directions
REFERENCES
GLOSSARY
APPENDICES
 Appendix A Research instruments and extended results
 Appendix B Academic integrity and AI use disclosure

---

## LIST OF FIGURES

*[Guidance — delete before submission: Use Word's Insert Caption command with
the label Figure. Number figures by chapter and cite every figure in the text.
In this Markdown source, figure captions are given as bold lines directly beneath
the ASCII/mermaid block that the figure replaces.]*

**Figure 1.1** Mentora system context and the boundary of the individual
component
**Figure 1.2** Artefact metrics for the individual component, used throughout
this thesis
**Figure 2.1** Conceptual framework of the peer-learning service derived from the
gap synthesis
**Figure 3.1** Design Science Research process adapted from Peffers et al. [7]
**Figure 3.2** Evaluation procedure timeline
**Figure 3.3** Comparison-group allocation and data-collection flow
**Figure 4.1** Layered architecture of the peer-learning service
**Figure 4.2** Task-type sequence and Bloom's revised taxonomy mapping
**Figure 4.3** Diagnostic session and collaboration-room state machine
**Figure 4.4** Two-gate evaluation pipeline (compilation gate and grading gate)
**Figure 4.5** Complementarity-based peer-matching decision flow
**Figure 4.6** Real-time collaboration message exchange
**Figure 4.7** Degraded-mode decision flow for LLM-dependent operations
**Figure 5.1** Intended deployment topology, showing the component's isolation from the
orchestrated monorepo

---

## LIST OF TABLES

**Table 1.1** Individual objectives mapped to deliverables
**Table 2.1** Literature review search strategy
**Table 2.2** Comparison of related systems against the component's capabilities
**Table 2.3** Gap synthesis and the design requirement it generates
**Table 3.1** Study participants and sampling frame
**Table 3.2** Instruments used in the evaluation
**Table 3.3** Research questions mapped to measures, instruments and analyses
**Table 3.4** Research artefacts and their locations
**Table 4.1** Functional requirements
**Table 4.2** Non-functional requirements
**Table 4.3** MongoDB collections, indexes and purpose
**Table 4.4** Design alternatives considered and decisions taken
**Table 4.5** Diagnostic task types, cognitive demand and intended evidence
**Table 4.6** Peer matching filters, with the threat each excludes
**Table 4.7** Collaboration WebSocket message vocabulary
**Table 4.8** Degraded modes: operation, trigger, behaviour and consequence
**Table 4.9** REST endpoints grouped by domain
**Table 4.10** WebSocket and Socket.IO endpoints
**Table 4.11** Standards and professional practice conformance
**Table 4.12** Requirement-to-implementation traceability
**Table 4.13** Objective-to-section mapping
**Table 4.14** Design decision summary: what was chosen, what it enables, what it costs
**Table 5.1** Technology stack and versions
**Table 5.2** Module inventory and responsibility
**Table 5.3** Endpoint catalogue of the registered application
**Table 5.4** Peer-matching filters as implemented and the failure mode each excludes
**Table 5.5** WebSocket message vocabulary observed in the implementation
**Table 5.6** Degraded modes observed in the implementation
**Table 5.7** Integration status with the other components
**Table 5.8** Test inventory and current status
**Table 5.9** Verification coverage against the design's critical logic
**Table 5.10** Deployment and configuration defects found in the reference commit
**Table 6.1** Status of each research question and the evidence required to answer it
**Table 6.2** Learning gain results by condition
**Table 6.3** Grader agreement results against expert markers
**Table 6.4** Measured product characteristics
**Table 6.5** Stakeholder validation status
**Table 6.6** Integration results
**Table 6.7** Summary of findings against research questions and objectives
**Table 7.1** Comparative analysis against literature and product baselines
**Table 7.2** Limitations and threats to validity
**Table 8.1** Achievement of objectives

---

## LIST OF ABBREVIATIONS

*[Guidance — delete before submission: List abbreviations alphabetically. Define
each abbreviation at first use in the main text even when it appears here.]*

| Abbreviation | Meaning |
|---|---|
| AC | Acceptance Criteria |
| API | Application Programming Interface |
| ASGI | Asynchronous Server Gateway Interface |
| CI | Continuous Integration |
| CI/CD | Continuous Integration / Continuous Delivery |
| CRUD | Create, Read, Update, Delete |
| DSR | Design Science Research |
| FASTER | Feedback, Assistance, Scaffolding, Transparency, Engagement, Reflection |
| GDPR | General Data Protection Regulation |
| GHCR | GitHub Container Registry |
| ICAP | Interactive, Constructive, Active, Passive |
| ICE | Instrumented Collaborative Editing |
| ITER | Iterative Testing, Evaluation and Refinement |
| JDK | Java Development Kit |
| JWT | JSON Web Token |
| LMG | Learning Material Generator |
| LLM | Large Language Model |
| LOC | Lines of Code |
| MCQ | Multiple-Choice Question |
| MoSCoW | Must, Should, Could, Won't (requirement prioritisation) |
| NFR | Non-Functional Requirement |
| OLS | Ordinary Least Squares |
| REST | Representational State Transfer |
| RAG | Retrieval-Augmented Generation |
| RQ | Research Question |
| SDK | Software Development Kit |
| SRS | Software Requirements Specification |
| SWE | Software Engineering |
| SWEBOK | Guide to the Software Engineering Body of Knowledge |
| TA | Teaching Assistant |
| WCAG | Web Content Accessibility Guidelines |
| WS | WebSocket |

---
---

# 1 INTRODUCTION

## 1.1 Overall project context

The project documented in this group report, identified internally as
**R26-SE-030** and titled *Agentic AI-Driven Multi-Agent Tutoring System for
Personalised Learning and Mastery Assessment*, addresses a problem that sits at
the intersection of two persistent shortcomings in undergraduate computer science
education. The first is diagnostic: institutions know, in general terms, which
students are struggling, yet the evidence supporting that judgement is usually
indirect — quiz marks, submission counts, repository activity — and is rarely
resolved to the granularity of an individual *subskill* such as
`try-catch-finally` semantics or loop boundary conditions. The second is remedial: even
where a gap is known, the mechanisms available to close it are static. A video,
a reference slide and a search engine are all one-directional; none of them
requires the learner to produce, defend or repair code in front of another
person. The pedagogical literature is unambiguous that peer-mediated
explanation and problem-solving produce substantially larger learning gains than
passive instruction [1], [2], and that active-learning formats substantially
reduce failure rates in STEM cohorts [3]. Practising this at scale requires
machinery, and that machinery is what this project builds.

The group's answer is a multi-agent architecture in which specialised
artificial-intelligence agents, each with a narrow and auditable
responsibility, are composed into a single pedagogical pipeline: analyse a
learner's work, decide what is missing, produce material and practice targeted
at that specific deficiency, verify whether practice actually helped, and route
the learner to human or artificial assistance accordingly. The system is
realised as a monorepository of cooperating services, illustrated in
**Figure 1.1**.

```
             +-----------------------------------------------------------------+
             |                        Mentora platform                        |
             |                                                                 |
   +---------+---------+   JWT    +------------------+   analysis    +--------+---------+
   |                   |--------->|                  |<-------------|                  |
   |    user service   |          |   knowledge      |  document     |    AI engine    |
   |  (authentication, |          |   analysis       |               | (code execution |
   |   profiles, LMS)  |          |  (mastery gaps,  |               |  sandbox, LLM   |
   |   port 3001       |          |   strengths)     |               |  feedback)      |
   |                   |          +--------+---------+               |   port 5010     |
   +---------+---------+                   |                         +------------------+
             |                             | analysis document
             |                             v
             |                   +---------+-------------------+
             |                   |     peer-learning service    |
             |                   |  >>> THIS INDIVIDUAL        |
             |                   |      COMPONENT <<<          |
             |                   |  diagnostics, peer matching, |
             |                   |  collaborative rooms, RAG,  |
             |                   |  moderation   port 8000     |
             |                   +---------+-------------------+
             |                             |
             |                             | learning material, quiz items
             v                             v
   +---------+---------------------------------------------------------------+
   |                web front end / student dashboard                        |
   +-------------------------------------------------------------------------+
```

**Figure 1.1** Mentora system context and the boundary of the individual
component. The component is the *peer-learning service*: it consumes an
authenticated identity and a mastery-analysis document and produces
gap-targeted practice, peer pairing, collaborative sessions and validated
evidence of learning.

Within that architecture the team divided the work into four individually
owned components, developed on separate branches and merged into the
monorepository: the **user service** (authentication, profiles, session
bookkeeping), the **knowledge analysis service** (the component that produces
the mastery profile — knowledge gaps, weak subskills, strengths, observed error
patterns and suggested interventions), the **AI engine** (a code-execution
sandbox and feedback generator), and the **peer-learning service** (this thesis).
The `README.md` at the repository root names the project and its aim; the CI
workflow builds and publishes the AI engine, user service and learning-material
generator to GitHub Container Registry, and `docker-compose.yml` wires the user
service, learning-material generator and AI engine into a running topology with
the AI engine configured against an Ollama endpoint.

The decision to split the system along *pedagogical function* rather than along
*technical layer* is the first substantive design decision of the project and is
inherited by this thesis. Because the knowledge-analysis component owns the
diagnosis and this component owns the intervention, the interface between them
is a single versioned document schema, `kaa-lmg-v1.0`, rather than a shared
database schema. That is why Section 3.7 and Section 5.3 devote deliberate
attention to the *contract* between the components rather than to internal data
structures, and why Section 7.5 treats contract drift as an identified threat to
validity.

## 1.2 Individual component context

The individual component reported in this thesis is the **peer-learning service**
of the Mentora platform — an agentic backend whose purpose is to convert a
*declaration* of what a student is weak at into *evidence* of what the student
can actually do. It is a Python 3.11 FastAPI application registered under the
title *Java Multi-Agent Pedagogy Platform*, API version 1.2.0, implemented in
`app/main.py` and organised as a layered modular monolith.

Its scope is unusually broad for a single component, and this breadth is a
deliberate consequence of the pedagogical argument in Chapter 2: a diagnosis is
worthless unless it is followed by a targeted task, a task is worthless unless
its completion can be verified, verification is worthless unless the learner and
the peer both observe it in a shared state, and the shared state is worthless
unless it can be interrogated afterwards. The component therefore spans eight
functional concerns, each realised as an agent or service module:

1. **Mastery-analysis ingestion** — a JWT-authenticated import endpoint that
   validates and stores the knowledge-analysis document and enforces that the
   body identity matches the token identity (`app/api/student_routes.py`).
2. **Diagnostic task generation** — an agent that produces a fixed sequence of
   seven *code-writing* tasks, one per cognitive demand type, all targeting the
   same weak subskill (`app/agents/student_agent.py`).
3. **Deterministic Java validation** — an agent that compiles submitted source
   with the platform's own `javac` and degrades to a strict structural checker
   when no JDK is present (`app/agents/assessment_agent.py`).
4. **AI grading and feedback** — a second gate that judges the submission against
   the stored task description and evaluation criteria, returning pass/fail
   with specific feedback and a non-solution hint (`app/agents/student_agent.py`).
5. **Complementary peer matching** — a deterministic matcher that pairs a
   learner whose analysis reports a gap on a topic with a student whose analysis
   reports a *strength* on the same topic, subject to availability, session
   conflict and repeated-teaching constraints (`app/api/peer_routes.py`).
6. **Real-time collaborative rooms** — a WebSocket code editor with live cursor
   presence, a shared whiteboard, room chat, server-authoritative task
   progression and full state restoration on reconnect (`app/api/collab_routes.py`).
7. **Retrieval-augmented content** — a pipeline that chunks a Java documentation
   PDF, embeds it, retrieves by cosine similarity and generates a targeted study
   guide (`app/rag/`, `app/api/rag_routes.py`, `app/api/content_routes.py`).
8. **Moderation, summarisation and support** — a discussion moderator that keeps
   peer dialogue on topic and summarises it, a support agent that answers
   student questions with knowledge-gap context, and an individual quiz and
   question generator pair for solo practice (`app/api/chat_routes.py`,
   `app/agents/support_agent.py`, `app/api/individual_quiz_routes.py`,
   `app/api/question_generator_routes.py`).

**Figure 1.2** summarises the artefact's measurable extent, all figures being
directly verifiable from the source tree at the commit recorded in Section 3.7.

| Property | Value |
|---|---|
| Python modules (`app/`) | 38 files, 4,978 lines |
| Concrete agent classes | 8 (`assessment`, `student`, `support`, `moderator`, `peer matching`, `knowledge RAG`, `graph workflow`, quiz) |
| Registered routers | 8 |
| REST endpoints | 25 |
| WebSocket endpoints | 2, plus a Socket.IO channel at `/socket.io` |
| MongoDB collections with declared indexes | 13 collections, 17 index specifications |
| Diagnostic task types | 7, in fixed order |
| Persistent collaboration fields | 13 |
| Automated tests | 10 recorded node identifiers, 6 test functions in source |
| Postman collection entries | 10 |

**Figure 1.2** Artefact metrics for the individual component, used throughout
Chapters 4, 5 and 6 as the verifiable portion of the product evaluation.

Three architectural commitments distinguish this component from a conventional
LMS plugin, and each is defended in Chapter 4 and, where evidence exists,
evaluated in Chapter 6.

*The assessment is server-authoritative.* A task advances only when *both* the
compilation gate and the grading gate succeed; the client cannot skip or rewind
the sequence, and attempts to do so are answered with `TASK_LOCKED`. State
transitions are applied with a compare-and-swap filter on the current task
number and status, so a double submission cannot double-advance a learner.

*The learner is never shown the answer.* Failed submissions return specific
feedback and a hint but never a complete solution, and the content of locked
tasks is withheld from the initial-state payload, so a client cannot read ahead
by inspecting the connection handshake.

*The system degrades rather than fails.* Every LLM-dependent operation has a
deterministic local fallback, and every database operation is wrapped so that a
persistence fault degrades the affected feature rather than taking the process
down. Table 4.8 tabulates this behaviour, and Section 7.5 assesses its cost:
degraded modes preserve availability but weaken the validity of the evidence
the component exists to produce.

## 1.3 Problem statement

Mastery analysis has become cheap to compute and expensive to act upon. The
knowledge-analysis component of this project can state, with confidence and
evidence, that a given student has a *weak subskill* in Java exception handling
and a documented misconception about `finally` blocks. Nothing in that statement
has been demonstrated by the student. The gap between a declared deficiency and
a demonstrated competence is the problem this thesis attacks, and it decomposes
into four concrete, separately addressable deficiencies.

**First, multiple-choice diagnostics do not produce evidence of competence.**
Most automated diagnostics in undergraduate programming are item banks. They
measure recognition — the student can select the right answer from four
presented options — which occupies the lowest rungs of both Miller's
competence/performance hierarchy [4] and Bloom's revised taxonomy [5]. A student
who can recognise a correct `try-with-resources` statement and a student who can
write one are indistinguishable to such an instrument. Worse, item banks are
finite: a course of 120 students consumes 120 items, so items must be reused,
and reuse is detectable. The pedagogical requirement is for *generated* items
that are simultaneously targeted at the diagnosed subskill, varied enough to be
fresh, and demanding enough to be diagnostic.

**Second, LLM-generated tasks are not automatically valid instruments.** Because
an LLM can produce a plausible-looking Java exercise in milliseconds, the
obstacle has shifted from generation to *assurance*. A generated task may be
unanswerable, ambiguous, solvable in a degenerate way, or accompanied by starter
code that does not compile. Grading is harder still: a model asked whether
student code "correctly demonstrates" a concept is a *judge*, and judges are
known to be inconsistent, sensitive to presentation and vulnerable to
self-preference. If such a judge is placed between a learner and their progress
through a course, its error rate becomes an educational harm rather than a
software defect. The component must therefore combine a *deterministic* gate
that cannot be argued with — the platform's own Java compiler — with a
*probabilistic* gate, and must treat disagreement between them as data rather
than as an error.

**Third, peer learning in practice is unguided.** The standard arrangements —
pair programming in a laboratory, a "find a partner" instruction, a breakout
room — assign pairs on availability, not on complementarity. A pair of two weak
students cannot resolve a misconception; a pair of two strong students learns
nothing. Without a mechanism that reads both students' profiles and pairs them
*against* their respective gaps and strengths, the peer-Instruction literature's
central mechanism [2] is left to chance.

**Fourth, collaborative coding tools are not pedagogically governed.** Real-time
editors such as those built on operational transformation or conflict-free
replicated data types solve concurrency: two people can type in the same buffer
without corrupting it. None of them knows that Task 4 must not be attempted
until Task 3 has been passed, none of them knows which subskill the pair is
supposed to be remediating, and none of them can tell a facilitator afterwards
what happened. State is held in the client, so a refresh loses the session.
Progression is whatever the participants agree it is.

The four deficiencies compound. Generated tasks without deterministic
validation produce unreliable evidence; unreliable evidence makes guided pairing
meaningless; unguided pairing inside an ungoverned editor produces no record;
and no record means no basis for the next diagnosis. The problem is therefore
not any single feature but the **absence of a closed, evidence-bearing loop**
from diagnosis to verified remediation and back to diagnosis.

## 1.4 Research gap

The literature reviewed in Chapter 2 establishes the four deficiencies above and
leaves four gaps that this component addresses. Each gap is stated as a
discrepancy between what is known and what has been built and measured.

**Gap 1 — Pedagogically sequenced generation.** Retrieval-augmented generation
[6] and structured-output LLM APIs make it trivial to generate items on demand,
and the education literature provides a mature account of *why* items must be
sequenced from construction through repair, prediction and refactoring [5], [7].
No deployed system located by this review combines both: existing automated
programming assessment is either human-authored and fixed [8], [9] or generated
without pedagogical ordering. The gap is a generation method that is
*pedagogically constrained by construction* — a fixed type sequence the
generator must fill rather than an instruction the generator may ignore.

**Gap 2 — Complementary rather than available pairing.** Peer-instruction and
peer-assisted-learning research is extensive [2], [10], [11], and the
matching-theory literature supplies principled algorithms for pairing agents with
complementary attributes under capacity constraints [12], [13]. Educational
practice, by contrast, pairs on availability. The gap is a *profile-driven*
pairing decision that reads the same mastery-analysis document the diagnosis
draws on, so that pairing and remediation are guaranteed to concern the same
subskill.

**Gap 3 — Server-authoritative progression in collaborative editors.** The
real-time collaborative editing literature focuses on consistency, concurrency
control and network efficiency [14], [15]. It does not treat the editor as an
assessment instrument, and consequently does not address task locking, leakage
of locked content through the state payload, optimistic-concurrency task
transitions or state restoration after reconnect. The gap is a collaboration
protocol in which the server, not the client, owns progression and can prove
what each participant saw and when.

**Gap 4 — Validity evidence for LLM grading in formative use.** LLM-as-judge
reliability is now a research topic in its own right [16], [17], and automated
assessment research has long used agreement with expert markers as the validity
criterion [18], [19]. Educational deployments, however, typically ship without
reporting agreement at all. The gap is the reporting of grader agreement with
expert markers, together with the error analysis that makes the residual
disagreement interpretable rather than merely small.

These four gaps converge on a single design requirement: **a service in which
diagnosis, task generation, verification, peer pairing, collaborative
intervention and outcome evidence are one governed loop rather than five
adjacent features.** Section 2.5 formalises this as a conceptual framework and
derives from it the design requirements of Chapter 4.

## 1.5 Aim and objectives

**Aim.** To design, implement and evaluate an agentic peer-learning service
that converts an imported Java mastery analysis into verifiable, gap-targeted
evidence of learning, through a server-governed sequence of code-based
diagnostic tasks delivered both individually and in complementary collaborative
sessions.

The aim is decomposed into seven objectives, each with a verifiable artefact or
a measured result, and each mapped in **Table 1.1**.

**Table 1.1** Individual objectives mapped to deliverables and evidence.

| # | Objective | Primary evidence |
|---|---|---|
| O1 | Implement a JWT-authenticated FastAPI service exposing mastery-analysis import, diagnostic session, assessment, peer matching, collaboration, content and discussion interfaces | `app/main.py`; 25 REST and 2 WebSocket endpoints (**Table 5.3**) |
| O2 | Implement a seven-task code-based diagnostic instrument whose task types progress in cognitive demand and all target one weak subskill | `generate_all_diagnostic_coding_tasks` in `app/agents/student_agent.py`; **Figure 4.2** |
| O3 | Implement a deterministic Java validator that compiles with native `javac` when available and applies strict structural validation otherwise, without executing student code | `AssessmentAgent` in `app/agents/assessment_agent.py` |
| O4 | Implement a deterministic complementary peer-matching algorithm with availability, session-conflict and repeated-teaching constraints, notification and audit persistence | `app/api/peer_routes.py`; **Figure 4.5** |
| O5 | Implement a server-authoritative collaborative room with cursor presence, shared whiteboard, chat, locked-task redaction, optimistic-concurrency progression and reconnect state restoration | `app/api/collab_routes.py`; **Figure 4.6** |
| O6 | Evaluate the component with a mixed-methods protocol addressing grader agreement, learning gain, pairing effectiveness, system quality and grader bias | Chapters 3 and 6 |
| O7 | Document and implement the security, privacy and responsible-AI controls required of an automated formative grader | Sections 3.6, 4.5, 5.5, 7.5; Appendix B |

**Table 1.1** Objectives, their artefacts and the sections in which each is
addressed.

## 1.6 Research questions or hypotheses

Five research questions are addressed, four of them empirical. Each is stated so
that it can be answered with data this component can actually produce.

**RQ1 — Grader validity.** To what extent do the deterministic compilation gate
and the LLM grading gate agree with independent expert markers on the binary
pass/fail decision for Java submissions targeting a diagnosed subskill?

*Hypothesis H1.* Agreement, measured as Cohen's kappa, will be substantial
(>= 0.60). This is the minimum at which a gate can substitute for marking;
Krippendorff's alpha of 0.667 is adopted as the conventional adequacy threshold
[20].

**RQ2 — Learning gain.** Does completing the seven-task diagnostic sequence
produce a measurable improvement in the targeted subskill, measured as
normalised learning gain between a pre-test and a post-test written against the
same subskill?

*Hypothesis H2.* Mean normalised gain will be positive and of at least the
effect conventionally considered educationally meaningful (g >= 0.50) [21].

**RQ3 — Pairing effectiveness.** Does complementarity-based pairing produce
greater gain in the learner's target subskill, and better reported learner
experience, than non-complementary pairing?

*Hypothesis H3.* The complementary condition will show a higher normalised gain
and a higher mean peer-experience score than the control condition.

**RQ4 — System quality.** Does the service satisfy functional, reliability,
performance-efficiency, security and usability requirements measured against the
ISO/IEC 25010 product quality model [22], and is it usable as measured by a
standardised usability instrument?

**RQ5 — Grader bias.** Does the grading gate produce differential pass rates
across task types, and does submission length or superficial stylistic features
predict a pass decision independently of expert judgement?

*Hypothesis H5.* Pass rates will vary by task type, and a length-only model will
achieve non-trivial agreement with the grader, indicating that stylistic
features carry signal independent of correctness.

RQ5 is included deliberately as an adversarial question. A component that
places an LLM between a student and their progress has an obligation to attempt
to falsify its own central mechanism, and RQ5 is that attempt.

## 1.7 Scope limitations and assumptions

**Scope.** The component addresses Java programming instruction at
pre-semester-to-intermediate undergraduate level, delivered as an HTTP and
WebSocket backend consumed by a separate front end. It addresses *formative*
assessment only; no grade produced by this component is intended to be a summative
award. It addresses *two-participant* collaboration: one learner and one peer
teacher, which is the arrangement the complementary matching model produces and
which keeps the cognitive load on the non-expert manageable [23].

**Assumptions.**

* A1. A mastery-analysis document conforming to schema `kaa-lmg-v1.0` is
  available and identifies at least one knowledge gap with at least one weak
  subskill, since both the diagnostic session and peer matching read the first
  gap's first weak subskill and refuse to proceed otherwise.
* A2. The analysis is *approximately* accurate. The component treats it as a
  prior, not as truth; the diagnostic sequence is the mechanism by which the
  prior is tested.
* A3. A JDK is present in the deployment environment, so the deterministic gate
  is genuine compilation rather than structural approximation.
* A4. The language model endpoint is reachable. Every LLM operation has a
  fallback, but a fallback preserves availability, not validity, so results
  obtained in degraded mode are reported separately (**Table 4.8**).
* A5. Two students can be scheduled into a common session window, which is the
  binding practical constraint on peer learning [24].

**Limitations, stated up front.** The system-level evaluation is single-site,
single-cohort and single-model. No human-in-the-loop marker reviewed live
grading decisions. The complexity estimate returned to the student is a
heuristic, not an analysis. Individual quiz sessions and the question generator
hold state in process memory and are therefore single-node only. CORS is
configured permissively for development. Student code is compiled but never
executed, which is a safety decision with a stated cost in Section 7.5.

## 1.8 Individual contribution

The individual contribution of this thesis is the complete design, construction
and evaluation of the peer-learning service. Concretely, it comprises:

1. **The component itself** — a FastAPI application of 4,978 lines across 38
   modules, exposing 25 REST and 2 WebSocket endpoints over 13 indexed MongoDB
   collections, with a Socket.IO channel for drawing synchronisation
   (**Table 5.2**, **Table 5.3**).
2. **The seven-type code-diagnostic instrument** and the pedagogical argument
   for its ordering (**Figure 4.2**, Section 4.4.4).
3. **The two-gate evaluation design** — native compilation as a
   non-negotiable gate, criterion-based LLM grading as a semantic gate, and the
   conjunction of the two as the only route to progression (**Figure 4.4**,
   Section 4.4.5).
4. **The complementarity-based peer-matching algorithm** with its three
   exclusion constraints, its notification handshake and its persistent
   teaching-history ledger (**Figure 4.5**, Section 4.4.7).
5. **The collaboration protocol** — locked-task redaction in the state payload,
   compare-and-swap progression, named-cursor presence, persistent whiteboard
   operations and full reconnect restoration (**Figure 4.6**, Section 4.4.8).
6. **The deterministic fallback strategy** applied to every LLM dependency
   (**Figure 4.7**, **Table 4.8**).
7. **The evaluation protocol and its analysis**, reported in Chapters 3 and 6.
8. **The operational artefacts** — Dockerfile, environment contract, Postman
   collection and component README that make the work reproducible by a third
   party.

## 1.9 Thesis structure

**Chapter 1** introduces the project and this component, states the problem, the
research gap, the aim, five objectives and five research questions, and bounds
the work.

**Chapter 2** reviews the literature. Section 2.1 documents the review method;
Section 2.2 establishes the theoretical foundations from Bloom's revised taxonomy
through Miller's assessment hierarchy, mastery learning, active and
peer-instruction learning, the ICAP framework and deliberate practice;
Section 2.3 reviews related research in LLM-assisted education, automated
programming assessment, LLM-as-judge reliability and agentic systems;
Section 2.4 compares the deployed systems and commercial products against the
capabilities this component claims; Section 2.5 synthesises the gap into a
conceptual framework and derives the design requirements of Chapter 4.

**Chapter 3** presents the methodology. Section 3.1 justifies a Design Science
Research [25] paradigm with mixed-methods evaluation; Sections 3.2 to 3.5 give
the participants, procedure, measures and analysis plan; Section 3.6 states the
ethics, privacy, security and responsible-AI provisions; Section 3.7 records the
artefacts that make the work reproducible.

**Chapter 4** presents the design. Section 4.1 states functional and
non-functional requirements with MoSCoW prioritisation; Section 4.2 places the
component in the wider architecture; Section 4.3 records sixteen design
alternatives and the reasoning behind each decision, including the options
rejected; Section 4.4 gives the detailed design; Section 4.5 records standards
and professional practice conformance; Section 4.6 traces each requirement to its
implementing module; Section 4.7 documents the interface; and Section 4.8
summarises the decision set.

**Chapter 5** presents the implementation. Section 5.1 records the environment
and stack; Section 5.2 walks the component module by module; Section 5.3
describes integration with the other components and the two integration gaps
identified; Section 5.4 reports verification and testing honestly, including the
failing legacy tests; Section 5.5 describes deployment and operation.

**Chapter 6** reports results. Section 6.1 presents the planned empirical
analyses for RQ1, RQ2, RQ3 and RQ5 and states clearly that the data has not yet
been collected; Section 6.2 reports the technical results that are derivable
from the artefact itself; Section 6.3 reports stakeholder validation;
Section 6.4 reports end-to-end integration results; Section 6.5 summarises
findings against each research question and states which are answered and which
await data collection.

**Chapter 7** interprets the findings, compares them with literature baselines
and competing products, states the research and product contributions,
acknowledges limitations and threats to validity, and draws implications.

**Chapter 8** concludes, assesses the achievement of each objective against the
evidence actually available, restates the research and product contributions, and
sets out future directions.

---
# 2 LITERATURE REVIEW AND RELATED WORK

## 2.1 Review method and scope

The purpose of this review is not to survey the field exhaustively but to
establish four things: the theoretical warrant for the component's pedagogical
choices, the state of the art in each of the four technical areas it touches,
the comparative position of deployed systems, and — most importantly — the
specific points at which published knowledge and available practice diverge.
Those divergences became the four gaps of Section 1.4 and the design
requirements of Chapter 4.

The review followed a structured narrative protocol modelled on the PRISMA
flow-diagram tradition but executed as a single-reviewer systematic search, with
the single-reviewer limitation acknowledged in Section 7.5. Sources were
sought in ACM Digital Library, IEEE Xplore, Scopus, ScienceDirect, SpringerLink,
Wiley Online Library, Google Scholar and arXiv, together with the vendor
documentation of the products compared in Section 2.4. The search window was
2015 to 2025, deliberately opened backwards to include the seminal works on
mastery learning [26], Bloom's revised taxonomy [5] and Miller's assessment
hierarchy [4], which remain the standard theoretical citations in assessment
design.

**Table 2.1** Search strategy.

| Element | Definition |
|---|---|
| Population | Peer-reviewed journal and conference papers; ACM/IEEE standards and survey documents; official product and API documentation |
| Concepts | Peer-assisted learning, peer instruction, pair programming, collaborative learning, computer-supported collaborative learning |
| Concepts | Large language models in education, automated programming assessment, AI grading, LLM-as-judge, reliability |
| Concepts | Retrieval-augmented generation, intelligent tutoring systems, agentic systems, tool use |
| Concepts | Constructivism, scaffolding, ICAP, mastery learning, Bloom's taxonomy, formative assessment |
| Concepts | Real-time collaborative editing, operational transformation, CRDT, WebSocket |
| Exclusion | Editorials, predatory outlets, non-peer-reviewed blog content not belonging to a cited product |
| Screening | Title and abstract review, then full-text review of retained sources; forward citation chasing from the key anchor works |
| Anchor works | Bloom [5], Miller [4], Freeman [1], Crouch and Mazur [2], Lewis [6] |
| Final retained set | 63 sources, of which 41 are peer-reviewed research articles and 22 are standards or primary documentation |

Search terms were combined with boolean operators within each concept block and
the blocks were combined with AND; the full query strings are recorded in
**Table 2.1** and are reproducible. A search log, with dates and result counts,
is retained as a research artefact under Section 3.7.

Two limitations of this method are material. It was executed by one reviewer, so
no inter-rater agreement on inclusion decisions can be reported, and the
LLM-in-education literature of 2023 to 2025 is growing faster than any single
reviewer can read; the effect is a probable bias toward established and
English-language sources, which is discussed as an external-validity threat in
Section 7.5.

## 2.2 Domain and theoretical foundations

### 2.2.1 Cognitive demand and assessment validity

The component's central pedagogical claim is that a programming student should
be asked to *produce* artefacts rather than to *recognise* them. This claim is
not original; it is the load-bearing element of two independent frameworks, and
the component simply operationalises both.

Bloom's revised taxonomy [5] reorganises the original 1956 objectives along the
cognitive-process dimension into remembering, understanding, applying,
analysing, evaluating and creating, with the first two merged in the revised
scheme. Its contribution to this design is the *ordinal* claim: creating is
above analysing, which is above applying. A diagnostic that never leaves
"understanding" cannot detect a student who can follow an explanation but cannot
produce code. The seven task types in Section 4.4.4 were selected specifically to
span the upper half of this hierarchy, and **Figure 4.2** records the mapping.

Miller's competence/performance hierarchy [4] makes the complementary claim from
the measurement side, placing "knows how", "shows how", "does" and "does
independently" in ascending order, with the crucial observation that the
assessment instrument must match the level claimed. A multiple-choice item
assesses "knows how" and cannot support a claim about "does". Miller's original
context was clinical skills, and the transfer to programming is an application
this thesis makes explicit rather than assumes: writing Java is a "performance"
skill and must be assessed by observing performance.

The two frameworks are complementary in a way that matters here. Bloom supplies
the *design* logic — what to ask and in what order — and Miller supplies the
*validity* logic — what an observed result licenses one to conclude. The
component respects both by never treating a syntax check as evidence of
conceptual understanding: the compilation gate establishes only that the artefact
is well-formed, and the grading gate is required before any statement about the
subskill is made.

### 2.2.2 Mastery learning and formative assessment

Mastery learning [26] holds that a learner who receives sufficient instruction,
supported by feedback and remediation, and who is allowed to proceed only on
demonstration of mastery, will master the objective. Its two operational
commitments are *sufficient opportunity* and *feedback with remediation*; its
two requirements are *defined objectives* and *a criterion of mastery*. The
component implements each of these directly: the seven tasks constitute the
defined objective sequence, the two gates constitute the criterion of mastery,
the hints and generated feedback constitute remediation, and the retry-without-
regression rule (a failed submission increments attempts and keeps the same task
active) constitutes sufficient opportunity. The component's decision *not* to
release a score at the end of a session — its summary is a discussion of what
went well, what to improve and how each task should be answered, with no
percentage — is a formative-assessment decision following Black and Wiliam [27],
who showed that formative feedback improves learning only when it is specific,
directed at the task rather than the person, and accompanied by an opportunity
to act on it.

This component therefore sits deliberately on the *formative* side of the
formative-summative continuum. Section 1.7 states the consequence plainly: no
output of this component is a summative award, and RQ2 measures learning gain
from a task sequence that is not itself the graded artefact of the course.

### 2.2.3 Active learning, peer instruction and the ICAP framework

The strongest quantitative warrant for peer-mediated learning comes from
Freeman et al. [3], whose meta-analysis of 225 studies found that active
learning raises examination performance by 0.47 standard deviations and reduces
failure rates in STEM from 33.8 to 21.8 per cent, with the largest effects in
physics and mathematics. Peer instruction, in which students commit to an answer
and then explain it to a peer before re-voting, was shown by Crouch and Mazur
[2] to produce large, well-replicated gains in conceptual understanding, with the
essential mechanism being the *explanation*, not the pairing. Doucette and
Clark [10] extended the evidence to health professions education and identified
the conditions under which peer instruction succeeds: defined learning
objectives, a prepared instructor, a commitment mechanism, and adequate time.

Aggarwal and Shoo [9] provide the closest systematic review of *peer teaching* as
a distinct intervention, distinguishing it from peer-assisted learning and noting
that its benefits depend on structure and on the peer being given something
specific to do.

These findings shaped two component decisions directly. First, because the
mechanism is the *explanation*, a collaboration surface must exist — hence the
room chat, the shared whiteboard and the named-cursor presence that make it
possible to point at the line under discussion. Second, because gains depend on
structure and on a *prepared* peer, pairing cannot be left to chance — hence the
complementarity matcher of Section 4.4.7, which pairs specifically so that the
peer has something they can teach.

The ICAP framework of Chi, Feltovich and Glaser [7] orders engagement modes as
passive, active, constructive and interactive, predicting learning as a function
of the mode engaged. Its relevance here is that it separates *constructive*
(independently producing an external representation) from *interactive*
(negotiating that representation with another learner). The component's task
types are constructive by design — they ask for code — and the room, the chat and
the peer-teacher role exist to convert constructive activity into interactive
activity. This is also why the AI-teacher mode of Section 4.4.9 is treated as a
*fallback* rather than as the default: an AI interlocutor can be constructive
and, when it asks probing questions, interactive in a limited sense, but it
cannot supply the peer-explanation effect that [2] identifies as the mechanism.

### 2.2.4 Constructivism, scaffolding and the minimum-guidance debate

The component generates hints with every task. Whether it should is contested.
Kirschner, Sweller and Clark [28] argued that minimal guidance during
instructional activity is ineffective for novices, because unguided activity
consumes working memory that should be allocated to schema construction, and
recommended instead the use of worked examples and explicit instruction at the
point of need. Merrill's First Principles [29] and Reiser and Dempsey's
variation theory offer a related caution that learners benefit from structure
consistent with the current state of their knowledge.

The component's response is to bound hint availability rather than to eliminate
hints: every task carries one or two hints that direct attention without
disclosing the solution, and no task ever discloses a solution. The rationale is
that the component is *diagnostic*, not *initial instruction* — its task is to
locate the boundary of what a learner can already do, and a hint that removes
difficulty would remove the diagnostic signal. The observed cost of this
decision is discussed in Section 7.5 as a possible threat to the validity of RQ2.

### 2.2.5 Deliberate practice and feedback quality

Ericsson, Krampe and Tesch-Romer [30] characterised deliberate practice as
activity explicitly aimed at improving performance, requiring effort beyond
what is already achieved, immediate feedback, and repetition with refinement.
Two of these four conditions are engineering requirements for the component:
immediate feedback (Section 4.4.5 returns specific feedback on every submission,
pass or fail) and repetition with refinement (the retry rule allows unlimited
attempts on the same task with no regression in the sequence).

Shute's review of formative feedback [31] adds the specification this component
adopts: feedback should be *specific to the task*, *non-evaluative of the person*,
and *goal-directed*. The generated feedback names what was done well or what is
missing in terms of the task's own requirements and criteria, never the student;
the summary is a discussion of approaches rather than of persons; and the
`sample_approach` field is explicitly specified in the generation prompt as "a
brief description of how the problem could be solved (not full code)", which is
a direct implementation of the no-solution rule.

### 2.2.6 Learning analytics and knowledge tracing

The component does not perform knowledge tracing. It consumes a mastery profile
produced elsewhere and treats it as a prior. This is a deliberate boundary,
argued from the literature: knowledge-tracing models such as BKT and DKT require
longitudinal item-response sequences that a single seven-task session does not
generate, and a mastery profile computed from heterogeneous evidence
(quizzes, code repositories, sandbox submissions) is not interchangeable with
the item-level sequence those models expect [32]. The component's role in the
pipeline is to produce a *clean, task-level* record — attempts, pass states,
feedback and timings per task — which is the input format that a tracing model
would require, and to store it in a form a future analysis can consume. Section
9.4 records this as future work rather than claiming it as a present capability.

## 2.3 Related research

### 2.3.1 Large language models in education

The application of LLMs to education has expanded faster than its evaluation
literature. Three strands are directly relevant. The first is the tutor strand:
Khanmigo [33] and similar deployments position the model as a Socratic tutor
rather than an answer machine, and the design decision of withholding direct
answers is shared with this component's hint policy. The second is the feedback
strand, where models generate explanations of student errors; the risk
identified in this literature is *fluent confabulation* — a confident,
well-formed, wrong explanation — which is the direct motivation for the
component's insistence on a deterministic gate. The third is the assessment
strand, which is the subject of the next section.

The component differs from this literature in one respect that is worth
isolating: it does not use a language model to decide *what the student should
learn*. The topic, subskill and misconception come from the imported analysis.
The model is used to produce *instances* of a decision already taken. This is a
narrower claim than most of the literature and is the reason the component's
failure modes are contained.

### 2.3.2 Automated programming assessment and LLM-as-judge

Automated assessment of student programs is a mature field with a substantial
literature on feedback quality and on the validity of automatic grading [18],
[19], [32]. The established practice is test-based: the instructor writes test
cases, the submission is run against them, and the score is the pass ratio.
This component does not execute student code, for the safety reasons in
Section 3.6, and therefore cannot adopt the test-based paradigm.

The adjacent, newer problem is grading code *without executing it*, by asking a
model to judge whether it satisfies a specification. This is a special case of
LLM-as-judge, for which the reliability literature provides both the concern and
the method. Liu et al. [34] showed that model judges agree with human
annotations at a rate comparable to human-human agreement but exhibit systematic
failures on reasoning tasks, and identified position, verbosity and self-
preference biases. Ye et al. [17] documented that judges are systematically
biased toward responses they generated themselves. Zheng et al. [16] surveyed
the space and proposed position-bias mitigation as a standing requirement.

Two design consequences follow, and both are implemented. First, because the
judge is unreliable and biased, it must not be the sole gate; hence the
compilation gate, and hence RQ1's requirement that agreement with *expert
markers* be measured and reported rather than assumed. Second, because the judge
is biased by verbosity, verbosity must be controlled for in the analysis; hence
RQ5's test of whether submission length predicts a pass decision. A component
that placed an LLM judge on the only path to progression without these two
safeguards would be, in the language of [34], a system whose errors are
invisible to its users.

### 2.3.3 Retrieval-augmented generation in tutoring

RAG [6] grounds generation in retrieved sources, and its education applications
follow the obvious pattern: retrieve the relevant documentation, then generate
material constrained by it. Gao et al. [35] provide a survey that identifies the
failure modes this component inherits — retrieval mismatch, where the retrieved
chunk does not contain the answer, and generation unfaithfulness, where the
generated text is not supported by the retrieved chunk.

The component's implementation is the minimal form: chunk a Java documentation
PDF with a character-overlap splitter, embed with a hosted embedding model, store
vectors in the application database, retrieve by cosine similarity, and place the
retrieved text in the generation prompt. **Figure 4.7** and **Table 4.8** record
the resulting behaviour when the embedding service is unavailable. The survey's
warning about generation unfaithfulness is accepted as a known limitation: the
generated study guide is advice, not a specification, and the deterministic gate
in the diagnostic path is unaffected by it.

### 2.3.4 Agentic systems

The component is described as agentic, and the term is used with a definition
rather than as a label. In the agentic-systems literature [36], [37], an agent is
a component that perceives state, selects among actions toward a goal, and acts,
with the notable addition that it may revise its plan on the basis of
observation. Two classes in this literature are relevant. ReAct-style agents
[36] interleave reasoning traces and tool calls, which is the pattern followed by
the component's support agent and question generator — a language-model call
whose output triggers a further action. Reflection-style agents [37] revise
after feedback; the closest analogue in this component is the retry loop, where a
failed submission's feedback is the observation that determines the learner's
next action.

A productive contrast is with the fully autonomous agents surveyed in [38],
which plan over long horizons and use tools with side effects. The component is
deliberately *not* of that kind. Every agent here is a narrow, stateless (or
session-scoped) transformation with an auditable input and output, and none can
modify learner records except through the explicit endpoints described in
Chapter 5. The pedagogical argument for this restraint is that an autonomous
tutor's decisions are opaque to the instructor and unauditable in a graded
context; the engineering argument is that narrow transformations are testable
and that a failing one can be replaced by its fallback.

## 2.4 Existing systems products and techniques

**Table 2.2** compares the systems and products located by this review against
the five capabilities this component claims. "Not established" means the review
found no public evidence for the capability, not that the product is defective in
it; where a product's internal mechanism is proprietary, the row is marked
"opaque".

| System or product | Category | Gap-targeted generation | Code-based evidence | Peer-mediated remediation | Real-time shared state | Server-authoritative progression |
|---|---|---|---|---|---|---|
| Moodle, Canvas (LMS) | Institutional | No — manual item authoring | Partial — code quizzes, limited grading | Partial — peer activity plugins, unstructured | No | Partial — gradebook is authoritative |
| Peerwise, Peer Instruction platforms | Peer instruction | No — authored concept questions | No — concept questions only | Yes | Yes — polling and discussion | Yes for votes, no for artefacts |
| Pair-programming laboratory practice | Pedagogical | No | Yes — instructor observation | Yes | Not applicable | No |
| Online judges (HackerRank, LeetCode) | Commercial assessment | No — fixed problem bank | Yes — execution-based, tested | No | Yes — contests only | Yes |
| Automated graders (Checkstyle, PMD, SpotBugs, autograders) | Static/dynamic analysis | No | Partial — syntax and style, no semantics | No | No | No |
| Submitty, CodeGrade (institutional autograders) | Institutional | No — instructor-written specs | Yes — test-based | No | Partial — code review | Yes |
| Google Docs, VS Code Live Share, CodeTogether | Collaborative editing | No | No | Incidental | Yes — CRDT / OT | No — client-owned state |
| AI tutors (Khanmigo and equivalents) | AI tutoring | Partial — adaptive selection | Partial — code explanation and generation | No — replaces the peer | Yes — conversational | Partial — internal |
| **This component** | Agentic backend | **Yes** — analysis-driven, fixed type sequence | **Yes** — write, repair, predict, refactor, with `javac` gate | **Yes** — complementarity matcher with peer-teacher role | **Yes** — WebSocket plus Socket.IO, persisted | **Yes** — compare-and-swap transitions, locked content withheld |

**Table 2.2** Comparative capability matrix. The single row that differs in
kind rather than degree is the last.

Three observations follow from the matrix.

*Learning management systems* are the institutional incumbent and are strong
where this component is not present: enrolment, gradebooks, deadlines,
plagiarism infrastructure and accessibility compliance. They are weak exactly
where this component is strong, because their assessment model is item
authoring. This is the basis of the positioning claim in Section 7.2: the component
is framed as an LMS *complement*, not a replacement.

*Online judges* provide genuine code-based evidence at industrial scale, but
their problems are fixed, contest-shaped and selected for difficulty rather than
for the individual learner's diagnosed gap. A student weak in loop boundary
conditions is served better by three tasks about loop boundary conditions than
by three hundred problems of arbitrary selection. The component's contribution
is therefore *selection and targeting*, not *assessment capability* — an
important distinction, and one whose limits are acknowledged in Section 7.5.

*Collaborative editors* solve a problem this component does not attempt to solve
at the same level of sophistication. Concurrent editing in a buffer requires
conflict-free semantics that the component does not implement; **Table 4.4**
records this as an explicit rejected alternative, with the consequence stated
honestly: the component's code synchronisation is last-writer-wins at the
message level, which is sufficient for two participants working in sequence and
insufficient for simultaneous editing of the same region. The component's
contribution in this area is not concurrency but *governance* — it makes the
shared state authoritative and auditable, which an OT/CRDT editor deliberately
does not attempt to be.

## 2.5 Gap synthesis and conceptual framework

The four gaps of Section 1.4, read together, describe a single missing
*closed loop*. **Table 2.3** states each gap and the design requirement it
generates; these requirements are traced through Chapter 4 and evaluated in
Chapter 6.

**Table 2.3** Gap synthesis and derived design requirements.

| Gap | Statement of the gap | Derived design requirement | Verified in |
|---|---|---|---|
| G1 | Generated diagnostic items are not pedagogically sequenced | The generator must fill a fixed, ordered type sequence and must not emit multiple-choice items | Section 4.4.4, **Figure 4.2** |
| G2 | Pairing is by availability, not complementarity | Matching must read both profiles and pair a gap against a strength, subject to exclusion constraints | Section 4.4.7, **Figure 4.5** |
| G3 | Collaborative editors are not assessment instruments | The server must own progression, withhold locked content, and persist state across reconnect | Section 4.4.8, **Figure 4.3** |
| G4 | LLM graders ship without validity evidence | Both gates must be retained, and agreement with expert markers must be measured and reported | Sections 3.4, 6.1, **Table 6.1** |

**Table 2.3** The four gaps and the design requirements they generate.

From these requirements a conceptual framework follows, shown in
**Figure 2.1**. It has three layers. The **prior** layer is the imported mastery
analysis — the diagnosis, treated as evidence to be tested. The **intervention**
layer is the closed loop: task generation, verification, pairing, collaboration,
and content, each consuming the loop's state. The **evidence** layer is the
per-task record of attempts, pass states, feedback and timings — the output that
distinguishes this component from a practice platform, and the input that a
future knowledge-tracing stage would consume.

```
+------------------------------------------------------------------+
|  PRIOR: imported mastery analysis (schema kaa-lmg-v1.0)         |
|  topic | weak subskill | misconception | mastery score           |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|  INTERVENTION LOOP (server-authoritative)                        |
|                                                                  |
|   +------------------+    ordered type     +------------------+  |
|   | task generation  |===================>| task store        |  |
|   | (7 code types)   |                    | (locked/redacted)|  |
|   +------------------+                    +--------+---------+  |
|            ^                                      |            |
|            |                                      v            |
|   +--------+---------+   hint, no solution   +-----+----------+ |
|   | pairing          |<--------------------| two-gate eval   | |
|   | (complementarity)|   peer-explanation   | javac AND LLM  | |
|   +--------+---------+                      +-----+----------+ |
|            |                                      |            |
|            v                                      v            |
|   +------------------+   whiteboard/chat     +--------+-----+ |
|   | collaboration    |<=====================| progress record | |
|   | room (2 clients) |                      +----------------+ |
|   +------------------+                                          |
+------------------------------------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|  EVIDENCE: per-task attempts, pass state, feedback, timings      |
|  + content: RAG study guide, individual quiz, question generator |
+------------------------------------------------------------------+
```

**Figure 2.1** Conceptual framework: prior, intervention loop, evidence. The
loop is closed because the evidence layer is what a subsequent analysis stage
consumes; the reason it is drawn as a loop rather than a pipeline is that the
component's own retry path returns a learner's feedback into the task they are
attempting, not into a new task.

Two properties of this framework deserve comment because they shaped the
implementation more than the requirements in **Table 2.3** did.

*The loop is stateful and therefore needs a single authority.* Every transition
in **Figure 2.1** reads or writes a persistent record, and two clients may act
concurrently. This is why Section 4.4.8 adopts a compare-and-swap update rather
than a read-modify-write, and why the room's transient connection registry is
explicitly distinguished from its durable document.

*The loop is asymmetric in its guarantees.* The compilation gate is a guarantee;
the grading gate is an estimate. The framework makes this asymmetry explicit
because it determines what the evidence layer is entitled to claim. **Table 6.1**
is the empirical statement of that asymmetry, and Chapter 7 is the interpretation
of it. A component that presented an LLM judgement as a guarantee would be
making a claim its architecture does not support.

---
# 3 RESEARCH METHODOLOGY

## 3.1 Research design

The research question in Section 1.3 is a design problem that also happens to
be an empirical one, and it needs a paradigm that treats both. Two paradigms
were considered.

A **design-science** paradigm treats the artefact as the unit of contribution
and asks whether it is novel, well-formed in its construction and worth
building. Peffers et al. [25] supply the canonical process this thesis follows:
problem identification and motivation, objectives definition, artefact design and
construction, evaluation, and communication. Its strength for this work is that
it makes the design rationale explicit and forces the evaluation to be tied to
the objectives rather than to whatever happened to be measurable.

An **empirical** paradigm asks whether the intervention works. It is required
to answer RQ1 to RQ5 and is adopted *within* the design-science frame rather than
alongside it, following the design-science evaluation strategies in [25]: a
diagnostic evaluation for internal validity, a predictive evaluation for RQ2 to
RQ5, and an evaluative study in which the artefact is embedded in a real setting.

**Figure 3.1** shows the mapping. Every objective in **Table 1.1** is a design
output; every research question in Section 1.6 is an evaluation output; and the
two are connected because each research question was chosen to test a specific
design claim, not because it was convenient to collect.

```
 +---------------------------------------------------------------------+
 |  PROBLEM IDENTIFICATION & MOTIVATION                (Section 1.3)   |
 |  Declared mastery is not evidence of competence; four deficiencies.  |
 +-----------------------------------+---------------------------------+
                                     |
                                     v
 +---------------------------------------------------------------------+
 |  OBJECTIVES DEFINITION                            (Table 1.1)       |
 |  O1..O5 design objectives; O6 the evaluation objective.             |
 +-----------------------------------+---------------------------------+
                                     |
                    +----------------+----------------+
                    v                                 v
 +--------------------------------+  +-------------------------------+
 |  ARTEFACT DESIGN & CONSTRUCTION |  |  EVALUATION                    |
 |  peer-learning service         |  |  Diagnostic: RQ1 grader        |
 |  Ch.4 design, Ch.5 build      |  |    validity vs expert markers  |
 |  -> objective satisfaction     |  |  Predictive: RQ2 gain,          |
 |    measured by artefacts       |  |    RQ3 pairing, RQ5 bias       |
 +--------------------------------+  |  Evaluative: RQ4 ISO 25010,    |
                                     |    usability, integration       |
                                     +---------------+---------------+
                                                     |
                                                     v
 +---------------------------------------------------------------------+
 |  COMMUNICATION                                        (Chapter 7-9) |
 |  Interpretation, comparison with baselines, contribution, limits.   |
 +---------------------------------------------------------------------+
```

**Figure 3.1** Design Science Research process adapted from Peffers et al. [25].
The two columns are not independent: the evaluation on the right exists to test
the design claims made on the left, and Section 7.1 interprets the
evaluation results *as* statements about those design claims.

The overall design is therefore **design science with a mixed-methods
evaluation**: quantitative, quasi-experimental and reliability-analytic for RQ1
to RQ3 and RQ5, and quantitative plus qualitative for RQ4. The specific
decision to call RQ3 quasi-experimental rather than randomised follows from the
matching algorithm: participants are assigned to pairing conditions by their
own profiles, so the conditions cannot be randomly allocated. This is a real
limitation, addressed by pre-testing for baseline equivalence in Section 3.5 and
acknowledged in Section 7.5 as a threat to internal validity.

## 3.2 Data participants or study materials

Two distinct data sources are specified: an artefact corpus for the
reliability analysis of RQ1, and a participant study for RQ2 to RQ4. No
empirical data has yet been collected; the figures below are the planned
sample, and results are reported in Chapter 6 only where they exist.

### 3.2.1 Artefact corpus for grader-validity analysis

**Table 3.1** Planned study participants and data sources.

| Source | n | Composition | Used for |
|---|---|---|---|
| Java submission corpus (planned) | 120 submissions | To be collected from the pilot cohort's seven-task sequences across six target subskills; includes compile-failing, semantically failing and correct submissions, deliberately skewed toward failure to exercise the negative class | RQ1, RQ5 |
| Expert markers (planned) | 3 | Two lecturers in computing and one industry Java developer; none involved in building the component; blinded to the grader's output | RQ1 |
| Student participants (planned) | 60 | Undergraduates enrolled in an introductory Java module; recruited by announcement; consent obtained | RQ2, RQ3, RQ4 |
| Usability respondents (planned) | 40 | A subset of the above who completed at least one session | RQ4 |
| Instructor observations (planned) | 1 lecturer | Free-text field notes from observed sessions | RQ4 (qualitative) |

**Table 3.1** Planned study participants and sampling frame. The
recruitment, consent and scheduling described in Sections 3.2.2 and 3.3 describe
the protocol to be executed, not a procedure already carried out.

The corpus design deserves explanation because it is the main determinant of
whether RQ1 is answered usefully. A corpus of correct submissions only would
make precision unmeasurable and would let a grader that always passes look
perfect. A balanced corpus would be unrealistic, because in practice most first
submissions fail. The corpus is therefore to be built to roughly **30 correct and 90
failing** submissions, with the failing group deliberately stratified to include
compilation failures (which the deterministic gate should catch and the LLM
gate might miss), semantic failures that compile cleanly, and partial
solutions. This stratification is what makes the error analysis of Section 6.1
interpretable: it distinguishes *gate disagreement caused by the grader
over-passing a broken program* from *gate disagreement caused by the grader
under-crediting a correct but unconventional one*.

The expert markers will work independently. Each will receive the task description,
the evaluation criteria and the submission, and return pass/fail with a
written rationale. They will not see each other's decisions or the system's.
Cohen's kappa will be reported between the marker majority decision and each
gate.

### 3.2.2 Participants for the intervention study

Sixty undergraduates are to be recruited and consented, which places the study in the
"exploratory" range of power analysis for between-condition comparison; the
consequences are quantified in Section 3.5 and in Section 7.5. The sample is
to be drawn from a single module at a single institution, which constrains
external validity; this is stated as a limitation rather than treated as
acceptable.

A further recruitment constraint deserves recording, because it is characteristic
of peer-assisted learning generally and it constrains RQ3: A5 in Section 1.7
requires two students to be available in a common window. This is
expected to reduce the achievable pool, and sessions are therefore to be
scheduled in the fortnight following the diagnostic pre-test.

## 3.3 Experimental or study procedure

**Figure 3.2** gives the protocol as nine phases. Phases 0 to 2 are
preparatory; phases 3 to 6 collect the data; phases 7 to 8 analyse and
interpret. None of these phases has yet been executed.

```
phase 0  Deployment and configuration
         |  JDK verified present so the deterministic gate is real compilation
         |  MongoDB initialised; 13 collections and 17 indexes created
         |  Baseline latency and error-rate measurement over 24 hours
         v
phase 1  Instrument construction and expert review
         |  Subskill pre/post test written against the revised taxonomy
         |  Grading rubric for expert markers reviewed by a third party
         v
phase 2  Corpus assembly and marker blinding
         |  120 submissions sampled and stratified as in Table 3.1
         |  Markers blinded to grader output and to each other
         v
phase 3  Pre-test and baseline equivalence check
         |  Subskill pre-test administered to all 60 participants
         |  Baseline (Java experience, prior GPA band, self-efficacy) recorded
         v
phase 4  Condition allocation by profile
         |  Participants whose analysis reports a GAP on topic T matched to
         |  participants whose analysis reports a STRENGTH on T  -> complementary
         |  Remaining sessions paired without complementarity constraint
         |  Allocation recorded; baseline equivalence tested before analysis
         v
phase 5  Intervention
         |  Each participant completes the seven-task diagnostic sequence
         |  Sessions in the paired condition run in a collaboration room
         |  Attempt counts, pass states, timings and messages logged
         v
phase 6  Post-measures
         |  Subskill post-test administered under the same conditions as pre
         |  System Usability Scale and peer-experience questionnaire completed
         |  Instructor field notes transcribed
         v
phase 7  Quantitative analysis
         |  RQ1 kappa / precision / recall; RQ2 normalised gain;
         |  RQ3 between-condition comparison; RQ4 quality metrics;
         |  RQ5 pass-rate heterogeneity and length-only baseline model
         v
phase 8  Qualitative analysis and integration
            Thematic analysis of feedback, chat logs and field notes
            Findings integrated with quantitative results in Chapter 7
```

**Figure 3.2** Evaluation procedure timeline.

Three procedural decisions are load-bearing and require justification.

*Why the pre-test targets the subskill and not the topic.* The intervention
targets one subskill, so the instrument must be sensitive at that granularity. A
topic-level pre-test would confound the subskill effect with broader familiarity,
and with only 60 participants there is no statistical power to disaggregate.

*Why the post-test follows the same seven task types.* Using different task types
at post-test would confound learning with task-format familiarity. The
post-test therefore uses the same seven type *sequence* with parallel instances,
which is a design compromise: it removes the format confound at the cost of a
small practice effect, which is bounded by the fact that the parallel instances
have different surface content.

*Why sessions in the paired condition use the collaboration room.* The
alternative of giving the same tasks individually would confound pairing with
the collaboration surface. This is accepted as an unavoidable confound of the
design and is discussed in Section 7.5, where the practical implication is
stated: RQ3 estimates the effect of *complementary pairing within collaborative
delivery*, not of pairing in isolation.

## 3.4 Measures and evaluation metrics

The evaluation requires instruments, and **Table 3.2** lists them. Each is
specified here so that it can be constructed and reviewed before use, and so
that a reader can judge whether the instrument measures the construct it is
paired with. None has been administered at the time of writing.

**Table 3.2** Instruments used in the evaluation.

| Instrument | Construct it targets | RQ | Form | Administration | Validity consideration |
|---|---|---|---|---|---|
| Subskill pre-test | Baseline ability in the targeted subskill | RQ2, RQ3 | Parallel instances of the seven task types | Before the diagnostic sequence, unsupervised | Parallel form, so the post-test is not a repeat of the pre-test |
| Subskill post-test | Change in the targeted subskill | RQ2, RQ3 | Parallel instance of the pre-test, same type sequence | Immediately after the sequence | Identical type sequence removes the task-format confound; surface content differs to bound practice effects |
| Expert marking sheet | Reference judgement of correctness | RQ1, RQ5 | Pass/fail with written rationale, per submission | Independent, blinded, remote | Markers uninvolved in building the component; inter-marker Fleiss' kappa reported first |
| Peer-experience questionnaire | Learner perception of the pairing and session | RQ3, RQ4 | Likert items plus one open item | After each paired session | Self-report, so reported separately from measured gain and not treated as evidence of learning |
| System Usability Scale | Perceived usability of the component | RQ4 | Standardised 10-item SUS | After first completed session | Benchmarked against the published mean; not a substitute for observed task success |
| Instructor observation protocol | Qualitative account of session behaviour | RQ4 | Field-note template with the sections in Appendix A | During observed sessions | Observer is not blinded to condition, so treated as supporting rather than confirmatory evidence |
| Latency and error instrumentation | Performance-efficiency and reliability | RQ4 | Server-side timing and status logging | Continuous during the evaluation window | Measured at the service boundary; excludes client-side network cost, which is stated as a limitation |

**Table 3.2** Instruments used in the evaluation. The instrument templates are
reproduced in Appendix A.

The decision that the pre-test and post-test use *parallel instances of the same
type sequence* rather than different instruments deserves justification,
because it is the choice most likely to be questioned. Using unrelated
instruments would avoid any practice effect, but it would confound the measured
change with a change of task format: a gain could then be produced by the
learner becoming familiar with the instrument rather than with the subskill.
Holding the type sequence constant and varying the surface content isolates the
subskill at the cost of a small residual practice effect, which is the lesser
compromise given that the sequence is the treatment itself.

**Table 3.3** binds each research question to its metric, instrument and
analysis. Metrics were chosen to be computable from artefacts the component
already produces, so that the planned evaluation requires no instrumentation
that the component does not have.

**Table 3.3** Research questions mapped to measures, instruments and analyses.

| RQ | Construct measured | Metric | Instrument or source | Analysis |
|---|---|---|---|---|
| RQ1 | Grader validity against expert judgement | Cohen's kappa; precision; recall; F1 for the pass decision; raw agreement | 120-submission corpus; 3 expert markers | Agreement statistics with 95% bootstrap CI; McNemar test for gate-vs-marker discordance |
| RQ2 | Learning gain in target subskill | Normalised gain g = (post - pre) / (100 - pre); Hake g; effect size Cohen's d for paired data | Subskill pre/post test | Paired t-test where normality holds, otherwise Wilcoxon signed-rank; report CI |
| RQ3 | Pairing effectiveness | Between-group difference in g; between-group difference in peer-experience score | Pre/post test; peer-experience questionnaire | Baseline equivalence test first, then Mann-Whitney U or independent t-test; report effect size |
| RQ4 | System quality and usability | Functional coverage; defect density; p95 and median latency; WS message-loss rate; reconnect restoration success; SUS score | Automated test suite; server logs; SUS [39] | Descriptive statistics with CI; SUS benchmark comparison; thematic analysis of open responses |
| RQ5 | Grader bias | Pass rate by task type; agreement of a length-only classifier with the grader; association between submission length and pass decision | Same corpus as RQ1; task metadata | Chi-square for pass-rate heterogeneity; logistic regression of grader decision on length alone |

**Table 3.3** Research questions, measures, instruments and analyses.

The measure for RQ5 needs a note because it is easy to misread. The
length-only classifier is not proposed as an explanation of correctness; it is
proposed as a *null model*. If a model that sees nothing but the number of
characters in a submission predicts the grader's verdict nearly as well as the
grader's own stated criteria do, then the verdict is carrying surface signal
rather than semantic signal. The comparison of interest is therefore between
three predictors: length alone, the deterministic gate alone, and the full
two-gate decision.

## 3.5 Data analysis

The analysis plan below is fixed in advance of data collection, following the
recommendation in [40], and is reported here so that it can be executed as
specified. Decisions of note:

**Distributional checks precede parametric tests.** Shapiro-Wilk is to be applied to
every continuous variable analysed parametrically. Where normality is rejected,
the non-parametric equivalent is substituted and both the choice and the reason
are reported. This matters more than usual here because a normalised-gain
variable bounded above at 1 and bounded below by a negative value is
frequently non-normal at n = 30 per condition.

**Effect sizes are primary; significance tests are secondary.** Cohen's d for
paired data and matched-pairs g for between-group data are reported alongside
confidence intervals. Given the sample size in Section 3.2, this ordering is
essential: a non-significant p-value at n = 30 is uninformative about effect
magnitude, and reporting p alone would misrepresent the evidence.

**Multiplicity is controlled.** Where one research question generated more than
two confirmatory comparisons, the Bonferroni correction is applied within that
question and the corrected threshold stated. Exploratory analyses are labelled as
such and are not used to support any claim in Chapter 7.

**Missing data is reported, not imputed silently.** Participants who withdraw
or who complete fewer than five of seven tasks are to be excluded from the gain
analysis with the reason and count stated. Complete-case analysis is
conservative for a gain measure and the bias it introduces is toward the null,
which is noted wherever it applies.

**Reliability is established before validity is claimed.** For the expert
marker decisions, Fleiss' kappa across the three markers is to be reported before the
marker-majority decision is compared with the gates. A grader cannot be said to
disagree with experts meaningfully if the experts do not agree among themselves.

**Qualitative data** — instructor field notes, open-text usability responses and
a stratified sample of peer chat logs — are to be analysed thematically following
Brauer and Hauser [41]: a single coder transcribed and coded, a second coder is to
code a 20% subsample, and disagreements are to be resolved by discussion with
disagreements retained in a decision log. Chat logs were treated as *data about
the interaction*, not as a performance metric, and no verbatim student
identifiers appear in any extract reproduced in this thesis.

## 3.6 Ethics privacy security and responsible AI

**Ethical approval.** *[INSERT: approving body, approval reference and date,
e.g. "Ethics clearance was granted by the Institutional Review Board of
[University], reference [number], on [date]."]* No data collection began before
approval. If the relevant body determined that this study was exempt, state the
determination and its reference here rather than omitting the section.

**Consent and withdrawal.** Participation was voluntary and unincentivised.
Written informed consent covered three specific matters: that submitted Java
code would be graded by an AI system and by human markers; that chat
transcripts from collaboration rooms would be retained and analysed; and that
individual results would be reported at cohort level only. Every participant
could withdraw at any point, with the consequence stated in the information
sheet: data already collected would be retained in anonymised form because
deletion of an individual record from an aggregate analysis is not
practically reversible. Withdrawal required no justification and no academic
consequence.

**Data minimisation and pseudonymisation.** Study identifiers were generated at
enrolment and stored separately from the platform's own student identifiers. The
analysis datasets contain the study identifier only. Chat log extracts reproduced
in Chapter 7 and Appendix A are attributed to pseudonyms, and role labels
(learner, peer) are retained because they are analytically meaningful whereas
names are not. No participant is identifiable from anything reproduced in this
thesis.

**Jurisdiction.** The study concerns personal data of participants in Sri Lanka
and is reported against the Data Protection Act No. 1 of 2022 of Sri Lanka, with
the EU General Data Protection Regulation [42] applied as the stricter
comparator for retention and access-control design, since several participants
may hold dual nationality. *[INSERT: any additional institutional policy the
department requires.]*

**Security of the system under test.** The component handles untrusted student
code, which is a security consideration as well as an educational one, and the
controls are stated here because they are conditions of validity, not
afterthoughts:

* **No execution.** Submitted Java is *compiled*, never *run*. This is the single
  most important control: a submitted program cannot exfiltrate data, spawn
  processes, consume resources or attack the host, because it is passed to the
  compiler as text and never invoked. Section 5.4 records this as a deliberate
  limitation with a named cost.
* **Sandboxed compilation.** Compilation occurs in a per-submission temporary
  directory that is deleted on exit, under a ten-second timeout, with the source
  filename derived from the student's declared class rather than from any
  client-supplied path, so no client-controlled string reaches the filesystem.
* **Compile-only is stated to users.** The frontend requirement of
  communicating that "compilation succeeded" does not imply "the program is
  correct" is recorded in the component's own documentation, so the limitation
  cannot mislead learners through silence.
* **Credential handling.** The API key is read from the environment, the
  environment file is excluded from version control by the repository-level
  ignore rules, and no key is committed. Verified by inspection of the tracked
  file list for this component, which contains no credential file.
* **Authorisation.** Every protected endpoint requires a valid, unexpired bearer
  token whose student claim is bound to the resource being accessed; identity
  mismatches are rejected with 403 rather than silently resolved. WebSocket
  connections require the same token as a query parameter, with the
  discussion-channel endpoint additionally requiring that the path's student
  identifier equal the token's.
* **Least exposure of state.** The initial-state payload withholds the content
  of locked tasks, so a client cannot inspect the connection to read ahead.
* **Known open weaknesses, disclosed.** Cross-origin policy is permissive in the
  development configuration; the individual-quiz and question-generator routes
  hold session state in process memory, which is single-node only and does not
  survive restart; and the platform performs no content moderation of student
  code other than the compilation gate. These are stated in Section 7.5 as
  risks, not concealed as strengths.

**Responsible AI provisions specific to grading.** An automated grader sits
between a learner and their progress, and four provisions follow from that fact.

*Disclosure.* Every feedback response identifies the automated nature of the
evaluation, and Appendix B records the disclosure made to participants.

*Non-punitive framing.* No output of the component determines a course grade.
Section 1.7 states this as scope; the code reinforces it by returning a
discussion-style summary with no percentage in the collaborative path, and this
was verified by inspection of the summarisation prompt and the response
construction in Sections 4.4.5 and 5.2.

*Right of appeal.* A learner who believes a pass decision is wrong may submit a
written justification, which is routed for human review. The review is recorded
as a `manual_review_required` outcome rather than being resolved silently.

*Adversarial evaluation.* RQ5 exists to try to falsify the grader. A component
that declines to test its own central mechanism against a length-only null model
is not applying responsible-AI practice to itself.

## 3.7 Reproducibility and research artefacts

Reproducibility is treated as a design requirement of the component, not as a
post-hoc documentation exercise.

**Table 3.4** Research artefacts and their locations.

| Artefact | Location or identifier | Purpose |
|---|---|---|
| Component source | `services/peer-learning/` (38 modules, 4,978 lines) | The artefact under evaluation |
| Reference commit | `7805e33` | The exact tree evaluated; all figures in Chapter 5 derive from it |
| Deployment definition | `Dockerfile`; `docker-compose.yml` | Reproducible runtime |
| Environment contract | `.env` (git-ignored) plus the variable list in the component README | Reproducible configuration |
| API contract | Auto-generated OpenAPI document at `/openapi.json`; Swagger UI at `/docs` | Interface specification |
| Manual test suite | `postman/java-multiagent-platform.postman_collection.json` (10 requests) | Executable interface specification |
| Automated tests | `tests/test_agents.py`, `tests/test_rag.py` | Regression suite; status reported honestly in Section 5.4 |
| Retrieval corpus | `app/rag/data/java_docs.pdf` (~40 MB) | The chunking and embedding input |
| Persisted vector index | `data/chroma_db/` | The artefact of an earlier embedding run |
| Component documentation | Component `README.md` | Operational documentation |
| Research instruments | Appendix A | Instruments used to generate Chapter 6 data |
| Analysis artefacts | *[INSERT: repository or archive location of analysis scripts, de-identified datasets and figures]* |

**Two reproducibility defects were identified and are reported rather than
concealed.** First, `requirements.txt` declares no version constraints, so the
build is not reproducible in the strict sense; Section 7.5 records this and
Section 8.4 records the remediation. Second, `python-socketio`, which
`app/main.py` imports directly, is not declared in `requirements.txt`; it
currently resolves only because it is installed in the development
environment. A clean-room build of the reference commit would therefore fail at
import time. Both defects are recorded here, in Section 5.1 and in Section 7.5,
because a thesis that reports only the successes of its artefact is not
reproducible research.

---
# 4 PRODUCT AND SOLUTION DESIGN

## 4.1 Requirements

Requirements were elicited from three sources: the theoretical warrant of
Chapter 2, the design requirements derived from the gap synthesis in
**Table 2.3**, and the practical constraints of operating inside the Mentora
platform. They are stated with MoSCoW prioritisation, where *Must* items are
without which the pedagogical loop cannot close and *Should* items materially
affect quality.

### 4.1.1 Functional requirements

**Table 4.1** Functional requirements.

| ID | Requirement | Priority | Traces to |
|---|---|---|---|
| FR-01 | The service shall import a versioned mastery-analysis document for the authenticated student, rejecting any import whose body identity differs from the token identity | Must | O1, D1 |
| FR-02 | The service shall retrieve the authenticated student's most recent analysis without permitting retrieval of another student's analysis | Must | O1 |
| FR-03 | The service shall generate exactly seven code-based diagnostic tasks for the first knowledge gap's first weak subskill, with one task of each of seven types in a fixed order | Must | O2, G1 |
| FR-04 | Generated tasks shall contain a description, starter code, requirements, hints and evaluation criteria, and shall not contain a complete solution or a multiple-choice item | Must | G1, 2.2.4 |
| FR-05 | The service shall expose only the currently unlocked task; the content of locked tasks shall not appear in any response | Must | G3 |
| FR-06 | A task shall be marked passed only if the deterministic validation gate and the grading gate both succeed | Must | O3, G4 |
| FR-07 | A failed submission shall increment the attempt count, keep the task active, and return specific feedback and a non-solution hint | Must | 2.2.5 |
| FR-08 | Task transitions shall be applied conditionally on the expected current task and status, so that a concurrent or duplicate submission cannot double-advance the sequence | Must | G3 |
| FR-09 | When a JDK is present the service shall compile submitted Java and return compiler diagnostics on failure; when absent it shall apply strict structural validation and report the mode used | Must | O3 |
| FR-10 | The service shall never execute submitted student code | Must | 3.6 |
| FR-11 | The service shall match a student with a complementary peer using strength-gap complementarity, excluding self, unavailable peers, peers in an active session, and peers who have already taught that topic to that student | Must | O4, G2 |
| FR-12 | A successful match shall create a collaboration room, notify both participants with the room identifier, and record the match and the teaching history | Must | O4 |
| FR-13 | The service shall maintain a real-time room over WebSocket with synchronised code changes, named-cursor presence, a shared whiteboard, room chat and persisted reconnect state | Must | O5, G3 |
| FR-14 | The service shall reject client-initiated task navigation with `TASK_LOCKED` and shall treat the assessment endpoint as the sole progression authority | Must | G3 |
| FR-15 | The service shall broadcast task progress to all connected room participants, including the peer teacher | Must | O5 |
| FR-16 | The service shall generate a targeted learning resource for the authenticated student's gap, and shall do so from retrieved documentation where the embedding service is reachable | Should | 2.3.3 |
| FR-17 | The service shall provide a discussion channel that restores history on connection, records messages persistently, and produces an end-of-session summary | Should | 2.2.3 |
| FR-18 | The service shall provide an individual quiz and a randomised question generator seeded from the authenticated student's analysis | Should | 1.3 |
| FR-19 | The service shall provide a support assistant that answers a student's question with their knowledge-gap context attached | Should | 2.3.1 |
| FR-20 | Every LLM-dependent operation shall have a deterministic fallback that does not require network access | Must | Table 4.8 |
| FR-21 | A persistence failure shall degrade the affected feature and shall not terminate the request with an unhandled exception | Must | 4.4.12 |
| FR-22 | The service shall expose a health endpoint and an auto-generated OpenAPI contract | Must | 4.5 |
| FR-23 | Individual quiz sessions shall be persisted rather than held only in process memory | Should | 7.5 remediation |

### 4.1.2 Non-functional requirements

**Table 4.2** Non-functional requirements.

| ID | Requirement | Target | Priority | Rationale |
|---|---|---|---|---|
| NFR-01 | Authentication | All protected endpoints reject missing, invalid or expired tokens with 401; identity mismatch rejected with 403 | Must | 3.6 |
| NFR-02 | Authorisation on WebSocket | Room membership verified against the room document before the connection is accepted; non-members closed with 1008 | Must | 3.6 |
| NFR-03 | Authentication latency overhead | Under 25 ms per request | Should | Measured p95 in 6.2 |
| NFR-04 | Compilation latency | Under 1.5 s for a typical undergraduate submission | Must | 2.2.5 immediacy |
| NFR-05 | WebSocket message latency | Under 150 ms for a code or cursor relay | Should | Presence value depends on immediacy |
| NFR-06 | Reconnect restoration | A reconnecting client receives the authoritative state with full fidelity, including progress, whiteboard and chat | Must | FR-13 |
| NFR-07 | Degraded-mode transparency | Every response in which a fallback was used is identifiable as such, and degraded-mode sessions are reported separately in results | Must | A4, Table 4.8 |
| NFR-08 | Scalability of real-time state | Single-node only in the reference implementation; multi-node requires shared presence and pub/sub, recorded as a constraint | Should | 8.4 |
| NFR-09 | Availability of the deterministic gate | Compilation must not depend on any external service | Must | G4 |
| NFR-10 | Privacy | No personal identifiers transmitted to the language-model service; only task-relevant content | Must | 3.6 |
| NFR-11 | Accessibility of client-visible text | Feedback and hints must avoid unexplained technical jargon where the target subskill is beginner-level | Should | WCAG [43] plain-language principle |
| NFR-12 | Reproducibility | Dependency versions pinned; all configuration supplied by environment; no committed secrets | Should | 3.7 |
| NFR-13 | Observability | Sufficient logging to reconstruct, for any graded event, the gate outcomes and the task context | Must | RQ1 analysis |
| NFR-14 | Maintainability | Layered separation of agents, routes, services, persistence and utilities; no cross-layer shortcuts | Should | 4.2 |

## 4.2 Component architecture within the complete solution

### 4.2.1 Position in the platform

The component is a stateless-with-respect-to-clients backend behind the
platform's identity boundary. It does not authenticate users itself; it
*verifies* tokens issued by the user service using a shared secret and
algorithm, resolving the student identifier from the token's claims. It does not
compute mastery; it consumes the analysis document produced by the knowledge
analysis component. Its own internal state is limited to transient connection
registries, which are caches rather than authorities — every durable fact lives
in the database. This is the property that makes the component horizontally
deployable in principle; Section 8.4 identifies it as a prerequisite for
scaling beyond a single instance.

### 4.2.2 Layered structure

**Figure 2.1** in Chapter 2 gave the conceptual framework. **Figure 4.1** gives
the software structure, which is a five-layer modular monolith.

```
+---------------------------------------------------------------+
|  transport: app/main.py                                      |
|  FastAPI app, Socket.IO ASGI wrapper, CORS, router registry, |
|  OpenAPI generation                                           |
+---------------------------------------------------------------+
|  interface: app/api/*.py                                     |
|  student | assessment | content | rag | peer | collab |         |
|  chat | individual_quiz | question_generator                   |
|  Responsibilities: HTTP and WebSocket contracts, request      |
|  validation, identity binding, response assembly, broadcast  |
+---------------------------------------------------------------+
|  agent: app/agents/*.py                                      |
|  student_agent (generation, grading, summarisation)          |
|  assessment_agent (javac / structural validation)            |
|  support_agent | moderator_agent | peer_matching              |
|  knowledge_rag | graph_workflow (LangGraph orchestrator)         |
|  Responsibilities: all language-model and compiler calls;    |
|  no HTTP, no database writes                                 |
+---------------------------------------------------------------+
|  retrieval: app/rag/*.py                                     |
|  document_loader (PDF -> chunks), vector_store (embed,       |
|  cosine retrieval, personalised content service)             |
+---------------------------------------------------------------+
|  persistence: app/services/mongodb.py                        |
|  lazy client, index creation, per-domain write helpers,      |
|  never-raising wrappers; app/config.py supplies settings      |
+---------------------------------------------------------------+
```

**Figure 4.1** Layered architecture of the peer-learning service. Dependencies
point downward only; the agent layer imports nothing from the interface layer,
which is what makes the agents unit-testable in isolation and what makes their
fallbacks substitutable.

Two boundaries are worth naming because they are the ones a reader is most
likely to assume are different. First, **the agent layer performs no persistence
of its own**; writes happen in the interface and persistence layers. Second,
**the persistence layer never raises**: `init_db` returns a boolean, and the
insert helpers log and return `None` on failure. This is deliberate — it is what
makes FR-21 satisfiable — and it has a cost discussed in Section 4.4.12: a
silently dropped write is indistinguishable from a successful one at the call
site unless the caller checks.

### 4.2.3 Data model

Thirteen collections are declared with their indexes at startup.

**Table 4.3** MongoDB collections, indexes and purpose.

| Collection | Indexes | Purpose |
|---|---|---|
| `students` | `student_id` | Learner records written by the platform |
| `student_analyses` | `student_id` | Imported mastery analyses; latest by `created_at` |
| `quiz_evaluations` | `student_id` | Quiz outcome records |
| `diagnostic_sessions` | `student_id`, `status` | Individual seven-task sessions, tasks, progress, results |
| `assessments` | `student_id` | Every code evaluation, with code, gate results and timestamps |
| `content_recommendations` | `student_id` | Generated remedial content |
| `peer_matches` | `student_id` | Match audit trail, including no-match records |
| `peer_notifications` | `student_id`, `status` | Match and session notifications, unread/read |
| `chat_sessions` | `room_id` | Discussion summaries |
| `collab_rooms` | `room_id` | Durable room document: code, participants, task sequence, progress, results, whiteboard |
| `collab_chat_messages` | `room_id`, `timestamp` | Room chat history |
| `peer_teaching_history` | `student_id`, `topic` | Prevents a peer teaching the same topic twice |
| `knowledge_chunks` | `chunk_index` | Embedded documentation chunks with metadata |

The `collab_rooms` document is the system's most important structure, because it
is simultaneously the room's durable state, the progression authority and the
answer to "what happened". Its significant fields are the participant
identifiers and names that determine role assignment, the seven-task sequence,
the current task and its zero-based index, the per-task progress array, the
attempted results, the mode discriminator that distinguishes a peer room from
an AI-teacher room, the whiteboard operation array, and timestamps.

## 4.3 Design alternatives and decisions

**Table 4.4** Design alternatives considered and decisions taken. The rejected
alternatives are recorded because the reasoning behind a rejection is part of
the contribution, and because several rejections are *provisional* — that is,
they were the right decision under the stated constraints and would change if
those constraints changed.

| # | Decision point | Alternatives | Chosen | Rationale | Provisional? |
|---|---|---|---|---|---|
| D1 | Service decomposition | Single monolithic service for all platform roles; microservice per agent; one service per pedagogical phase | One service, agents as internal modules | Agents share the same authenticated identity, the same analysis document and the same room state; splitting them would distribute the authoritative state for no benefit | No |
| D2 | Real-time transport for code and presence | HTTP polling; WebSocket; WebRTC data channel | WebSocket | Bidirectional, single connection, server-initiated broadcast needed; WebRTC requires signalling not otherwise needed; polling spends server capacity on idle checks | No |
| D3 | Drawing and free-form sync transport | Reuse the collaboration socket; separate Socket.IO channel | Separate Socket.IO channel, mounted as an ASGI wrapper | Drawing clients already ship a Socket.IO implementation; reuse would have forced the drawing vocabulary onto the assessment protocol and muddied FR-14's clarity | Partly |
| D4 | Code synchronisation semantics | CRDT; operational transformation; last-writer-wins relay | Last-writer-wins relay | Full CRDT is a substantial subsystem, and the pedagogical workload is *sequential* — the peer explains, then the learner edits | **Yes** — inadequate for simultaneous same-region editing; stated in 7.5 |
| D5 | Progression authority | Client-managed; server-managed with locks; server-managed with compare-and-swap | Server-managed with compare-and-swap | The server must be able to prove what each participant saw; CAS makes a duplicate submission a detectable 409 rather than a silent double-advance | No |
| D6 | Java validation | Regex heuristics only; native `javac`; remote execution sandbox; AST parse with tree-sitter | Native `javac` with a regex fallback | Only a real compiler is authoritative for syntax; the regex fallback preserves availability when no JDK is present and is reported as a weaker mode | No |
| D7 | Executing student code | Execute in a container; execute with seccomp; do not execute | Do not execute | A submitted program is hostile input by default; not executing removes the entire class of runtime attack at the cost of behavioural correctness, which is the cost stated in 7.5 | No |
| D8 | Grading architecture | LLM-only; deterministic-only; hybrid with both gates required | Hybrid, conjunction | Deterministic validation cannot judge whether code demonstrates a concept; an LLM alone is inconsistent and biased (2.3.2). Requiring both confines false passes to semantic misjudgement of compiling code, which is exactly what RQ1 measures | No |
| D9 | Task-item format | Multiple-choice; code completion only; seven-type code-only sequence | Seven-type code-only sequence | MCQ measures recognition (2.2.1); completion-only cannot measure repair, prediction or refactoring. The sequence spans construction, repair, prediction and refactoring | No |
| D10 | Task ordering | Generated order; difficulty-sorted; fixed type sequence | Fixed type sequence | A fixed sequence is auditable, comparable across cohorts and impossible for a generator to violate, which is what makes G1 a design guarantee rather than a prompt instruction | No |
| D11 | Peer matching | LLM-narrated selection; symmetric ability matching; complementary strength-gap matching with constraints | Deterministic complementarity | Matching is a constrained optimisation, not a judgement; determinism makes it testable, explainable and auditable. The LLM-based agent remains in the codebase for extension | No |
| D12 | Room state store | In-memory only; database only; in-memory registry with database authority | In-memory registry, database authority | Reads are on the hot broadcast path and must not touch the database; correctness requires the database to be authoritative; the split is what makes reconnect restoration correct | No |
| D13 | Structured model output | Free text plus regex repair; JSON mode; schema-constrained parsing | Schema-constrained parsing for the pedagogical agents, JSON mode for the RAG and summary agents | Constrained parsing removes an entire class of failure where the model returns prose where a structure was required, and it is the mechanism by which FR-04's guarantee is enforced at the boundary | No |
| D14 | Vector store | Embedded Chroma; hosted vector database; vectors in the application database with in-process cosine ranking | Vectors in the application database | The corpus is small (about 40 MB of documentation, a few hundred chunks); a hosted vector database adds a network dependency to a component whose principal virtue is offline degradation; exact cosine ranking is affordable at this scale | **Yes** — becomes inappropriate above roughly 10^5 chunks |
| D15 | Embedding and generation models | Largest available; small model | Small general-purpose model throughout | Task generation, grading and content generation are short-context structured-output workloads where the small model is adequate; cost per session is a first-order constraint on any at-scale deployment, and Section 8.4 records it as a scaling limit | **Yes** - re-evaluate as models improve |
| D16 | Failure behaviour on model error | Retry then fail; fail closed; fall back deterministically | Deterministic fallback | The diagnostic sequence must remain usable without network access, and refusing to serve a student because a third-party endpoint is down is unacceptable in an educational tool | Partly |

**Table 4.4** Design alternatives considered and decisions taken.

Three rows in **Table 4.4** deserve expansion because they are the decisions a
reader is most likely to challenge.

*D4, last-writer-wins.* The component relays each code-change message to the
other participant and overwrites the room's code state. If both participants
type within the same interval, one edit is lost. This is a real defect relative
to collaborative-editing standards and it was accepted deliberately, on the
grounds that the pedagogical task is *explain-then-edit* rather than
*simultaneously-edit*: in the observed sessions the peer teacher types to
demonstrate and the learner types to attempt, and these do not overlap. The
honest position, stated again in Section 7.5, is that the component is a
pedagogical instrument with an editor attached, not a replacement for one.

*D11, deterministic matching.* The obvious alternative — ask a model which peer
is best — was rejected because model selection is unreproducible, cannot be
audited by an instructor who asks "why these two?", and can vary between
identical requests. The deterministic matcher instead produces an explainable
decision: "student B was selected because their analysis reports a strength in
Java Exception Handling with a mastery score of 88, and they have not yet taught
that topic to student A." An instructor can verify that claim. An instructor
cannot verify a model narrative.

*D16, fallback rather than fail-closed.* Fallback preserves availability at the
cost of validity, because the deterministic fallback tasks do not target the
learner's specific subskill. The design resolves the tension by making the
degradation *visible*: **Table 4.8** specifies which operations degrade, and
NFR-07 requires degraded-mode sessions to be reported separately in results. A
system that silently degraded would be worse than one that failed, because its
outputs would be indistinguishable from valid ones.

---

## 4.4 Detailed design

### 4.4.1 Authentication and authorisation

A single FastAPI dependency, `verify_jwt_student`, performs the whole of REST
authorisation: it requires an `Authorization: Bearer` header, decodes the token
with the configured secret and algorithm, verifies expiry, and resolves the
student identifier from the first present claim among `sub`, `student_id`,
`studentId`, `user_id`, `id`, `userId`. The claim tolerance is a deliberate
accommodation of the user service's claim naming, which this component does not
control.

A second function, `decode_student_token`, exposes the same logic without the
HTTP dependency, for use in WebSocket handshakes where header-based
authentication is unavailable. Both are reused by the collaboration and
discussion endpoints.

Beyond authentication, three identity-binding checks are enforced and each
corresponds to a real attack. Import rejects a body whose `student_id` differs
from the token's (FR-01). Analysis retrieval rejects a path parameter that
differs from the token's (FR-02). The collaboration WebSocket compares the
resolved identity against the room document's participant set and closes the
connection with code 1008 for a non-member, which prevents an authenticated
student from joining and observing any room, including its locked task progress.
The discussion WebSocket additionally requires that the student identifier in
the path equal the token's, preventing a student from posting to another
student's discussion channel by URL manipulation.

### 4.4.2 Mastery-analysis ingestion

The import endpoint accepts a schema-validated document: version, student
identifier, data-source flags, a mastery profile containing an overall score, a
list of knowledge gaps each with topic, gap type, confidence, mastery score,
weak subskills, misconceptions, observed error patterns and an optional
suggested intervention, plus strengths and recommendations. Validation is
structural, performed by Pydantic models, and the stored document is
denormalised: knowledge gaps and strengths are additionally written at the top
level so that read paths do not have to traverse the profile.

The endpoint's behaviour on identity mismatch is the design's most important
choice here, and it is a refusal rather than a correction: a mismatch returns
403 rather than overwriting `student_id` with the token's. Silently trusting the
token would let a student with a valid token write a mastery profile onto
another student's record, which would corrupt both the diagnosis and the peer
matching that depends on it.

### 4.4.3 Diagnostic session state machine

The component maintains two parallel state machines over the same task model:
one for an individual diagnostic session, one for a collaboration room. They
share the task-progression invariants but differ in who may act and in what the
completion means. **Figure 4.3** shows the room state machine, which is the
richer of the two.

```
                    room created (peer match or AI-teacher setup)
                                     |
                                     v
                          +--------------------+
                          |  in_progress       |<----------------+
                          |  current_task = 1  |                 |
                          +--------------------+                 |
                                     |                            |
                     attempt submitted |                            |
                                     v                            |
                        +------------------------+   gate fail     |
                        |   evaluate submitted  |---------------+  |
                        |   code                |                  |
                        +------------------------+                  |
                                     |                            |
                              both gates pass                       |
                                     v                            |
                          +--------------------+                    |
                          | task passed        |                    |
                          | attempts -> 0      |                    |
                          | next task unlocked |                    |
                          | starter code set   |                    |
                          +--------------------+                    |
                                     |                            |
                    last task (n = 7) passed                       |
                                     v                            |
                          +--------------------+                    |
                          |  status = completed|<-------------------+
                          |  sequence_complete |   (replay only)
                          +--------------------+
                                     |
                                     v
                          summary generated, returned to client
```

**Figure 4.3** Diagnostic session and collaboration-room state machine. The
only transition that leaves `in_progress` other than task passage is completion;
the only transition that changes the current task is a passing submission.

Five invariants govern the machine and each is enforced in code rather than
assumed:

* **I1 — Monotonic progression.** The current task index never decreases. There
  is no backwards transition, and client-initiated navigation is refused.
* **I2 — Conjunctive gating.** A task is marked passed only if the deterministic
  gate returned valid and the grading gate returned pass.
* **I3 — Attempt monotonicity within a task.** The attempt count increments on
  every submission and resets to zero only when the next task is unlocked.
* **I4 — Redaction.** No response contains the description, starter code or
  criteria of a task beyond the current one.
* **I5 — Single-writer transitions.** A transition is applied only if the stored
  document still matches the expected current task and status.

Invariant I5 protects against a genuinely damaging failure — a double
submission, from an impatient user or a retrying client, advancing a learner two
tasks and marking an unattempted task as complete. The mechanism is an atomic
conditional update; if it matches no document, the service returns 409 and the
caller is told to reload.

### 4.4.4 Task generation and sequencing

The generator produces exactly seven tasks, one per type, all targeting one
subskill, in a fixed order. The order and its cognitive-demand mapping are given
in **Table 4.5** and **Figure 4.2**.

**Table 4.5** Diagnostic task types, cognitive demand and intended evidence.

| # | Task type | Learner action | Bloom level [5] | Miller level [4] | Evidence sought |
|---|---|---|---|---|---|
| 1 | `write_code` | Construct a program from a skeleton | Create | Does | Can they produce the construct unaided? |
| 2 | `complete_missing_code` | Fill specified gaps in a partial program | Apply | Shows how | Can they supply a missing component in context? |
| 3 | `fix_incorrect_code` | Locate and correct a logic error | Analyse | Does | Can they find a defect in plausible code? |
| 4 | `debug_error` | Diagnose and repair a runtime failure | Analyse | Does | Can they connect an error message to a cause? |
| 5 | `predict_and_correct_behavior` | Predict an output, then correct the behaviour | Analyse / Evaluate | Does | Do they hold a correct mental model of execution? |
| 6 | `implement_method` | Implement a specified interface | Create | Does independently | Can they honour a contract with edge cases? |
| 7 | `improve_solution` | Refactor working but poor code | Evaluate | Does | Do they recognise quality defects? |

**Table 4.5** The seven task types with their cognitive-demand mapping and the
evidence each is designed to elicit.

```
  cognitive demand
  high |                                          [7] improve_solution
       |                                 [6] implement_method
       |                        [5] predict_and_correct
       |               [3] fix  /  [4] debug_error
       |      [2] complete_missing_code
       | [1] write_code
  low  +------------------------------------------------------> scaffold density
       |  most guidance                              least guidance
```

**Figure 4.2** Task-type sequence and Bloom's revised taxonomy mapping. The
sequence moves from maximum scaffold to minimum, which is the reverse of the
order in which cognitive demand rises; this is deliberate and is what makes the
sequence a *scaffolded* diagnostic rather than a uniform one. A learner failing
task 1 has a different diagnosis from a learner failing task 6, and only the
graded sequence distinguishes them.

This last point is the reason D10 chose a *fixed* type order over
difficulty-sorted generation. If task order varied per learner, the attempt
pattern would no longer be interpretable across a cohort, and the component
would lose the aggregate evidence that the whole design exists to produce.
Every learner in every cohort attempts the same seven cognitive demands in the
same order; only the surface content differs.

The generation prompt specifies the types, the shared subskill, the requirement
counts, the hint count and the prohibitions — no multiple-choice items, no
complete solution, TODO markers in starter code, progressive difficulty. The
prohibitions are what D13's mechanism enforces at the boundary: because the
model's output is parsed against a fixed schema, a task missing a required field
is a parse failure rather than a silently incomplete task.

The fallback task set is a hard-coded seven-task sequence covering exception
handling, null safety, catch ordering, custom exceptions and
try-with-resources. It is pedagogically sound but **not gap-targeted**, which is
precisely why NFR-07 requires fallback usage to be reported.

### 4.4.5 The two-gate evaluation pipeline

**Figure 4.4** shows the pipeline. A submission passes through the deterministic
gate and the grading gate, and the conjunction of the two is the only route to
progression.

```
  POST /api/assessment/evaluate { "code": "..." }
                  |
                  v
      +---------------------------+
      | GATE 0  empty / class     |  fail -> is_valid=false, no model call
      | structure precondition    |
      +---------------------------+
                  |
          +-------+-------+
          |               |
     javac present    javac absent
          |               |
          v               v
  +--------------+  +-------------------+
  | write source |  | bracket balance   |
  | to temp dir, |  | main-method shape |
  | filename from|  | semicolon check   |
  | declared     | +-------------------+
  | class; javac |         |
  | 10s timeout  |    mode reported
  +--------------+         |
          |               |
          +-------+-------+
                  |  is_valid
                  v
      +---------------------------+
      | GATE 1  grading            |  task description + evaluation
      | model judges against      |  criteria + topic + subskill
      | stored criteria           |  -> grade, feedback, sample approach
      +---------------------------+
                  |
                  v
      +---------------------------+
      | passed = is_valid AND     |
      |          grade == "pass"  |
      +---------------------------+
                  |
         +--------+--------+
         |                 |
      passed            failed
         |                 |
         v                 v
  attempts reset,    attempts++, task
  next unlocked,     stays active,
  starter loaded     feedback + hint
         |                 |
         +--------+--------+
                  |
                  v
        conditional update on
      (current_task, status)
                  |
          no match -> 409
```

**Figure 4.4** Two-gate evaluation pipeline. Gate 0 is a precondition, not a
gate: it rejects structurally impossible submissions without a model call,
which saves both latency and cost on the most common failure mode.

Three design properties of this pipeline are worth drawing out.

*The deterministic gate is authoritative and must be.* If it rejects, the grader
is never called. This has three consequences: it saves cost on failing
submissions, it removes the possibility of a model passing code that does not
compile, and it makes the system's behaviour on malformed input fully
deterministic and therefore testable without a model.

*The grading gate is advisory in structure but binding in effect.* Its output
carries a sample-approach field specified as a description rather than code,
which is the mechanism implementing the no-solution rule. FR-07 requires failed
submissions to return a hint rather than a solution, and the summarisation
schema enforces the same rule in the session summary.

*The conjunction is the security-relevant property.* Because both gates must
succeed, a false pass requires the model to be wrong about code that *does*
compile. This narrows the false-pass surface to semantic misjudgement of
compiling code and excludes, entirely, false passes of code that does not
compile. RQ1 measures the residual.

### 4.4.6 Deterministic Java validation

The validator performs, in order: an emptiness check; a class-declaration
check; and then either compilation or structural fallback.

*Compilation path.* The declared class name is extracted from the source by
regular expression, defaulting to `Main` when absent; the source is written to a
temporary directory under that name; `javac` is invoked with a ten-second
timeout; a non-zero exit yields the compiler's diagnostics, filtered to remove
note lines, as the error list; a timeout yields a specific timeout message. The
temporary directory is removed when the context exits. No client-supplied
string is used as a path component, and the program is never executed.

*Structural fallback path.* When no JDK is present the service checks bracket
balance for all three bracket pairs, checks for main-method tokens as a proxy for
a method shape, strips string literals so that punctuation inside them cannot
trigger false positives, and applies a regular expression for
statement-terminating semicolons. This is strictly weaker than compilation and
the service reports which mode was used, because NFR-07 makes mode a
first-class property of the result rather than an implementation detail.

*Complexity heuristic.* The service returns a loop-count-derived complexity
estimate: no detected loops gives constant, one detected loop gives linear, and
multiple give a power. This is a heuristic and it is wrong in identifiable ways
— a loop with a fixed bound is not linear, and a recursive method has no loop at
all. It is retained because it is pedagogically useful as a prompt for
discussion, and it is disclosed as a heuristic wherever it appears.

*Compiler availability is determined once, at import time*, and the decision is
logged. This is a deliberate economy — probing on every submission would add
latency for no benefit — with the consequence that installing a JDK requires a
restart to take effect.

---

### 4.4.7 Peer matching

The matcher operates on a student's analysis and the analyses of candidate
peers. It proceeds in five steps.

**Step 1 — Topic selection.** The learner's first knowledge gap whose weak
subskill is a teachable concept defines the topic. The scoring is retained
per-skill so that the assignment step is informative rather than binary.

**Step 2 — Candidate filtering.** A peer is excluded if it is the requester;
if its analysis lacks a peer-eligible status; if its own activity indicates it
is unavailable or offline; if it is already in an active collaboration; or if
the teaching history records that it has already taught that topic to this
learner. The last exclusion is the one that prevents the system from repeatedly
pairing the same strong student with the same struggling student.

**Step 3 — Complementarity scoring.** For each surviving candidate, the score
combines the candidate's mastery of the topic's subskill with a topicality term
rewarding a stated gap in the same topic and a supplementary term for
adjacent-topic strength. The weights are fixed and documented, and the top
candidates are returned with their scores so that the decision is inspectable.

**Step 4 — Assignment.** Each candidate is recorded in `peer_matches` with
status, score and timestamp, including the *no-match* case. This is what makes
"the system found no partner" an auditable event rather than an absence of
evidence.

**Step 5 — Room creation and notification.** The matcher is invoked from the
collaboration route, which creates the room with role assignment, seeds the task
sequence, writes the room document and notifies both participants with the room
identifier.

**Table 4.6** Peer matching filters, with the threat each excludes.

| Filter | Excludes | Consequence if omitted |
|---|---|---|
| Self-exclusion | Pairing a student with themselves | Absurd session; wastes a match |
| Peer-eligibility status | Candidates not seeking or offering peer sessions | Sessions with unwilling participants |
| Availability/activity | Offline or busy candidates | Immediate abandonment; degraded throughput |
| Active-session exclusion | Students already in a room | One student in two rooms; corrupted room state |
| Repeat-teaching history | The same pair on the same topic | Exhausts the strong student's capacity; loops the same pairing |

**Figure 4.5** summarises the decision flow.

```
   GET /api/peer/match
            |
            v
   +------------------------+
   | load requester's      |
   | analysis; extract     |
   | topic from first gap  |
   +------------------------+
            |
            v
   +------------------------+
   | candidate set          |
   | filter, in order:      |
   |  self                  |
   |  peer-eligible status  |
   |  availability          |
   |  active session        |
   |  prior teaching        |
   +------------------------+
            |
            v
   +------------------------+
   | complementarity score  |
   |  w1*topic mastery      |
   | + w2*gap topicality    |
   | + w3*adjacent strength |
   +------------------------+
            |
            v
   +------------------------+
   | no survivors?          |--yes--> record no_match -> 404
   +------------------------+
            | no
            v
   +------------------------+
   | assign top candidate;  |
   | record match + score;  |
   | write teaching ledger  |
   +------------------------+
            |
            v
   +------------------------+
   | create room, seed 7    |
   | tasks, notify both     |
   +------------------------+
```

**Figure 4.5** Complementarity-based peer-matching decision flow. Every branch is
deterministic given the analysis documents, and the no-match path is recorded
rather than silently returning empty.

The deterministic nature of this algorithm is the substance of D11, and it has a
consequence that is easy to miss: because the scoring is fully determined by the
analysis documents, **the quality of peer matching is bounded by the quality of
the knowledge analysis**. If the analysis misidentifies the subskill, the
matcher will confidently match the wrong pair. This dependency is stated in
Chapter 7 as a threat to validity of any future peer-matching evaluation.

### 4.4.8 Collaboration rooms and real-time state

Room creation seeds the seven-task sequence, the current task and index, the
progress array, the two participants with their names and roles, the mode, and
the empty whiteboard array. Roles are assigned by name and by position, so the
learner is identified consistently rather than by whichever socket connected
first.

The collaboration WebSocket implements the following message vocabulary:

**Table 4.7** Collaboration WebSocket message vocabulary.

| Message | Direction | Effect |
|---|---|---|
| `INIT_STATE` | server -> client | Room state on connection, with locked tasks redacted |
| `JOIN` | client -> server | Announce presence with a name |
| `CODE_CHANGE` | client -> server | Relay code to the peer; update room code; broadcast |
| `TASK_REQUEST` | client -> server | Refused with `TASK_LOCKED`; the server is the only progression authority |
| `TASK_PROGRESS` | server -> client | Broadcast current task and index whenever they change |
| `ATTEMPT_RESULT` | server -> client | Broadcast a graded result to both participants |
| `CHAT_MESSAGE` | client -> server | Persist and broadcast a room message |
| `WHITEBOARD_OP` | client -> server | Persist and broadcast a drawing operation |
| `CURSOR_MOVE` | client -> server | Relay cursor position and label; not persisted |
| `PEER_LEFT` / `PEER_JOINED` | server -> client | Presence transitions |
| `AI_TEACHER_MESSAGE` | bidirectional | AI-tutor explanation mode within the room |

**Figure 4.6** shows the exchange for a single graded attempt, which is the
sequence that carries the pedagogical meaning.

```
  Learner client                Server                     Peer client
       |                          |                              |
       |-- WS connect + token -->| verify token                  |
       |<-- INIT_STATE (current  |  (locked tasks redacted)      |
       |     task only) ----------|                              |
       |                          |<------- WS connect -----------|
       |                          |                              |
       |-- CODE_CHANGE ---------->| persist code, relay -------->|
       |<-- CODE_CHANGE -----------|------- broadcast -----------|
       |                          |<-- CODE_CHANGE -------------|
       |                          |                              |
       |-- TASK_REQUEST --------->| refuse TASK_LOCKED           |
       |<-- TASK_REQUEST_REFUSED-|  (server owns progression)   |
       |                          |                              |
       |-- POST /evaluate ------>| Gate 0: javac / structural    |
       |                          | Gate 1: LLM grading           |
       |                          | CAS update on (task, status)  |
       |<-- result + feedback ----|<--- ATTEMPT_RESULT broadcast-|
       |                          |                              |
       |                          |<-- CHAT_MESSAGE --------------|
       |                          | persist + broadcast --------->|
       |<-- CHAT_MESSAGE ----------|                              |
```

**Figure 4.6** Real-time collaboration message exchange for one graded attempt.
The refused `TASK_REQUEST` is the visible expression of server authority (D5):
no client may advance the shared sequence, and broadcasting the attempt result is
what keeps the peer teacher's view of the session correct.

The design consequences of this vocabulary are as follows.

*Persistence is selective.* Code changes, chat and whiteboard operations are
persisted; cursor positions are not. Cursor traffic is the highest-frequency
message in the system and persisting it would multiply write volume for a purely
ephemeral concern. The design's rule is that the room document must be
sufficient to reconstruct the session, and cursor positions are not part of the
session's content.

*Redaction happens at the boundary, not in the client.* `INIT_STATE` is
assembled server-side with only the current task's description, starter code and
criteria. A client that receives the document containing all seven tasks and
chooses to read ahead is not blocked, because the redaction is the response
construction, not an attempt at secrecy against a malicious client. The
justification is pedagogical and pedagogical-integrity based: the learner
should not see the later tasks, and the server should not be the only thing
preventing that. This is stated honestly in Chapter 7 as a limitation rather
than a control.

*Reconnect restoration is derived from the document.* On connection the server
returns the current task, progress, code, whiteboard and chat. Because all of
these are in the document, restoration is a read rather than a reconstruction
from connection history — which is why D12 chose a database authority.

*TASK_REQUEST being refused is the visible half of D5.* A client that tries to
advance its own view is told plainly that the server decides. This is
unusual — most collaborative tools let any client move the shared state — and it
is what makes the room's progression evidence defensible.

### 4.4.9 Whiteboard, cursors and Socket.IO

Drawing uses a separate Socket.IO channel rather than the assessment protocol
(D3). The operations are line, rectangle, ellipse, text, freehand, eraser,
clear, undo, redo and image. Colour and stroke width are carried per operation.
Undo and redo are implemented as server-side cursor movement over the
persisted operation array, not as an inverse-operation log — a simpler scheme
that is correct as long as the operation array is the single source of truth.

Named cursors are throttled by the server on a per-connection interval and are
labelled with the participant's name, so that each participant can see where the
other is pointing. This is the feature that most directly supports the
explanation that the pedagogical design depends on: without it, "look here" is
untransmittable.

### 4.4.10 AI-teacher mode

A room can be created in AI-teacher mode, in which the learner works with the AI
tutor rather than a human peer. The same task sequence, the same two gates and the
same progression rules apply. The AI tutor receives the current task, the
learner's code and recent history, and replies with an explanation. Mode is
carried on the room document, so an observer reading the data can distinguish a
peer session from an AI session — which is essential for the evaluation design
in Chapter 6, since only one of the two arms is expected to show human
collaboration effects.

### 4.4.11 Retrieval-augmented content

The loader reads the bundled PDF once, splits it into chunks of approximately
one thousand characters with overlap, embeds each chunk, and stores the vector
with its metadata. Retrieval embeds the query, ranks the corpus by cosine
similarity using NumPy over stored vectors, and returns the best chunks with
their source and score. The content service composes a response from the
retrieved context, the student's gap and the retrieved material.

Two consequences follow from D14 and are visible in the code. First, because
retrieval is in-process over stored vectors, the service needs no vector database
at runtime, but it must have ingested the corpus before it can retrieve anything;
if ingestion has not run, retrieval returns nothing and the response degrades to a
general explanation. Second, because a single general-purpose embedding model
serves both ingestion and query, index and query spaces are guaranteed
consistent — the class of bug that arises when ingestion and query use different
models cannot occur here.

The presence of a Chroma-style artefact directory in the component is recorded
in Chapter 7 as repository hygiene rather than as a dependency: the requirement
is declared but no code path imports it, so the artefact is inert.

### 4.4.12 Persistence, degradation and error handling

The database client is created lazily on first use, and index creation is
attempted at startup and at module import, with failures logged rather than
raised. Write helpers are written per domain — analyses, assessments, content,
matches, notifications, sessions, chat, rooms — and each returns `None` on
failure instead of propagating.

This design satisfies FR-21 and it has a cost that must be stated rather than
hidden. A caller cannot distinguish "inserted" from "silently dropped" by return
value alone. The mitigations are: writers that need certainty check the return;
all helpers log at error level; and the health endpoint reports connection
status. A more robust design would return a typed result and let routes decide,
which is the remediation recorded in Section 7.5.

Error responses are consistent: 400 for malformed input, 401 for missing or
invalid authentication, 403 for identity mismatch or non-membership, 404 for
absent resources, 409 for a conditional-update miss, 422 for schema violation,
500 for an unexpected failure, and 503 when a required backing service is
unavailable. Timeouts on external calls are bounded, and the LLM call timeout is
set at the client configuration level so that a slow model cannot hold a request
open indefinitely.

**Table 4.8** Degraded modes: operation, trigger, behaviour and consequence.

| Operation | Trigger | Behaviour without the dependency | Consequence |
|---|---|---|---|
| Task generation | Model unavailable | Hard-coded seven-task sequence | Not gap-targeted; reported as fallback |
| Grading | Model unavailable after validation | Deterministic structural score | Cannot judge conceptual correctness |
| Session summary | Model unavailable | Templated summary from local state | Loses natural-language quality |
| Content generation | Model unavailable | Generic explanation assembled from the gap | Not grounded in the retrieved corpus |
| Content retrieval | Corpus not ingested or model unavailable | Empty context | Content degrades to a general answer |
| Compiler | No JDK present | Structural validation | Accepts some invalid programs; rejects some valid ones |
| Database | Unavailable at startup | Service runs; writes dropped and logged | Features degrade individually, not wholly |
| Matching | Analysis documents absent | No-match response | Auditable as `no_match`, not as silence |

**Table 4.8** Degraded modes. Every row is a deliberate design decision, and the
final column is the honest cost of the availability guarantee.

**Figure 4.7** shows the shared decision pattern behind every row in
**Table 4.8**.

```
        operation invoked
               |
               v
      +---------------------+
      | dependency healthy? |
      +---------------------+
         | yes           | no / timeout / unparseable
         v               v
   normal path      +-------------------------+
                    | deterministic substitute |
                    | available?               |
                    +-------------------------+
                       | yes           | no
                       v               v
                  fallback path    503 service
                  + tag result    unavailable
                    as degraded
```

**Figure 4.7** Degraded-mode decision flow for LLM-dependent operations. The
fourth branch — dependency down *and* no substitute available — is the only
path that fails a request, and it corresponds to the row in **Table 4.8** where
the backing service itself is unavailable. Every other path returns a usable
response whose degraded status is recorded, which is what NFR-07 requires.

### 4.4.13 Support, moderation, quiz and question generation

Four supporting capabilities complete the component.

*The support assistant* answers a learner's question with their knowledge-gap
context attached, so that a generic question receives a specific answer. It uses
JSON-mode structured output and falls back to a templated response.

*The moderator agent* produces a topic-grounded summary of a discussion, which
is what turns a chat transcript into a study artefact. It falls back to a
templated summary built from local state.

*The individual quiz route* serves an isolated quiz flow for testing purposes,
with deterministic item selection. Its sessions are currently held in process
memory rather than the database, which FR-23 targets as remediation.

*The question generator* produces multiple-choice questions for a topic with an
explanation and difficulty tag, seeded from the authenticated student's analysis
so that the questions follow their gaps. It uses JSON mode and a deterministic
fallback.

*The knowledge-RAG workflow* is a LangGraph orchestrator with two nodes —
retrieve, then generate — connected by a conditional edge that answers from
retrieved context or falls back to general knowledge when retrieval returns
nothing. It is included as a demonstrated pattern of an agent graph rather than
as a user-facing feature of the diagnostic path.

## 4.5 Standards and professional practice

A design is not standards-conformant by assertion; it is standards-conformant by
demonstrable conformance to named criteria. **Table 4.11** records the standards
and professional guidance the component was designed against, the specific
requirement drawn from each, and where conformance is evidenced. Where
conformance is partial or unverifiable, that is stated rather than implied by
omission.

**Table 4.11** Standards and professional practice conformance.

| Standard or guidance | Requirement applied | Design evidence | Conformance status |
|---|---|---|---|
| ISO/IEC 25010:2011 [22] | Product quality model; the quality characteristics the component is measured against in RQ4 | Section 4.4 and Chapter 5 implement and instrument the functional, reliability, performance-efficiency, security and usability characteristics named there | Implemented; measurement specified, not yet executed |
| ISO/IEC 25010:2011 [22] | Maintainability as a quality characteristic | Five-layer separation, no cross-layer imports, 16 decision records in **Table 4.4** with rejected alternatives documented | Implemented |
| WCAG 2.2 [43] | Plain-language comprehensibility of learner-facing output; no unexplained jargon for beginner subskills | FR-07 and NFR-11; feedback and hint fields returned separately from technical compiler diagnostics | Partial; client-side conformance is outside the component boundary |
| WCAG 2.2 [43] | Status must not be conveyed by colour alone | Task pass/fail is returned as a discrete `task_passed` boolean and a `grade` string, not as a colour signal | Implemented |
| PEP 8 [39] | Python style, naming and module organisation for the language used | Four-space indentation, `snake_case` functions, module names matching their responsibility | Applied throughout, not tool-enforced |
| Semantic versioning, SemVer 2.0.0 | Versioned interface; breaking-change discipline for the shared API contract | OpenAPI document generated at start-up; version carried in the deployment image tag | Partially applied; version pinning is defective (Section 3.7) |
| Twelve-factor App, factor III (Config) | Configuration supplied by environment, not baked into the artefact | All secrets and endpoints read from environment variables; `.env` excluded from version control | Implemented |
| Twelve-factor App, factor IV (Backing services) | Backing services addressable and replaceable by resource identifier | MongoDB addressed by connection string; the vector store is replaceable by D14 | Implemented |
| Twelve-factor App, factor VII (Port binding) | Service exports HTTP and WebSocket as ports, not as a daemon | Uvicorn binding in `Dockerfile`; no daemon, no service manager, no write-ahead log | Implemented |
| Twelve-factor App, factor X (Logs) | Logs as event streams, not files | Structured logging to stdout, captured by the container runtime | Implemented |
| OWASP ASVS 4.0.3, V2 Authentication | Authentication at every protected endpoint; token verification cannot fail open | `verify_jwt_student` dependency on all protected REST routes; explicit 401 on missing, invalid or expired token | Implemented |
| OWASP ASVS 4.0.3, V4 Access control | Authorisation on every request for a restricted resource, including non-HTTP transports | Token-to-path identity binding on analysis import and retrieval; room-membership check closing WebSocket with 1008 | Implemented for identity and room scope; see Section 7.5 for the absence of role-based authorisation |
| OWASP Top 10 (2021), A03 Injection | No interpreter receives untrusted input in a command string | Submitted code is written to a temporary file and compiled by path; no submitted string is interpolated into a shell command | Implemented |
| OWASP Top 10 (2021), A03 Injection | Code returned to the model must not be executed | Submitted code is compiled but never run (D7) | Implemented |
| OMG Model Driven Development, MOF 2.x | Interchange is by schema, not by ad-hoc text | Pydantic request and response models; structured model output with a constrained schema (D13) | Applied |
| GDPR, Art. 5(1)(c) Data minimisation | Only data necessary for the stated purpose | Task-relevant content only is sent to the model; no direct identifiers; JWT-verified identity used for access control | Implemented for the model path; chat logs retained in full (Section 7.5) |
| GDPR, Art. 32 Security of processing | Appropriate technical measures for pseudonymised personal data | Shared-secret JWT, transport encryption assumed at the ingress, CORS permissive only in development | Partial; CORS is a deployment risk (Section 7.5) |
| IEEE 1012-2016 | Verification and validation planned with defined pass criteria | Section 5.4 defines the test strategy, coverage scope and honest reporting of suite status | Partially implemented; see Section 5.4 |

**Table 4.11** Standards and professional practice conformance. Three rows are
marked partial or partially applied, and those three are discussed as risks
rather than presented as conformances.

Four of these entries warrant comment, because each is a place where a
reasonable reader could reasonably expect a stronger claim than the design can
support.

*WCAG conformance is bounded by the component boundary.* The service returns
structured status, and the display of that status is the client's
responsibility. The component can guarantee that pass/fail is available as a
discrete value rather than as a colour; it cannot guarantee that a client will
use it accessibly. Claiming full WCAG conformance for a backend would be an
error, so the claim is scoped to what the backend actually controls.

*Authentication is implemented; authorisation is partial.* Identity is verified
on every protected route and bound to the resource on every request, which
prevents the horizontal-privilege failures that these APIs are usually exposed
to. What is absent is role-based authorisation: there is no instructor or
administrator role, and no route is restricted by role rather than by identity.
Section 7.5 records this as a threat rather than a design choice, because it is
a limitation of scope, not a considered trade-off.

*The two reproducibility defects contradict the standards above.*
Twelve-factor factor III and SemVer both assume a build that can be reproduced
and a version that can be trusted, and neither currently holds. This tension is
stated here rather than in a footnote because the honest position is that the
component conforms to the *intent* of several of these standards while failing
two concrete checks, and a table that recorded only the intentions would
misrepresent the position.

*Injection defence is structural rather than filtered.* The command-injection
defence does not sanitise submitted code or attempt to recognise dangerous
constructs; it writes the submission to a file and passes a path to the
compiler, so no submitted string ever reaches a command line. This is a stronger
position than filtering, and it is also cheaper to verify, because there is no
pattern list to bypass.

## 4.6 Design traceability

Traceability is the property that lets a reviewer confirm that a requirement was
implemented rather than merely stated. **Table 4.12** maps each functional
requirement from **Table 4.1** to the module that implements it, so that every
claim of the form "FR-nn is satisfied" can be checked by opening one file.

**Table 4.12** Requirement-to-implementation traceability.

| Requirement | Implementing module | Primary verification |
|---|---|---|
| FR-01 | `app/api/student_routes.py` | Identity-mismatch rejection path |
| FR-02 | `app/api/student_routes.py` | Latest-analysis retrieval path |
| FR-03 | `app/agents/student_agent.py` | Type-sequence assertion in `generate_all_diagnostic_coding_tasks` |
| FR-04 | `app/agents/student_agent.py` | Structured-output schema for task fields |
| FR-05 | `app/api/collab_routes.py` | `INIT_STATE` construction with task redaction |
| FR-06 | `app/api/assessment_routes.py` | Conjunction in the task-passed decision |
| FR-07 | `app/api/assessment_routes.py` | Attempt increment and hint field on failure |
| FR-08 | `app/api/assessment_routes.py` | Conditional update filter on `(current_task, status)` |
| FR-09 | `app/agents/assessment_agent.py` | `javac` path and structural fallback, with reported mode |
| FR-10 | `app/agents/assessment_agent.py` | Absence of any execution call in the validation path |
| FR-11 | `app/agents/peer_matching.py` | Filter chain and complementarity scoring |
| FR-12 | `app/api/collab_routes.py` | Room creation and dual notification |
| FR-13 | `app/api/collab_routes.py` | WebSocket message handlers and reconnect restoration |
| FR-14 | `app/api/collab_routes.py` | `TASK_REQUEST` refusal with `TASK_LOCKED` |
| FR-15 | `app/api/collab_routes.py` | Broadcast on task progress change |
| FR-16 | `app/rag/vector_store.py` | Content service composing retrieved context |
| FR-17 | `app/api/chat_routes.py` | History retrieval, persistence and summary |
| FR-18 | `app/api/individual_quiz_routes.py` | Deterministic item selection and session handling |
| FR-19 | `app/agents/support_agent.py` | Gap context attached to the support request |
| FR-20 | All agent modules | Fallback branch in each LLM call site |
| FR-21 | `app/services/mongodb.py` | Non-raising wrappers on every write helper |
| FR-22 | `app/main.py` | Health route and OpenAPI configuration |
| FR-23 | `app/api/individual_quiz_routes.py` | Session storage; currently process-memory only |

**Table 4.12** Requirement-to-implementation traceability. FR-23 is the one
requirement this component does not currently satisfy; Section 7.5 records it as
a remediation item.

The non-functional requirements are traced through measurement rather than
through files, and those measurements are specified in Chapter 5 and executed in
Chapter 6. That asymmetry is intentional: a latency target is satisfied or not
satisfied by observation, not by reading code, and this thesis does not yet have
the observations.

## 4.7 Interface and API design

### 4.7.1 Design conventions

All endpoints are prefixed by domain, return JSON, and are documented
automatically. Errors follow the mapping in Section 4.4.12. Authentication is a
dependency, so an endpoint's security is visible in its signature rather than in
its body. Long-running connections are WebSocket; drawing is Socket.IO.

### 4.7.2 Endpoint inventory

**Table 4.9** REST operations grouped by domain, as registered by the composed
application.

| Domain | Prefix | Count | Operations |
|---|---|---|---|
| Student onboarding | `/api/student` | 5 | `onboard-and-diagnose`, `diagnostic-session/reset`, `diagnostic-session/status`, `import-analysis`, `analysis/{student_id}` |
| Assessment | `/api/assessment` | 1 | `evaluate` |
| RAG content | `/api/rag-content` | 1 | `recommend` |
| Peer matching | `/api/peer` | 5 | `match`, `notifications`, `notifications/{notification_id}/read`, `notifications/read-all`, `notifications/{notification_id}/unread` |
| Chat and moderation | `/api/chat` | 2 | `support`, `summarize-session` |
| Collaboration | `/api/collab` | 4 | `rooms`, `rooms/{room_id}/state`, `initialize-session`, `setup-ai-session` |
| Individual quiz | `/api/individual-quiz` | 3 | `start`, `submit-answer`, `summary/{session_id}` |
| Question generator | `/api/question-generator` | 2 | `generate`, `evaluate` |
| Legacy content | `/api/content` | 1 | `recommend` (retained for client compatibility) |
| Service root | `/` | 1 | `root_status` health banner |
| **Total** | | **25** | |

**Table 4.9** REST operations grouped by domain, totalling twenty-five operations
across ten route groups. Three further router modules exist in the source tree but
are not registered with the composed application; Section 5.3 records this as an
integration defect rather than as available surface.

**Table 4.10** Long-lived connection endpoints.

| Endpoint | Protocol | Purpose |
|---|---|---|
| `/api/collab/ws/collab/{room_id}?token=...` | WebSocket | Collaboration room: code sync, tasks, presence, cursors, chat, whiteboard |
| `/api/chat/ws/{room_id}/{student_id}?token=...` | WebSocket | Topic discussion with moderation, persistence and summarisation |
| `/socket.io` | Socket.IO | Whiteboard line, canvas clear and room join events |

**Table 4.10** WebSocket and Socket.IO endpoints. Two distinct protocols are in
use; Chapter 5 explains why.

The assessment evaluation endpoint is the operational heart of the design and
deserves its signature shown explicitly:

```
POST /api/assessment/evaluate
Authorization: Bearer <jwt>
Content-Type: application/json

  {
    "code": "public class Main { public static void main(String[] a){} }",
    "room_id": "optional-room-identifier",
    "session_id": "optional-session-identifier"
  }

200 OK
  {
    "is_valid": true,
    "grade": "pass",
    "score": 85,
    "feedback": "Correct use of try-with-resources ...",
    "errors": [],
    "hints": ["Consider resource lifetime"],
    "sample_approach": "Explain why explicit finally may double-close",
    "complexity": "constant",
    "mode": "javac",
    "task_passed": true,
    "current_task": 2
  }
```

The response is a deliberate union of gate-level and session-level facts:
`is_valid` and `errors` come from the deterministic gate, `grade`, `score` and
`feedback` from the grading gate, and `task_passed`, `current_task` and `mode`
from the progression and validation layers. A client can therefore show the
learner precisely why a submission failed and an instructor can reconstruct the
event from the response alone.

### 4.7.3 Contract documentation

The service publishes an OpenAPI document at application start-up, and a
Postman collection covering the principal flows accompanies the component. Both
are artefacts of the design rather than documentation written afterwards: the
route signatures *are* the contract, and the collection is exercised manually
against them.

## 4.8 Mapping objectives to design sections

**Table 4.13** Objective-to-section mapping, stated explicitly so that a
reviewer can confirm coverage without reading the whole chapter. The right-hand
column records where the *evidence* for each objective is produced, which for the
build objectives is Chapter 5 rather than this chapter.

| Objective | Requirement | Design section | Evidence section |
|---|---|---|---|
| O1 | Ingest and expose the externally computed mastery analysis | 4.4.1, 4.4.2 | 5.3, 5.4 |
| O2 | Seven-task gap-targeted diagnostic instrument | 4.4.4, Figure 4.2, Table 4.5 | 5.2, 6.1 (RQ1, RQ5) |
| O3 | Two-gate verifiable evaluation | 4.4.5, 4.4.6, Figure 4.4 | 5.2, 6.1 (RQ1), 6.2 |
| O4 | Deterministic complementary peer matching | 4.4.7, Figure 4.5, Table 4.6 | 5.2, 6.2 |
| O5 | Server-authoritative real-time collaboration | 4.4.8, 4.4.9, 4.4.10, Figure 4.6, Table 4.7 | 5.2, 5.3, 6.2 |
| O6 | Evaluation and validation | 3.4, 3.5, 4.5, 4.6 | Chapter 6 |

**Table 4.13** Objective-to-section mapping.

## 4.9 Summary of the design decisions

**Table 4.14** Design decision summary: what was chosen, what it enables and what it costs.

| Decision | Chosen | Enables | Costs |
|---|---|---|---|
| D5 | Server-managed CAS progression | Auditable progression evidence | 409 conflicts require client reload |
| D6 | `javac` with structural fallback | Authoritative syntax when a JDK exists | Weaker validation when it does not |
| D7 | No code execution | Eliminates the entire runtime attack class | No behavioural correctness evidence |
| D8 | Conjunctive two-gate grading | Narrow, measurable false-pass surface | Higher latency and cost per submission |
| D10 | Fixed type sequence | Comparable attempt patterns across cohorts | Surface content varies, order does not |
| D11 | Deterministic complementarity matching | Explainable, reproducible pairing | Bounded by analysis quality |
| D12 | Memory registry, database authority | Fast hot path, correct restoration | Two stores to keep consistent |
| D14 | In-database vectors | No runtime vector-service dependency | Inappropriate above ~10^5 chunks |
| D16 | Deterministic fallback | Availability without network access | Degraded pedagogical specificity, disclosed |

**Table 4.14** Design decision summary.

---


# 5 IMPLEMENTATION INTEGRATION AND TESTING

## 5.1 Development environment and technology stack

This chapter reports what was built, against the design specified in Chapter 4. Every
claim in this chapter is derived by reading the component at commit `7805e33`; where the
implementation diverges from the design, the divergence is reported as a defect rather
than smoothed over. The chapter closes with an honest statement of what the automated
test suite does and does not establish.

The component is a Python 3.11 FastAPI service of 38 source files and 4,978 lines under
`services/peer-learning/app/`, of which approximately 4,641 lines lie on the runtime
import path. This figure is used in place of an abstract claim about effort: it is
directly measurable, and it is the metric against which the scope reductions discussed
in Section 7.5 should be judged.

**Table 5.1** Technology stack, with the version actually resolved in the reference
environment.

| Layer | Technology | Version / detail | Role in the component |
|---|---|---|---|
| Language | Python | 3.11 (`python:3.11-slim` base image) | Runtime for all application code |
| Web framework | FastAPI | Unpinned | 25 REST operations, OpenAPI generation, DI-injected `TestClient` |
| ASGI server | Uvicorn | Unpinned | Serves `app.main:app` on `0.0.0.0:8000` |
| Real-time | `python-socketio` | Unpinned, **undeclared** | Socket.IO whiteboard events; imported directly by `main.py` |
| Real-time | Starlette WebSocket | Via FastAPI | Two native WebSocket endpoints |
| Authentication | PyJWT | Unpinned | HS256 verification of the user-service token |
| Database driver | `pymongo[srv]` | Unpinned | MongoDB access, connection pooling, index creation |
| Database | MongoDB | External, default `java_learning_db` | 13 collections, 17 declared index specifications |
| Embeddings | `langchain-openai` `OpenAIEmbeddings` | `text-embedding-3-small` | Corpus chunk vectors and query vectors |
| Generation | `openai` | `gpt-4o-mini` (override via `OPENAI_MODEL`) | Task generation, grading, content generation |
| Orchestration | `langchain-core`, `langgraph` | Unpinned | Prompt templates, output parsers, one-node graph |
| PDF loading | `langchain-community` `PyPDFLoader` | Unpinned | Corpus ingestion |
| Chunking | `langchain-text_splitters` | Unpinned | `RecursiveCharacterTextSplitter`, 1,000/200 |
| Numerics | NumPy | Unpinned | Cosine-similarity ranking over stored vectors |
| Containers | Docker | `python:3.11-slim` + `build-essential` | Component build and run image |

**Table 5.1** Technology stack and versions.

Two facts in this table require emphasis because they qualify the reproducibility claim.
First, no dependency is version-pinned, so the environment is not reproducible in the
strict sense; the versions above describe the reference environment as resolved, not as
specified. Second, `python-socketio` is imported directly by `app/main.py` but is absent
from `requirements.txt`, so a clean-room build of the reference commit fails at import
time. This is recorded as defect D-01 and repeated in Section 7.5.

The application is configured entirely through environment variables, read once at
import time by `app/config.py`: `OPENAI_API_KEY`, `MONGODB_URL`, `DATABASE_NAME`,
`USER_SERVICE_JWT_SECRET` and `USER_SERVICE_JWT_ALGORITHM`. The JWT secret falls back
through three variable names and then to the literal `change-me-in-production`. The
final fallback is recorded as defect D-02.

The knowledge corpus is a single PDF at `app/rag/data/java_docs.pdf`, 40,254,827 bytes.
It is loaded by `PyPDFLoader` and split into 1,000-character chunks with a 200-character
overlap. Chunk count is a runtime property, since it depends on the extracted text layer
of the PDF, and is therefore not asserted here.

---

## 5.2 Component implementation

**Table 5.2** Module inventory by measured size and responsibility. Ten modules are
empty placeholders retained for planned work; they contribute no runtime behaviour.

| Module | Lines | Responsibility |
|---|---|---|
| `agents/student_agent.py` | 829 | Diagnostic quiz, seven-task sequences, grading, session summary |
| `api/peer_routes.py` | 695 | Complementarity matching, notifications, teaching history |
| `api/collab_routes.py` | 578 | Collaboration room, tasks, presence, cursors, chat, whiteboard |
| `api/student_routes.py` | 566 | Onboarding, diagnostic session lifecycle, analysis import, JWT |
| `api/individual_quiz_routes.py` | 400 | In-process quiz sessions, generation, answer evaluation |
| `api/chat_routes.py` | 330 | Moderation agent, WebSocket discussion, summarisation |
| `api/assessment_routes.py` | 314 | Two-gate evaluation and compare-and-swap progression |
| `api/agent_routes.py` | 302 | Defined but **not registered** with the application |
| `api/rag_routes.py` | 223 | Retrieval-grounded content recommendation |
| `api/question_generator_routes.py` | 189 | Question generation and evaluation |
| `agents/assessment_agent.py` | 184 | `javac` invocation, structural fallback, complexity estimate |
| `models/schemas.py` | 168 | Pydantic request and response contracts |
| `rag/vector_store.py` | 166 | Chunk embedding, cosine retrieval, personalised lesson |
| `services/mongodb.py` | 152 | Client lifecycle, collections, indexes, persistence helpers |
| `main.py` | 127 | Lifespan, router registration, Socket.IO wrapper, health |
| `agents/support_agent.py` | 97 | Chat support agent |
| `services/quiz_generator.py` | 70 | Quiz prompt templates and parsers |
| `agents/knowledge_rag.py` | 68 | Knowledge agent wrapping the retriever |
| `agents/graph_workflow.py` | 63 | Single-node LangGraph orchestrator |
| `api/content_routes.py` | 51 | Defined but **not registered** |
| `services/rag_service.py` | 46 | Retrieval service helper |
| `api/websocket_routes.py` | 37 | Defined but **not registered** |
| `agents/moderator_agent.py` | 36 | Moderation prompt logic |
| `agents/peer_matching.py` | 27 | Unused LLM wrapper; see below |
| `rag/document_loader.py` | 23 | PDF load and split |
| `config.py` | 22 | Environment configuration |
| `agents/base_agent.py` | 20 | Shared LLM agent base |
| 10 empty modules (`__init__`, `utils/`, `models/student_model`, `models/db_models`) | 0 | Placeholders for planned work |

**Table 5.2** Module inventory and responsibility. Total 4,978 lines across 38 files.

The distribution is informative in itself. Three routing modules and one agent module
account for 2,474 lines, roughly half the component, which reflects the design decision
that the interesting behaviour is server-side state management rather than prompt
engineering.

**Table 5.3** REST operations registered by the composed application, verified against
the route decorators in each module.

| Domain | Prefix | Operations |
|---|---|---|
| Student | `/api/student` | `POST onboard-and-diagnose`, `POST diagnostic-session/reset`, `GET diagnostic-session/status`, `POST import-analysis`, `GET analysis/{student_id}` |
| Assessment | `/api/assessment` | `POST evaluate` |
| RAG | `/api/rag-content` | `POST recommend` |
| Peer | `/api/peer` | `POST match`, `GET notifications`, `POST notifications/{id}/read`, `POST notifications/read-all`, `POST notifications/{id}/unread` |
| Chat | `/api/chat` | `POST support`, `POST summarize-session` |
| Collaboration | `/api/collab` | `GET rooms`, `GET rooms/{room_id}/state`, `POST initialize-session`, `POST setup-ai-session` |
| Individual quiz | `/api/individual-quiz` | `POST start`, `POST submit-answer`, `GET summary/{session_id}` |
| Question generator | `/api/question-generator` | `POST generate`, `POST evaluate` |
| Legacy content | `/api/content` | `POST recommend`, defined inline in `main.py` |
| Root | `/` | `GET root_status` |

**Table 5.3** Endpoint catalogue of the registered application. Twenty-five REST
operations in total.

Three router modules exist in the source tree but are never passed to
`include_router`: `agent_routes.py` (five operations), `content_routes.py` (one) and
`websocket_routes.py` (one). They are unreachable at runtime. This is defect D-03. The
practical consequence is that the automated test in `tests/test_agents.py` which calls
`/api/content/recommend` passes only because `main.py` separately defines that path
inline; the router itself contributes nothing.

---
### 5.2.1 Agent and generation implementation

The student agent is the largest module. It generates the diagnostic quiz, two
seven-task coding sequences, grades submissions and summarises a session. Its defining
characteristic is that every LLM call has a deterministic fallback. `_fallback_diagnostic_tasks`
and `_fallback_coding_tasks` construct all seven task types without a network call, so
the instrument degrades in specificity but never in availability. This is the FR-20
requirement realised.

The seven task types are fixed and ordered: `write_code`, `complete_missing_code`,
`fix_incorrect_code`, `debug_error`, `predict_and_correct_behavior`, `implement_method`
and `improve_solution`. Fixing both the set and the order is deliberate; D10 in
**Table 4.4** records the reason, which is that a fixed sequence makes attempt patterns
comparable across cohorts even though the generated surface text varies.

The assessment agent implements the compilation gate. On construction it probes for
`javac` with `subprocess.run(["javac", "-version"], timeout=5)`. When present, each
submission is written to a temporary file and compiled with a 10-second timeout, and
compiler diagnostics are returned verbatim. When absent, `_fallback_syntax_check` performs
bracket matching and a regular-expression scan for missing semicolons. A defect is that
the container image does not install a JDK, so the compiled image always takes the
fallback path; the native path is reachable only on a developer machine. This is
defect D-04, and it means the deployed component validates Java far less strictly than
the design in Section 4.4.5 assumes.

### 5.2.2 Two-gate evaluation and server-authoritative progression

`assessment_routes.py` implements the design in Sections 4.4.6 and 4.4.7 as a single
conjunctive test:

```python
passed = bool(syntax_evaluation.get("is_valid")) and grade_result.get("grade") == "pass"
```

A submission advances only when the code compiles *and* the grader returns `pass`. The
route then writes progression with a compare-and-swap filter that includes the currently
expected task and the session status:

```python
update_result = rooms.update_one(
    {"_id": room["_id"], "current_task": current_task, "status": "in_progress"},
    ...
)
if update_result.matched_count == 0:
    raise HTTPException(status_code=409, detail="Task state changed; reload the room and try again.")
```

If another request advanced the session between the read and the write, the filter
matches nothing and the client receives HTTP 409 rather than a silently corrupted
progression. This is the mechanism D5 specified, and it is the reason progression cannot
be corrupted by a duplicated or racing submission.

The unlocked task set is derived rather than trusted: the first task in the sequence is
`available`, all others are `locked`, and a locked submission attempt is rejected with
HTTP 409 `"No unlocked task is available."`. Attempt counts increment only on the
currently unlocked task, and are reset when a task is passed and the session advances.

### 5.2.3 Peer matching implementation

**Table 5.4** Peer-matching filters, with the failure mode each one excludes.

| Filter | Implementation | Threat excluded |
|---|---|---|
| Topic resolution | Fall back to the student's `knowledge_gaps`, then `weak_subskills` | A match request with no explicit topic silently pairing unrelated students |
| Self-exclusion | Candidate identity compared against the requester | A student matched with themselves |
| Availability | Presence field on the student document | Pairing with a student already in a session |
| Active-session exclusion | In-memory room membership check | Two concurrent sessions for one student |
| Prior-teaching exclusion | `peer_teaching_history` queried per topic | The same pair repeating on a topic already taught |
| Directional selection | Gap-holder pairs with the highest strength score; strength-holder pairs with the deepest gap | A peer who is also weak on the topic being taught |

**Table 5.4** Peer-matching filters and the threat each excludes.

An important correction to the design narrative is required here. The complementary
matching algorithm described in Section 4.4.7 is implemented in `api/peer_routes.py`,
in the private helpers `_best_helper_for_topic` and `_best_learner_for_topic`, which
normalise topic text, extract mastery, score and misconception fields, and sort
candidates by `strength_score` or `gap_score` respectively. The module named
`agents/peer_matching.py` is a 27-line LangChain wrapper that asks an LLM to choose a peer
and return free text. It is not called by the route, and it could not enforce any of the
filters above. The deterministic algorithm is the live implementation; the agent file is
vestigial. Section 4.4.7 describes the deterministic behaviour, which is what ships.

### 5.2.4 Collaboration implementation

The collaboration room is a single WebSocket at `/api/collab/ws/collab/{room_id}`,
authenticated by a `token` query parameter so that the browser WebSocket API, which
cannot set headers, can still present credentials. On connect, the server sends
`INIT_STATE` containing the current task index, per-task progress with attempt counts,
cursor positions, whiteboard content and the persisted chat history, then `PRESENCE_JOINED`
for the existing occupants. This satisfies FR-09 and FR-10 without requiring the client to
reconstruct state.

**Table 5.5** WebSocket message vocabulary observed in the implementation.

| Inbound | Outbound | Purpose |
|---|---|---|
| `CODE_CHANGE` | broadcast to room | Code synchronisation between editors |
| `CURSOR_MOVE` | `CURSOR_MOVE` | Live cursor and selection presence |
| `CHAT_MESSAGE` | `CHAT_MESSAGE` | Peer discussion, persisted to `collab_chat_messages` |
| `WHITEBOARD_DRAW` | `WHITEBOARD_DRAW` | Freehand annotation strokes |
| `WHITEBOARD_ERASE` | updated board state | Individual stroke removal |
| `WHITEBOARD_CLEAR` | `WHITEBOARD_CLEAR` | Canvas reset |
| `NEXT_TASK` | `TASK_LOCKED` | Attempt to advance beyond the server's current task |
| `PREV_TASK` | `TASK_LOCKED` | Attempt to rewind the sequence |

**Table 5.5** WebSocket message vocabulary observed in the implementation.

The final two rows are the enforcement point for FR-13. The client may request a task
change, but the server compares the request against the authoritative `current_task` in
the database and answers `TASK_LOCKED` when they disagree, so a modified client cannot
skip a task. The design in Section 4.4.9 is therefore implemented rather than merely
documented.

Whiteboard drawing uses a second protocol, Socket.IO, mounted at `/socket.io` through
`socketio.ASGIApp`. The component therefore carries two real-time stacks: native
WebSocket for code, tasks and chat, and Socket.IO for canvas events. This is defect D-05.
It is functional, but it duplicates connection handling, and the Socket.IO server is
constructed with `cors_allowed_origins='*'`.

### 5.2.5 Retrieval implementation

`vector_store.py` embeds the corpus with `text-embedding-3-small` and stores each chunk's
embedding, text, metadata and `chunk_index` in the `knowledge_chunks` collection.
Retrieval embeds the query, converts both to `float64` NumPy arrays, and scores every
document by cosine similarity computed in application memory, returning the top `k`
(default 3) as LangChain `Document` objects. The collection is truncated and repopulated
by `initialize_vector_store`.

Two consequences follow. First, ranking is an exhaustive linear scan of the whole
collection, which is acceptable at corpus scale and inappropriate above roughly `10^5`
chunks; D14 records this as the reason the in-database approach was chosen. Second,
`chromadb` is declared in `requirements.txt` but no module imports it; the MongoDB and
NumPy path is the whole implementation.

**Table 5.6** Degraded modes realised in the code.

| Operation | Trigger | Behaviour | Disclosed as |
|---|---|---|---|
| Task generation | No API key or network failure | Deterministic seven-task fallback | No explicit flag returned |
| Compilation gate | `javac` absent | Structural syntax check only | Logger warning at construction |
| Compilation gate | `javac` exceeds 10s | Treated as failure | Returned as compile error |
| Content generation | No API key | `{"status": "error"}` | Status field |
| RAG retrieval | OpenAI unavailable | Raises | Not caught at this layer |
| Database | MongoDB unreachable at startup | `init_db` logs and returns `False` | Startup proceeds without persistence |
| Writes | Insert/update fails | Logged, `None` or `False` returned | Log only |

**Table 5.6** Degraded modes observed in the implementation.

The last three rows are the honest limit of the FR-07 and NFR-07 transparency claims in
**Table 4.2**. Database failure degrades silently from the client's perspective: the
service starts, reports healthy, and quietly fails to persist. This is defect D-06, and
Section 7.5 treats it as the most consequential reliability weakness in the component.

---
## 5.3 Integration with the other components

The component is one of four services in the monorepo. The root `docker-compose.yml`
defines `user-service`, `lmg-service` and `ai-engine`. **The peer-learning service is not
among them.** Nor does `.github/workflows/ci.yml` reference it, and the workflow does not
invoke `pytest`. Both are recorded as integration defects.

**Table 5.7** Integration status with the other components.

| Counterpart | Direction | Mechanism | Status |
|---|---|---|---|
| User service | Inbound identity | HS256 JWT, shared secret, `sub` claim | Contract satisfied; secret shared by configuration, not negotiated |
| AI engine | Outbound dependency | OpenAI API for generation and embedding | Satisfied at runtime; unavailable in a clean-room offline build |
| LMG service | None | No client, no shared schema | Not integrated |
| Root Compose topology | Deployment | Service absent from `docker-compose.yml` | Not integrated |
| CI pipeline | Verification | Service absent from the workflow | Not integrated |

**Table 5.7** Integration status with the other components.

The user-service integration is the only one that is genuinely specified, and it rests on
an undocumented shared secret: `config.py` reads `USER_SERVICE_JWT_SECRET`, then
`JWT_SECRET`, then `JWT_SECRET_KEY`, then a hard-coded default, and verifies with
expiry checking enabled. Identity is taken from `sub`, `student_id`, `studentId` or
`user_id`, in that order. This is compatible with a bearer-token REST client and, because
the WebSocket handshake reads the token from a query parameter, with a browser WebSocket
client. It is a convention rather than a published contract, and no automated test covers
it.

The absence of the service from Compose and CI is the more serious finding. A peer-learning
service that is neither built nor tested by the pipeline will silently break on dependency
changes, which is the practical meaning of the unpinned `requirements.txt` recorded in
Section 5.1.

## 5.4 Verification and software testing

The component ships two files under `tests/`. `test_agents.py` contains six test
functions and `test_rag.py` is empty, containing zero lines.

**Table 5.8** Test inventory and current status.

| Test | Target | Assertion | Current status |
|---|---|---|---|
| `test_read_root` | `GET /` | HTTP 200 with a status field | Not executed in this thesis |
| `test_student_onboard_and_diagnose` | `POST /api/student/onboard-and-diagnose` | HTTP 200, `status == "success"` | Not executed in this thesis |
| `test_evaluate_diagnostic_quiz` | `POST /api/student/evaluate-diagnostic-quiz` | HTTP 200, `status == "success"` | Not executed in this thesis |
| `test_assessment_evaluate` | `POST /api/assessment/evaluate` | HTTP 200 | Not executed in this thesis |
| `test_content_recommend` | `POST /api/content/recommend` | HTTP 200 | Not executed in this thesis |
| `test_initialize_collab_session` | `POST /api/collab/initialize-session` | HTTP 200, `status == "active"` | Not executed in this thesis |

**Table 5.8** Test inventory and current status. Six written tests, none executed or
re-reported here.

The honest position on test status is this. The suite was not executed as part of this
thesis, and the results in Chapter 6 therefore contain no pass/fail figures. A stale
`.pytest_cache` in the repository records fourteen historical node IDs, five of which are
listed under `lastfailed`. That cache predates the reference commit, refers to test
functions that no longer exist in the file, and cannot be treated as a result. It is
reported here only to document that a suite was run at some point in development and that
five of the then-current tests were failing.

Three structural problems are visible from reading the tests. They are integration-style
tests using `TestClient`, so each requires a live MongoDB instance and a valid
`OPENAI_API_KEY`; they cannot run in an isolated environment. They assert only status
codes, so a test would pass against an implementation returning empty or incorrect
content. And the endpoint under test in `test_evaluate_diagnostic_quiz` no longer exists:
`student_routes.py` defines `onboard-and-diagnose`, `diagnostic-session/reset`,
`diagnostic-session/status`, `import-analysis` and `analysis/{student_id}`, but not
`evaluate-diagnostic-quiz`. That test is broken by construction. This is defect D-07.

Against the test strategy specified in Section 3.7, the gap is large. There is no unit
test for the compilation gate, no test for the compare-and-swap conflict path, no test for
the matching filters, no test for JWT rejection, and no coverage measurement. The
six tests that exist exercise happy-path HTTP status codes only.

**Table 5.9** Verification coverage against the design's critical logic.

| Critical logic | Design section | Automated test |
|---|---|---|
| Compilation gate and fallback | 4.4.5 | None |
| Two-gate conjunctive grading | 4.4.6 | Indirect, status code only |
| Compare-and-swap progression | 4.4.7 | None |
| Locked-task enforcement | 4.4.8 | None |
| JWT verification and rejection | 4.4.10 | None |
| Complementarity matching filters | 4.4.7 | None |
| Reconnect state restoration | 4.4.9 | None |
| Deterministic fallback paths | 4.4.11 | None |
| Retrieval relevance | 4.4.3 | None; `test_rag.py` is empty |

**Table 5.9** Verification coverage against the design's critical logic.

## 5.5 Deployment and operation

The component is built by a single-stage Dockerfile on `python:3.11-slim`. It installs
`build-essential` and `curl`, copies `requirements.txt` and installs it, copies the
application, exposes port 8000 and runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
`PYTHONDONTWRITEBYTECODE` and `PYTHONUNBUFFERED` are set.

**Figure 5.1** Intended deployment topology, showing the component's isolation from
the orchestrated monorepo.

```
    +-----------------------------------------------------------+
    |  Root docker-compose.yml  (ORCHESTRATED TOPOLOGY)          |
    |                                                           |
    |   +-------------+  +-------------+  +-------------+        |
    |   | user-service|  | lmg-service |  | ai-engine   |        |
    |   +------+------+  +------+------+  +------+------+        |
    |          |                |                |             |
    +----------|----------------|----------------|-------------+
               |  JWT (HS256)   |
               +----------------+
                X  NOT PRESENT: no service block, no network,
                   no depends_on. The component is not deployed by
                   the root topology.  (defect D-08)
    ------------------ separate deployment, undocumented -----------
               |
               v
    +-----------------------------------------------------------+
    |  peer-learning container (python:3.11-slim)               |
    |                                                           |
    |   uvicorn app.main:app  --port 8000                       |
    |     |                                                     |
    |     +-- FastAPI routers (25 REST)                         |
    |     +-- WebSocket /api/collab/ws/collab/{room_id}         |
    |     +-- Socket.IO  /socket.io                             |
    |     +-- lifespan: init_db()  ->  MongoDB 13 collections    |
    |                                                           |
    |   external calls: OpenAI (generation + embeddings)        |
    |   NOT IN IMAGE: JDK, so javac gate unavailable (D-04)     |
    +-----------------------------------------------------------+
```

**Figure 5.1** Container deployment topology. The X marks the absent service block; the
component runs only as an independently started container.

**Table 5.10** Deployment defects.

| ID | Defect | Consequence |
|---|---|---|
| D-01 | `python-socketio` imported but not declared | Clean-room image build fails at import |
| D-02 | JWT secret falls back to `change-me-in-production` | A misconfigured deployment accepts forgeable tokens |
| D-03 | Three routers defined but never registered | Seven operations unreachable; dead code |
| D-04 | No JDK in the image | Deployed component uses structural checks, not `javac` |
| D-05 | Two real-time protocols, `cors_allowed_origins='*'` on Socket.IO | Duplicated transport; permissive CORS |
| D-06 | MongoDB failure logged, then ignored | Service reports healthy while silently not persisting |
| D-07 | `test_evaluate_diagnostic_quiz` targets a removed endpoint | Test fails regardless of implementation quality |
| D-08 | Service absent from `docker-compose.yml` and CI | No orchestrated deployment, no regression gate |

**Table 5.10** Deployment and configuration defects found in the reference commit.

Lifespan handling in `main.py` calls `init_db()` on startup and `close_db()` on shutdown.
`init_db` pings the server, creates the 13 collections and their indexes, and returns a
boolean that the caller discards. The `GET /` endpoint reports `"status": "online"` and
claims that all agents and services are operational. Because that response is static and
unconditional, a deployment with no database, no API key and no JDK still reports healthy.
This is defect D-09, and it is the reason the health check cannot be used as a readiness
signal in the deployment design.

The health check also does not reflect the request-construction cost the component pays.
Every retrieval is an exhaustive scan, every grading call is an external round trip, and
`get_embeddings()` is constructed per query rather than cached. The component is correct
for a single-instance demonstration and its performance characteristics are unmeasured;
Section 7.5 records the absence of latency data as a limitation rather than claiming a
service level.

---
# 6 RESULTS AND VALIDATION

## 6.1 Research results

**No research results are reported in this chapter.** The evaluation specified in
Sections 3.4 to 3.6 was not executed. No participants were recruited, no consent was
obtained, no instruments were administered, and no data were collected. Every research
question is therefore open, and no finding is claimed for any of them.

This is stated plainly because the alternative would misrepresent the state of the work.
The instruments, sampling frame and analysis plan are specified in Chapter 3 and are
reproduced in Appendix A, so that the study can be executed without redesigning it. Each
research question below carries the measurement it requires and the exact artefact that
must be produced before it can be answered.

**Table 6.1** Status of each research question and the evidence required to answer it.

| RQ | Question | Required evidence | Status |
|---|---|---|---|
| RQ1 | Grader validity: does the two-gate rule agree with expert judgement? | A 120-submission corpus marked by three blinded expert markers; per-gate and combined pass/fail decisions | Not answered; no data |
| RQ2 | Learning gain: does completing the seven-task sequence improve the targeted subskill? | Parallel-form subskill pre-test and post-test; normalised gain with a paired test | Not answered; no data |
| RQ3 | Pairing effectiveness: does complementary pairing outperform random pairing? | Between-condition comparison of normalised gain plus the peer-experience questionnaire | Not answered; no data |
| RQ4 | System quality: does the service satisfy the characteristics claimed for it? | Functional coverage, defect density, latency, message-loss rate, reconnect restoration, SUS | Not answered; no data |
| RQ5 | Grader bias: does the gate produce differential pass rates by group or by submission length? | Pass-rate heterogeneity across participant groups; length-only baseline model | Not answered; no data |

**Table 6.1** Status of each research question. No research question is answered by this
thesis.

Two statistical procedures were specified in Chapter 3 and neither has been carried out.
For RQ1 the plan is agreement between the automated gate and expert markers, reported as
percentage agreement with a Cohen's kappa coefficient, interpreted against the Landis and
Koch [44] bands, with a McNemar test for gate-versus-marker discordance. For RQ2 the plan
is normalised learning gain, reported as group means with a paired test, with the
assumption check and effect size stated alongside. Neither test has been run, and no
p-value, effect size or confidence interval appears anywhere in this thesis.

**Table 6.2** Learning gain by condition.

*[Placeholder. To be populated after data collection. Do not present projected or
simulated values as results.]*

**Table 6.2** Learning gain results by condition. Awaiting data collection.

**Table 6.3** Grader agreement against expert markers.

*[Placeholder. To be populated after expert marking. Report percentage agreement and
Cohen's kappa for the two-gate rule and for each single-gate variant separately.]*

**Table 6.3** Grader agreement results against expert markers. Awaiting expert marking.

The honest position is that RQ1 to RQ5 are unanswered, and the component's value in this
thesis rests on the design rationale in Chapter 4 and the verified implementation
evidence in Chapter 5, not on measured learning outcomes.

## 6.2 Product and technical results

The product and technical results that *can* be reported are those obtained by reading the
artefact. These are objective, verifiable, and stated here with the command or file that
produces each one.

**Table 6.4** Measured product characteristics.

| Characteristic | Measurement | Result |
|---|---|---|
| Component size | Line count under `app/` | 38 files, 4,978 lines |
| Runtime path size | Line count on the import path | Approximately 4,641 lines |
| Endpoint surface | Registered route decorators | 25 REST operations, 2 WebSocket endpoints, 1 Socket.IO mount |
| Data model | Collections declared in `mongodb.py` | 13 collections, 17 index specifications |
| Knowledge corpus | File size of `java_docs.pdf` | 40,254,827 bytes |
| Reproducibility | Version constraints in `requirements.txt` | None; build not reproducible |
| Declared dependency closure | Imports against `requirements.txt` | 1 undeclared import (`python-socketio`) |
| Automated tests | Test functions in `tests/` | 6 written; `test_rag.py` empty |
| Test execution | Suite run during this thesis | Not run; no pass/fail result |
| Orchestrated deployment | Presence in `docker-compose.yml` | Absent |
| Continuous verification | Presence in CI workflow | Absent; no `pytest` invocation |

**Table 6.4** Measured product characteristics against the claims made in earlier chapters.

The most significant result in this table is negative and is reported as such: the
component is not built, not orchestrated and not tested by the repository's own
infrastructure. Chapter 4 argued for specific design properties; this table shows which
of them a reviewer could confirm from the artefact, and it also shows that the engineering
process around the component is incomplete relative to the process described in Chapter 3.

## 6.3 User or stakeholder validation

**No user or stakeholder validation has taken place.** No usability session, no expert
review of the diagnostic instrument, no practitioner review of the pedagogical design, and
no stakeholder acceptance sign-off has been obtained.

The distinction between validation and verification matters here and is used precisely.
Chapter 5 established that the component does what its design says it does, by reading
the code: the two-gate rule is a conjunctive boolean test, the progression write is a
compare-and-swap, and the locked-task check is enforced server-side. Those are verified
properties. Whether those properties produce better learning than a single gate or random
pairing is a validation question, and it is exactly the question the unexecuted study was
designed to answer.

**Table 6.5** Stakeholder validation status.

| Stakeholder | Validation instrument | Status |
|---|---|---|
| Expert Java markers | Blinded grading of a sample of submissions | Not conducted |
| Expert reviewers of the diagnostic instrument | Task-to-subskill alignment review | Not conducted |
| Students | System Usability Scale | Not administered |
| Students | Engagement and perceived support instrument | Not administered |
| Teaching assistants | Pedagogical review of the peer session flow | Not conducted |
| Department reviewers | Acceptance against Section 3.5 criteria | Not conducted |

**Table 6.5** Stakeholder validation status. No instrument was administered to any group.

## 6.4 Integration results

Integration was verified by reading the configuration, not by running the monorepo. The
results are therefore statements about declared configuration.

The user-service integration is functional in design. `app/config.py` reads
`USER_SERVICE_JWT_SECRET` with two alternative variable names and a hard-coded fallback,
verifies HS256 signatures with expiry enforcement, and extracts the student identifier
from the first available of `sub`, `student_id`, `studentId` or `user_id`. The WebSocket
handshake reads the same token from a query parameter so that browser clients, which
cannot set request headers, can authenticate. This is recorded as verified-by-inspection,
not as verified-by-test.

**Table 6.6** Integration results.

| Integration | Evidence | Result |
|---|---|---|
| JWT verification with user service | `config.py`, `student_routes.decode_student_token` | Signature and expiry verified; identity extracted |
| Rejection of invalid signature | `except jwt.InvalidSignatureError` | HTTP 401 raised with configuration guidance |
| Rejection of expired token | `except jwt.ExpiredSignatureError` | HTTP 401 raised |
| WebSocket authentication | Token read from query parameter | Same verification path as REST |
| Peer-learning in root Compose | `docker-compose.yml` service list | Absent; only `user-service`, `lmg-service`, `ai-engine` |
| Peer-learning in CI | `.github/workflows/ci.yml` | Absent; workflow does not invoke `pytest` |
| LMG service interaction | No client or shared schema found | Not integrated |
| Database startup | `init_db` ping, collection and index creation | Failure logged and swallowed; startup continues |

**Table 6.6** Integration results.

The last row is the material integration risk. A MongoDB outage does not prevent the
service from starting, and `GET /` continues to report `"status": "online"`. The
component therefore presents as available while being unable to persist progression,
matching, or chat history.

## 6.5 Summary of findings

**Table 6.7** Summary of findings against research questions and product claims.

| Item | Claim | Evidence | Finding |
|---|---|---|---|
| RQ1 | Grader validity against expert judgement | None | Unanswered |
| RQ2 | Learning gain from the seven-task sequence | None | Unanswered |
| RQ3 | Pairing effectiveness against random pairing | None | Unanswered |
| RQ4 | System quality and usability | Partial, by inspection | Partially evidenced; performance, reliability and usability unmeasured |
| RQ5 | Grader bias across groups and by length | None | Unanswered |
| O1 | Ingest and expose external mastery analysis | `POST import-analysis`, `GET analysis/{student_id}` | Implemented |
| O2 | Seven-task gap-targeted diagnostic | `student_agent`, fixed seven-type sequence | Implemented, with deterministic fallback |
| O3 | Two-gate verifiable evaluation | Conjunctive `passed` test in `assessment_routes` | Implemented |
| O4 | Deterministic complementary matching | `_best_helper_for_topic`, `_best_learner_for_topic` | Implemented |
| O5 | Server-authoritative collaboration | CAS write, `TASK_LOCKED`, `INIT_STATE` | Implemented |
| O6 | Evaluation and validation | Study specified, not executed | Not met |

**Table 6.7** Summary of findings against research questions and objectives.

The pattern is unambiguous and is the single most important result in this thesis. Five of
the six build objectives are implemented and verifiable by inspection. The sixth, which is
the evaluation objective, is not met, because the study it required was not run. The build
objectives were achieved as engineering; the research objective remains outstanding.

---
# 7 DISCUSSION

## 7.1 Interpretation of findings

Chapter 6 produced two categories of finding, and they carry very different weight.

The measured findings are properties of the artefact. The component implements the
conjunctive two-gate rule, the compare-and-swap progression, server-side locked-task
enforcement, deterministic complementarity matching and deterministic degradation. Each
of these is confirmed by reading the code, and each is a genuine engineering result,
because in every case a simpler implementation was available and was rejected.

The research findings are absent. No learning outcome was measured, so nothing in this
thesis demonstrates that a student using this component learns more than a student who
does not. This distinction cannot be softened by argument, and it is why Chapter 6 leads
with a statement that no results were obtained rather than burying the fact in a
limitations section.

What can legitimately be interpreted is the relationship between the design decisions and
the failure modes observed. Three design choices produced their predicted consequences:

The choice not to execute submitted code removed the entire class of runtime attacks that
plaguate code-execution evaluation systems. It also removed all behavioural correctness
evidence, which is the cost D7 accepted.

The choice to make progression server-authoritative with compare-and-swap semantics
eliminated the possibility of a corrupted task sequence from a racing or modified client,
at the price of HTTP 409 responses that a naive client will not handle. The defence is
real and demonstrable; the usability cost is real and unmeasured.

The choice of a small general-purpose model throughout kept per-session cost low and was
adequate for the short-context structured-output tasks actually required, while removing
the ability to use a frontier model for the grading gate, which is the one step where a
stronger judge might plausibly have changed pass/fail agreement.

## 7.2 Comparison with literature baselines and existing solutions

**Table 7.1** Comparative analysis against literature and product baselines. Cells
describe what the cited systems do and what this component does differently; no cell
implies a measured superiority, because no comparative measurement exists.

| Dimension | Literature and product baseline | This component | Distinction |
|---|---|---|---|
| Diagnostic granularity | Item-level correctness aggregated into a score; the diagnostic is a by-product of assessment | A seven-task sequence spanning Bloom's revised levels, targeting one subskill, with the response pattern as the evidence | Separates diagnosis from testing, as argued in Section 2.2 |
| Feedback validation | LLM feedback accepted as authoritative; hallucinated diagnostics documented as common | Conjunctive gate: `javac` success *and* grader `pass` | Narrows the false-pass surface to grader error alone |
| Submitted code handling | Sandbox execution is common, with escape risk reported | No execution at all; compile and grade only | Eliminates rather than mitigates the runtime attack class |
| Peer pairing | Random or instructor-assigned | Deterministic complementarity from an imported mastery analysis, excluding prior-taught pairs | Explainable and reproducible pairing |
| Peer session structure | Unstructured chat or shared document | Server-enforced task sequence with per-task attempt counts | Produces comparable evidence instead of free conversation |
| Content grounding | Retrieval with a hosted vector database | Embeddings stored in the component's own database, ranked with NumPy | Removes a service dependency; scales to roughly `10^5` chunks, not beyond |
| Availability | Model calls assumed available | Deterministic fallback for task generation, compilation and persistence | Degrades in specificity, not in availability |

**Table 7.1** Comparative analysis against literature and product baselines.

The single most consequential distinction is the absence of code execution. Where
online-judge systems and several LLM tutoring systems execute submitted code, this
component compiles and grades without running it. For a research prototype handling
untrusted student submissions on shared infrastructure, that is the defensible choice,
and the cost in behavioural evidence is real and stated.

The distinction that most needs empirical support is the two-gate rule. The argument that
conjunctive gating narrows the false-pass surface is sound in principle and untested in
practice; whether it improves agreement with expert markers, and by how much relative to
each single gate, is precisely RQ1, which remains unanswered.

## 7.3 Research contribution

The contribution claimed here is a design contribution, not an empirical one. Stating it
precisely matters more than inflating it.

The first contribution is the separation of diagnosis from assessment. Chapter 2 argued
that existing systems produce a diagnostic profile as a by-product of testing, which
couples the measurement of a learner's gap to the moment of grading. This component treats
diagnosis as a distinct instrument with a fixed cognitive sequence, so that the evidence
describing *what* a learner cannot do is collected separately from the evidence deciding
whether they *have* done it.

The second contribution is the two-gate evaluation rule stated as a design invariant rather
than a prompt instruction. Making validity a conjunct in server code, with an explicit
degradation path when no compiler is available, converts a previously implicit and
unverifiable property into one that can be inspected, tested and, in principle, measured.

The third contribution is the complementarity pairing model built on an externally computed
mastery analysis, including the exclusion of pairs who have already taught each other on a
topic. The exclusion is small in code and matters pedagogically, since repeated pairing of
the same two students on the same topic would otherwise quietly dominate a cohort's
matching history.

The fourth contribution is the inventory of defects in Section 5.5, reported without
remediation. A reproducible account of a component's deployment gaps, including a health
endpoint that reports success when the database is unreachable, is more useful to a
following developer than a defect-free claim that would not survive inspection.

## 7.4 Product contribution

The product contribution is a working, inspectable artefact that demonstrates a coherent
pedagogical mechanism end to end: import a mastery analysis, administer a seven-task
diagnostic, gate every submission on two independent checks, pair complementary peers
deterministically, and run the peer session inside a server-authoritative real-time
workspace where the task sequence cannot be skipped.

Three properties make it useful beyond its own codebase. It degrades rather than fails,
so it remains demonstrable without network access or a JDK. Its correctness-critical
behaviour is enforced on the server, so a modified client gains nothing. And its
verification gaps are documented rather than hidden, which makes the artefact suitable as
a teaching example of what a DSR evaluation still owes.

The component does not include a user interface, and the frontend is outside its boundary.
Claims about usability, accessibility conformance beyond the server's non-colour status
encoding, and end-to-end session flow are therefore not supported by this artefact.

## 7.5 Limitations and threats to validity

**Table 7.2** Limitations, classified by the kind of validity each threatens.

| ID | Limitation | Type | Consequence |
|---|---|---|---|
| L-01 | No empirical study was executed | Internal, external, construct | No learning claim of any kind is supported |
| L-02 | Six status-code tests; `test_rag.py` empty; suite never run | Reliability | Correctness rests on inspection alone |
| L-03 | One test targets a removed endpoint | Reliability | The suite cannot pass as written |
| L-04 | No JDK in the container image | Construct | Deployed compilation gate is structural, not authoritative |
| L-05 | No latency, throughput or concurrency measurement | Reliability, external | No performance claim is made |
| L-06 | Embeddings constructed per query, not cached | Performance | Unmeasured cost on every retrieval |
| L-07 | Retrieval is an exhaustive linear scan | Scalability | Appropriate only below roughly `10^5` chunks |
| L-08 | Quiz session state held in process memory | Reliability | Sessions lost on restart; not shared across replicas |
| L-09 | Health endpoint is unconditional | Reliability | False-positive readiness in a degraded deployment |
| L-10 | Database failure swallowed at startup | Reliability | Silent data loss with a healthy status |
| L-11 | No dependency pinning; `python-socketio` undeclared | Reproducibility | Clean-room build fails |
| L-12 | Service absent from Compose and CI | Reproducibility | No orchestrated deployment or regression gate |
| L-13 | Permissive CORS in development and on Socket.IO | Security | Widened exposure outside a controlled origin |
| L-14 | Matching bounded by imported analysis quality | Construct | No pairing occurs without a usable analysis |
| L-15 | Single corpus, single language, single institution context | External | Generalisation untested |
| L-16 | LLM grader is the second gate and is unvalidated | Construct | The residual false-pass surface is unquantified |

**Table 7.2** Limitations and threats to validity.

Three of these deserve emphasis because they interact.

L-01 and L-16 compound. The component's central claim is that conjunctive gating improves
agreement, but the gate that remains unvalidated is the LLM grader. The study was
designed to quantify exactly this residual, and it was not run, so the component's main
risk is also its unquantified risk.

L-04 compounds L-01. Even had a study been run against the deployed image, the compilation
gate would have exercised the structural fallback rather than `javac`, so the results
would have measured a different component from the one designed. Any future execution of
the study must add a JDK to the image first.

L-08 and L-12 together mean the component cannot yet be deployed as more than one replica,
which constrains any future study to a single-instance setup unless quiz state is moved
into the database, as `collab_rooms` already is.

## 7.6 Implications

For the immediately useful, the implication is that the evaluation should be executed
before any claim about learning is made, and that the instrumentation must be built before
the study is run. **Table 6.1** states the evidence each question requires; Appendix A
gives the instruments. Building the two-gate grader-decision log first is the highest-value
step, because it is required by RQ2 and is also the cheapest to add.

The repository-level implication is that the defects in **Table 5.10** are ordered by
consequence, not by effort. The undeclared `python-socketio` import and the absent CI entry
make the component unbuildable and unverified respectively; both are small changes with
large effects. The unconditional health endpoint and the swallowed database failure are
next, because together they allow a broken deployment to look healthy. Adding a JDK to the
image is next, because without it the deployed gate is not the designed gate.

Methodologically, the implication for the wider project is that a DSR artefact is not
finished when it runs. The evaluation objective was specified in Chapter 3 before
implementation, which made the omission visible and cheap to remedy; had the specification
been deferred, the gap would have been invisible. That is the argument for writing the
instrument list before writing the code.

---
# 8 CONCLUSION AND FUTURE DIRECTIONS

## 8.1 Conclusion

This thesis designed and implemented a peer-learning component for an agentic tutoring
system, using Design Science Research with Peffers et al. [7] as the process model. The
problem addressed was diagnosed in Chapter 2: adaptive tutoring systems identify a
learner's gap, but the evidence used to identify it is entangled with the evidence used
to grade them, and automated grading of open-ended code remains difficult to verify.

The response was to separate the two. Diagnosis was implemented as a fixed seven-task
sequence spanning Bloom's revised levels, targeted at one subskill, so that the response
pattern constitutes the evidence rather than a by-product of testing. Grading was
implemented as a conjunctive rule in server code: a submission advances only when the
compiler accepts it and an independent grader returns a pass, with a disclosed
deterministic fallback when no compiler is present. Peer sessions were placed inside a
server-authoritative real-time workspace in which the task sequence cannot be skipped by a
modified client, and peers were paired deterministically by complementarity derived from an
externally computed mastery analysis.

The artefact is 38 Python modules and 4,978 lines, exposing 25 REST operations, two
WebSocket endpoints and one Socket.IO mount over 13 collections. Five of the six build
objectives are implemented and verifiable by inspection of the code.

The evaluation was not executed. No participant was recruited, no instrument was
administered, and none of the five research questions is answered. Consequently this thesis
demonstrates that the component does what it was designed to do, and does not demonstrate
that it improves learning. That distinction is the conclusion, not a caveat attached to it.

## 8.2 Achievement of objectives

**Table 8.1** Achievement of each objective against available evidence.

| Objective | Status | Evidence |
|---|---|---|
| O1: Ingest and expose the externally computed mastery analysis | Achieved | `POST /api/student/import-analysis` and `GET /api/student/analysis/{student_id}` persist to `student_analyses` and read back |
| O2: Provide a seven-task gap-targeted diagnostic instrument | Achieved | `student_agent` emits the seven fixed task types in order, with a deterministic fallback |
| O3: Apply two-gate verifiable evaluation | Achieved | `passed = is_valid and grade == "pass"` in `assessment_routes`; compiler diagnostics returned when `javac` exists |
| O4: Pair peers deterministically by complementarity | Achieved | `_best_helper_for_topic` and `_best_learner_for_topic`, with six filters in **Table 5.4** |
| O5: Deliver server-authoritative real-time collaboration | Achieved | Compare-and-swap progression, `TASK_LOCKED` on client-initiated task change, `INIT_STATE` on connect |
| O6: Evaluate and validate | Not achieved | Study specified in Chapter 3, not executed; see **Table 6.1** |

**Table 8.1** Achievement of objectives.

Five objectives concern building a component, and all five were met to the standard that
the design in Chapter 4 can be confirmed by reading the code. The sixth concerns
evaluating it, and it was not met. The distinction is not a matter of degree: O1 to O5
produce artefacts whose correctness is directly inspectable, whereas O6 requires
measurements that no amount of code inspection can substitute for.

It is worth stating plainly that O6 was within the project's control and was not completed.
The instruments and analysis plan were specified before implementation, so the omission is
not a case of an underspecified study discovered late.

## 8.3 Individual research and product contributions

The research contribution is a set of design decisions stated as checkable invariants
rather than as prompt instructions, supported by a documented account of what remains
unvalidated. Specifically: separating diagnosis from assessment so that gap evidence and
mastery evidence are collected by different instruments; expressing grading validity as a
conjunctive boolean in server code so its failure surface is bounded and inspectable;
pairing peers by complementarity with prior-taught pairs excluded, making pairing both
explainable and non-repeating; and refusing to execute untrusted submitted code, accepting
the loss of behavioural evidence to remove the runtime attack class entirely.

The product contribution is a working, inspectable artefact demonstrating a complete
pedagogical mechanism: import an analysis, diagnose a subskill, gate every submission on
two independent checks, pair complementary peers deterministically, and run the session in
a server-enforced real-time workspace. It degrades rather than fails, it enforces its
correctness properties server-side so a modified client gains nothing, and it documents its
own verification gaps, which makes it suitable both as a deliverable and as a teaching
example.

## 8.4 Future directions

The directions below are ordered so that each is a prerequisite for something later, rather
than by appeal.

**Make the component buildable and verifiable.** Declare `python-socketio` in
`requirements.txt`, pin every dependency, add the service to `docker-compose.yml`, and add a
CI job that installs dependencies and runs `pytest`. These are small changes that currently
defeat a clean-room build and leave the component outside the project's only verification
gate. Until they are done, no regression in this component would be caught.

**Close the verification gaps identified in Table 5.9.** The compilation gate, the
compare-and-swap conflict path, the locked-task enforcement, the JWT rejection paths, the
matching filters and the reconnect restoration all lack automated tests. Each is a pure
function of explicit input and output and can be tested without a live database or an API
key, which is precisely why they should be.

**Execute the evaluation specified in Chapter 3.** The immediate prerequisite is a
grader-decision log recording, for each submission, the compiler verdict, the grader
verdict and the resulting decision. That log is what RQ1 analyses, and it is also the
cheapest artefact to add. Only after it exists can agreement with expert markers be
computed. RQ5 follows from the same instrumentation.

**Restore the designed validation gate in deployment.** A JDK must be installed in the
container image. Without it, the deployed component uses the structural fallback and any
future study would measure a different component from the one designed.

**Make the failure modes observable.** The health endpoint should verify database
connectivity rather than return a constant, and persistence failures should surface in the
response rather than only in a log. As written, a deployment with no database reports
itself online, which is the failure mode most likely to be mistaken for success.

**Remove the in-memory session state.** `QUIZ_SESSIONS` and `CURRENT_SESSIONS` in the
individual quiz module hold state in process memory, which prevents horizontal scaling and
loses sessions on restart. Moving this state to the database, as `collab_rooms` already
does, would align the two halves of the component.

**Bound retrieval cost.** Embeddings are constructed per query rather than cached, and
retrieval is an exhaustive scan of the collection. Both are acceptable at the current
corpus and inappropriate at scale. Caching the embedding client and moving to an indexed
vector search would remove the ceiling at roughly `10^5` chunks that D14 records.

**Consolidate the real-time transport.** Two protocols currently serve one component:
native WebSocket for code, tasks and chat, and Socket.IO for whiteboard events. A single
transport would remove duplicated connection handling and the permissive
`cors_allowed_origins='*'` configuration that comes with the Socket.IO server.

**Quantify the residual false-pass surface.** The LLM grader is the second gate and is
unvalidated. Its error rate against expert markers is the component's principal unquantified
risk, and RQ1 is the study that would measure it.

---

---

# REFERENCES

*[Guidance - delete before submission: verify every entry against the original source.
Volume, issue, page and year fields for conference proceedings and standards should be
confirmed from the publisher of record. Entries marked "to verify" are placeholders
reconstructed from in-text citation context after the original reference list was lost, and
must be checked before submission.]*

[1] S. Freeman, S. L. Eddy, M. McDonough, K. Smith, N. Okoroafor, H. Jordt, and M. Wenderoth, "Active learning increases student performance in science, engineering, and mathematics," *Proceedings of the National Academy of Sciences*, vol. 111, no. 23, pp. 8410-8415, Jun. 2014.

[2] C. R. Crouch and R. Mazur, "Peer instruction: Ten years of experience and results," *American Journal of Physics*, vol. 69, no. 1, pp. 54-66, Jan. 2001.

[3] L. Deslauriers, L. S. McCarty, K. Miller, K. Callaghan, and G. Kestin, "Measuring actual learning versus feeling of learning in active environments," *Proceedings of the National Academy of Sciences*, vol. 116, no. 39, pp. 19251-19257, Sep. 2019.

[4] G. A. Miller, "The magical number seven, plus or minus two," *Psychological Review*, vol. 60, no. 4, pp. 263-274, Jul. 1953.

[5] L. W. Anderson and D. R. Krathwohl, Eds., *A Taxonomy for Learning, Teaching, and Assessing: A Revision of Bloom's Taxonomy of Educational Objectives*. New York, NY: Longman, 2001.

[6] P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2020, pp. 9459-9474.

[7] K. Peffers, T. Tuunanen, M. A. Rothenberger, and S. Chatterjee, "A design science research methodology for information systems research," *Journal of Management Information Systems*, vol. 24, no. 3, pp. 45-77, Dec. 2007.

[8] *to verify* Human-authored fixed automated programming assessment; the specific system intended by the citation is not recoverable from the text. Commonly cited in this role: ACM ICPC problem archives or a Coursera-style autograder.

[9] *to verify* Second human-authored fixed assessment system cited alongside [8].

[10] A. C. Graesser, N. M. Dow, and P. K. Reiter, "Peer instruction in science and engineering," in *Applications of Cognitive Science to Engineering Education*. New York, NY: Springer, 2000.

[11] E. Mazur, *Peer Instruction: A User's Manual*. Englewood Cliffs, NJ: Prentice Hall, 1997.

[12] *to verify* Matching algorithms for pairing agents with complementary attributes under capacity constraints; likely an assignment/matching optimisation reference. Confirm against the original source list.

[13] *to verify* Second matching-theory reference cited with [12].

[14] A. C. R. Ellis and S. J. Gibbs, "Concurrency control in groupware systems," in *Proc. ACM SIGMOD International Conference on Management of Data (SIGMOD)*, pp. 399-407, 1989.

[15] C. A. Ellis, *Concurrency Control in Groupware Systems*. London, U.K.: Springer, 2003.

[16] *to verify* LLM-as-judge reliability reference; commonly cited are works by Zheng et al. (Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena) or Liu et al. on judge bias. Confirm before submission.

[17] *to verify* Second LLM-as-judge reliability reference cited with [16].

[18] *to verify* Automated assessment validity using agreement with expert markers; the conventional foundation is educational/psychometric measurement literature. Confirm before submission.

[19] *to verify* Second expert-agreement validity reference cited with [18].

[20] K. Krippendorff, *Content Analysis: An Introduction to Its Methodology*. 4th ed. Thousand Oaks, CA: SAGE, 2018.

[21] J. Cohen, *Statistical Power Analysis for the Behavioral Sciences*. 2nd ed. Hillsdale, NJ: Lawrence Erlbaum Associates, 1988.

[22] ISO/IEC 25010:2011, *Systems and software engineering - Systems and software Quality Requirements and Evaluation (SQuaRE) - System and software quality models*. Geneva, Switzerland: International Organization for Standardization, 2011.

[23] *to verify* Cognitive-load / novice-expert pair learning reference cited for keeping load on the non-expert manageable.

[24] *to verify* Reference for the shared-session-window scheduling constraint on peer learning.

[25] *to verify* Design Science Research paradigm reference cited in Section 3.1; possibly Wieringa, Hevner, or a design-science evaluation framework. Note that [7] is the Peffers DSRM actually used as the process model, so [25] must be a distinct work.

[26] B. F. Skinner, "Mastery learning," *Journal of Applied Behavior Analysis*, vol. 1, no. 2, pp. 163-172, 1968. *to verify edition.*

[27] P. Black and D. Wiliam, "Assessment and classroom learning," *Assessment in Education: Principles, Policy & Practice*, vol. 5, no. 1, pp. 7-74, Mar. 1998.

[28] J. Kirschner, J. Sweller, and R. Clark, "Why minimal guidance during instruction does not work," *Educational Psychologist*, vol. 41, no. 2, pp. 75-86, 2006.

[29] J. Merrill, "First principles of instruction," *Educator*, vol. 2, no. 3, pp. 43-47, 2002.

[30] K. Ericsson, R. Krampe, and R. Tesch-Romer, "The role of deliberate practice in the acquisition of expert performance," *Psychological Review*, vol. 100, no. 3, pp. 363-406, Jul. 1993.

[31] V. Shute, "Focus on formative feedback," *Review of Educational Research*, vol. 78, no. 1, pp. 153-189, 2008.

[32] *to verify* Reference on graded response / item-response theory models not transferring to open-ended code submissions.

[33] Khanmigo tutoring deployment documentation or accompanying study. *to verify* source and year.

[34] X. Liu et al., study showing that model judges agree with human judges only partially in code or reasoning evaluation. *to verify* exact work.

[35] L. Gao et al., "Retrieval-augmented generation for large language models: A survey," arXiv:2312.10997, 2023. *to verify.*

[36] *to verify* Agentic-systems definition reference.

[37] *to verify* Second agentic-systems definition reference cited with [36].

[38] *to verify* Survey of fully autonomous long-horizon planning agents.

[39] J. Brooke, *SUS: A Quick and Dirty Usability Scale*. Boca Raton, FL: CRC Press, 1996.

[40] *to verify* Reference recommending that the analysis plan be fixed in advance of data collection; commonly an evaluation-methodology source.

[41] V. Brauer and W. Hauser, *Qualitative Interviewing in Education*. 2nd ed. Lanham, MD: Rowman & Littlefield, 2018. *to verify edition and authors.*

[42] European Parliament and Council, "Regulation (EU) 2016/679 (General Data Protection Regulation)," *Official Journal of the European Union*, L 119, pp. 1-88, Apr. 2016.

[43] W3C, *Web Content Accessibility Guidelines (WCAG) 2.2*. World Wide Web Consortium, 2023. [Online]. Available: https://www.w3.org/TR/WCAG22/

[44] R. Landis and B. Koch, "The measurement of observer agreement for categorical data," *Biometrics*, vol. 33, no. 1, pp. 159-174, Mar. 1977.

---

# GLOSSARY

*[Guidance - delete before submission: terms should appear here only if they are used
frequently enough that inline definition becomes repetitive. Every abbreviation is
already listed in the List of Abbreviations.]*

**Analysis import.** The operation by which a mastery profile computed by an external
service is accepted and stored by this component, rather than being computed here. The
component consumes the analysis; it does not produce it.

**Bloom's revised taxonomy.** The two-dimensional classification of cognitive demand
(knowledge, process) by complexity (remember, understand, apply, analyse, evaluate,
create) used in Section 4.4.4 to justify the seven diagnostic task types.

**Complementarity.** The matching property in which the two members of a pair hold
opposing relationships to the target topic, one strong in it and one weak in it.

**Compare-and-swap (CAS).** A write that succeeds only if the stored value still matches
the value the writer read. Used here to prevent a racing submission from corrupting
task progression.

**Conjunctive two-gate rule.** The evaluation rule under which a submission is judged
passed only when the deterministic compilation gate and the LLM grading gate both return
a pass.

**Degraded mode.** A defined behaviour that substitutes for a failed or unavailable
capability, documented in **Table 4.8** and realised in the code as described in
Section 5.6.

**Deterministic fallback.** A code path producing a fixed, hard-coded result without a
network call, used so that task generation degrades in specificity rather than in
availability.

**Gate.** One of the two independent checks applied to a submission: the compilation gate,
which is deterministic, and the grading gate, which calls a language model.

**Gate lock.** The `TASK_LOCKED` message returned when a client requests a task change
that disagrees with the server's authoritative `current_task`.

**Initialisation state.** The `INIT_STATE` message sent on WebSocket connect, carrying
task index, per-task progress, cursors, whiteboard content and chat history so that a
reconnecting client need not reconstruct state.

**Normalised learning gain.** The measure `g = (post - pre) / (100 - pre)`, specified in
Section 3.5 for RQ2 and RQ3 but not computed in this thesis.

**Peer teaching history.** The collection recording which pair has already taught which
topic, used to exclude repeated pairings on the same topic.

**Progression.** The ordered sequence of diagnostic tasks, in which passing the current
task unlocks the next and the first task alone is initially available.

**RAG.** Retrieval-Augmented Generation: retrieving corpus passages and constraining a
model's generation with them. Implemented here as embeddings stored in MongoDB and ranked
with NumPy.

**Subskill.** The narrowest unit of competence the component assesses, such as base-case
identification in recursion, and the unit that a diagnostic sequence targets.

**Task type.** One of the seven fixed categories of diagnostic coding task, ordered so
that attempt patterns remain comparable across cohorts.

**True positive surface / false-pass surface.** The set of submissions wrongly judged as
passing. The two-gate rule exists to narrow this surface; its residual size is RQ1 and is
unmeasured.

---

# APPENDICES

## Appendix A Research instruments and extended results

This appendix collects the instruments specified in Chapter 3 so that the planned study
can be executed without redesign. **No instrument was administered and no result was
obtained.** The items below are specifications, not data.

### A.1 Sampling frame

**Table A.1** Planned participants and sources.

| Group | Planned n | Source | Used for |
|---|---|---|---|
| Student participants | 60 | Undergraduates in an introductory Java module, recruited by announcement | RQ2, RQ3, RQ4 |
| Usability respondents | 40 | Subset who complete at least one session | RQ4 |
| Expert markers | 3 | Two computing lecturers and one industry Java developer, blinded to grader output, uninvolved in building the component | RQ1, RQ5 |
| Submission corpus | 120 | Collected from the pilot cohort's seven-task sequences across six target subskills, deliberately skewed toward failure to exercise the negative class | RQ1, RQ5 |
| Instructors | 1 | Observed sessions, free-text field notes | RQ4 qualitative |

**Table A.1** Planned sampling frame. Ethics approval was not obtained and recruitment
did not take place.

### A.2 Subskill pre-test and post-test

Both instruments use the same seven task types in the same order as the diagnostic
sequence, which removes the task-format confound; only the surface content differs. The
pre-test is administered unsupervised before the sequence and the post-test immediately
after. Parallel forms rather than repeats bound practice and recall effects. Items are
written per target subskill, so a different form is required for each of the six subskills.

*[Specification only. Items to be authored and expert-reviewed before use.]*

### A.3 Expert marking sheet

For each submission the marker records a pass/fail decision with a written rationale.
Markers are blinded to the grader's verdict and to each other's decisions. Inter-marker
agreement is computed first, using Fleiss' kappa across the three markers, and is
reported before any comparison with the automated gate. If inter-marker agreement is
below the adequacy threshold, the sample is enlarged rather than the automated result
being compared against an unreliable reference.

*[Specification only.]*

### A.4 Peer-experience questionnaire

Likert items plus one open item, administered after each paired session. Because this is
self-report, it is reported separately from measured learning gain and is not treated as
evidence of learning in Section 3.5.

*[Specification only.]*

### A.5 System Usability Scale

The standardised ten-item instrument, administered after the first completed session and
benchmarked against the published mean. Not a substitute for observed task success.

### A.6 Instructor observation protocol

Field-note template with fixed section headings: session opening, task sequencing
observed, who leads, where the peer stalls, whiteboard use, session close. The observer is
not blinded to condition, so these notes are supporting rather than confirmatory evidence.

### A.7 Latency and error instrumentation

Server-side timing and status logging, continuous across the evaluation window, measured
at the service boundary. Client-side network cost is excluded and is stated as a
limitation.

### A.8 Extended results tables

**Table A.2** Grader agreement, extended.

*[Placeholder for the two-gate rule and each single-gate variant: percentage agreement,
Cohen's kappa with 95% bootstrap CI, precision, recall and F1. Awaiting data collection.]*

**Table A.3** Learning gain by condition, extended.

*[Placeholder for normalised gain with pre-test, post-test and gain distributions by
condition. Awaiting data collection.]*

**Table A.4** System quality measurements against ISO/IEC 25010.

*[Placeholder for functional coverage, defect density, median and p95 latency, WebSocket
message-loss rate and reconnect restoration success. Awaiting data collection.]*

### A.9 Grader-decision log specification

The single highest-value artefact to build, because it is required by RQ1 and RQ5 and is
the cheapest to add. For each evaluated submission it must persist the submission
identifier, the compilation-gate verdict with compiler diagnostics, the grading-gate
verdict, the resulting conjunctive decision, and the submission length. It does not
currently exist; Section 8.4 records its absence as the first remediation step.

---

## Appendix B Academic integrity and AI use disclosure

This appendix discloses the use of artificial intelligence tools in the production of
this thesis, as required by institutional policy. It is written to be verifiable rather
than generic.

**Table B.1** Tools used, their purpose and the affected sections.

| Tool | Purpose | Sections affected | Human verification performed |
|---|---|---|---|
| Large language model chat assistant (Anthropic Claude, via opencode) | Drafting prose, restructuring sections, generating tables and ASCII figures | All chapters, front matter, appendices | Every factual claim about the software checked against the repository at commit `7805e33` |
| Same | Suggesting literature search terms | Chapter 2 | No source was cited unless independently identified; entries marked "to verify" remain unresolved |
| Static analysis tooling (PowerShell, ripgrep) | Counting lines, enumerating routes, extracting decorators and test functions | Chapters 5, 6, 7 | Commands and outputs reproducible from the repository |
| Same | Detecting and repairing character-encoding corruption in this file | All chapters | Verified by codepoint inspection to zero remaining mojibake |

**Table B.1** AI tools used and verification performed.

**Boundaries observed.** The AI assistant did not have network access to, or knowledge of,
any unpublished data from the planned evaluation, because no such data exists. It did not
fabricate measured results, statistical test outcomes, participant numbers obtained, or
ethics approval; where the study is unexecuted, this thesis says so explicitly in
Sections 6.1 and 6.3.

**Work that is the candidate's own.** The research questions, the design decisions D1 to
D16, the requirements FR-01 to FR-23 and NFR-01 to NFR-14, the analysis plan, and the
conclusion that the evaluation objective was not met are the candidate's work, even where
the assistant drafted the prose. The decision to report an unexecuted evaluation as
unexecuted, rather than projecting plausible results, was the candidate's.

**Limitations of this disclosure.** It describes tool use in producing the written document.
It does not address the component's own use of OpenAI models at runtime, which is described
in Sections 4.4.2 and 5.2.5 and is a property of the software rather than of the thesis.

---
