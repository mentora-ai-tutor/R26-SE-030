# Backend Test Suite

Central test suites for every backend service in the Mentora platform. Each
service gets its own folder with three layers:

```
test/
├── package.json                # node scripts to run the JS/Node suites
├── user-service/               # Jest
│   ├── unit/
│   ├── integration/
│   └── performance/
├── learning-generator/         # node:test (built-in test runner)
│   ├── unit/
│   ├── integration/
│   ├── performance/
│   └── support/                # module shims (mongoose/winston/dotenv)
├── assessment-agent/           # Jest
│   ├── unit/
│   ├── integration/
│   └── performance/
├── knowledge-analysis/         # pytest
│   ├── unit/
│   ├── integration/
│   └── performance/
├── peer-learning/              # pytest
│   ├── unit/
│   ├── integration/
│   └── performance/
└── ai-engine/                  # pytest
    ├── unit/
    ├── integration/
    └── performance/
```

Test layers:

| Layer         | Purpose |
|---------------|---------|
| `unit/`       | Pure logic: services, helpers, models, validation, response shaping. No I/O. |
| `integration/`| Routes/endpoints over the real app wiring with persistence and external clients mocked (no real MongoDB/Ollama/n8n/network). |
| `performance/`| Timing checks with generous thresholds (and measured timings logged) to catch regressions without flaky CI. |

All tests are **self-contained** — no real databases, LLM providers, or network
calls are required to run them.

---

## Prerequisites

- **Node.js** `>= 21` (Node 22 LTS **recommended**, and what CI uses) for the
  JavaScript suites. `node --test` glob arguments need Node 21+ — on Node 20 a
  glob like `"learning-generator/**/*.test.js"` is treated as a literal path and
  fails, and bare-directory scanning is broken on some Node 25.x builds.
- **Python 3.11+** with `pytest`, `fastapi` and `httpx` installed for the
  Python suites:
  ```bash
  pip install pytest fastapi httpx
  ```
- Jest and supertest are already declared in `test/package.json`.

---

## Run everything

```bash
cd mentora-backend/test
npm install        # first time only (installs jest + supertest)

npm test           # Node suites: user-service, assessment-agent, learning-generator
```

Then run the Python suites from the repo root:

```bash
cd /Volumes/My Data/SLIIT/Research/PP2/mentora-backend
python3 -m pytest test/knowledge-analysis -q
python3 -m pytest test/peer-learning       -q
python3 -m pytest test/ai-engine           -q
```

> We recommend running the Node suites from `test/` and the Python suites from
> the repo root (this is how the `npm run test:*` helpers and `conftest.py`
> sys.path wiring are set up).
>
> **Python services must each be run as their own pytest invocation** (one
> process per service). `knowledge-analysis`, `peer-learning` and `ai-engine`
> each ship a top-level `app` package, so collecting two or more of them in a
> single `pytest test/a test/b` command makes `import app` resolve to the wrong
> service and fails at collection. The separate commands in this section are
> the supported way to run them.

---

## Run a single service

### Node (Jest) — user-service / assessment-agent

```bash
cd mentora-backend/test
npx jest --silent user-service
npx jest --silent assessment-agent
```

### Node (node:test) — learning-generator

```bash
cd mentora-backend/test
node --test --test-reporter=dot "learning-generator/**/*.test.js"
```

### Python (pytest) — knowledge-analysis / peer-learning / ai-engine

```bash
cd /Volumes/My Data/SLIIT/Research/PP2/mentora-backend
python3 -m pytest test/knowledge-analysis -q
python3 -m pytest test/peer-learning       -q
python3 -m pytest test/ai-engine           -q
```

Run a single file:

```bash
python3 -m pytest test/ai-engine/unit/test_ollama_service.py -q
npx jest --silent user-service/unit/student.model.test.js
node --test "learning-generator/unit/material.service.test.js"
```

---

## Current status (verified)

| Service          | Runner      | Layer counts            | Result |
|------------------|-------------|-------------------------|--------|
| user-service     | Jest        | 10 unit · 6 integration · 2 perf | 18 passed |
| learning-generator | node:test  | 19 unit · 5 integration · 2 perf | 26 passed |
| assessment-agent | Jest        | 45 unit · 13 integration · 2 perf | 60 passed |
| knowledge-analysis | pytest    | 21 unit · 7 integration · 3 perf | 31 passed |
| peer-learning    | pytest      | 11 unit · 8 integration · 3 perf | 22 passed |
| ai-engine        | pytest      | 23 unit · 6 integration · 2 perf | 31 passed |

All suites run in seconds with no external dependencies.

---

## Notes

- Service source code is never modified by these tests; they only import it.
- Mocking strategy per service:
  - **Jest suites** use `jest.mock(...)` factories (and small in-folder helper
    shims where a dependency like `express` is unavailable).
  - **node:test suite** uses `node:test` `mock.method` plus minimal module shims
    under `support/`.
  - **pytest suites** use fixtures, `dependency_overrides`, `monkeypatch`, and
    a `conftest.py` that adds the service package to `sys.path`; heavy optional
    deps (e.g. `openai`, `langchain_openai`, `google-genai`) are stubbed or
    bypassed so the host does not need them installed.
- `performance/` thresholds are deliberately generous to avoid flaky CI; they
  catch gross regressions and print measured timings.