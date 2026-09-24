# Agentic Tabular ML Engineering Platform — Master Spec

> Save this file at `docs/PROJECT_SPEC.md` in the repo. Every phase prompt below tells
> the agent to read it first. This file is the single source of truth for scope —
> if a phase prompt is ambiguous, this file wins.

## 1. One-line description

An autonomous, Claude-Code-style workspace: the user uploads a tabular dataset, sets a
target column and an optional metric, and a small team of LLM agents — orchestrated by
LangGraph — profiles the data, explores it, engineers features, trains scikit-learn
models, evaluates them, loops when needed, and writes a final report. **No plots
anywhere.** Every agent output is structured text, JSON, or tables.

## 2. Locked scope decisions

Do not deviate from these without asking the user first.

- **Task types:** binary classification, multiclass classification, regression only.
  No vision, no NLP, no time-series/forecasting.
- **Models:** scikit-learn only. No LightGBM/XGBoost/CatBoost/deep learning.
- **Visualization:** zero plots or charts anywhere — not in EDA, not in Evaluator
  diagnostics, not in the leaderboard, not anywhere in the UI. Everything is text,
  numbers, or tables.
- **LLM:** Ollama only, model `gpt-oss:120b`. No other provider is wired up for v1,
  but keep a thin router abstraction so a provider/model can be swapped later without
  touching agent code.
- **Experiment tracking:** MLflow, local tracking store.
- **App metadata storage:** SQLite.
- **Code execution:** plain `subprocess`, per-run working-directory isolation,
  **no timeout enforcement** (explicit choice — trusted local/single-user tool, not
  multi-tenant).
- **No auth, no multi-user, no Docker sandboxing, no pause/resume/cancel** for v1.
  These are documented as stretch goals only — do not build them unless asked.
- **Build order:** Phase 1 (core agent layer: agents, memory, tools) → Phase 2
  (FastAPI backend) → Phase 3 (React/Tailwind frontend). Each phase must run and
  satisfy its own Definition of Done before the next phase starts.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Agent/LLM abstraction | LangChain (`langchain-ollama`) |
| LLM | Ollama, model tag `gpt-oss:120b` |
| Tabular ML | scikit-learn, pandas, numpy, pyarrow |
| Experiment tracking | MLflow (local sqlite backend store + local file artifact store) |
| App DB | SQLite via SQLModel |
| Code execution | Python `subprocess`, per-run temp working dir |
| Backend API | FastAPI |
| Realtime updates | Server-Sent Events (SSE) |
| Frontend | React + Vite + TypeScript + Tailwind CSS |
| Frontend libs | TanStack React Query (server state), Zustand (UI state), shadcn/ui (components) |

## 4. Project directory layout

```text
projects/
└── <project_id>/
    ├── datasets/
    │   ├── dataset_v1/
    │   └── dataset_v2/
    ├── profile/
    ├── eda/
    │   ├── findings.json
    │   └── summary.md          # no plots/ subfolder — text only
    ├── features/
    │   ├── feature_data.parquet
    │   ├── feature_pipeline.py
    │   ├── feature_schema.json
    │   └── feature_report.md
    ├── models/                 # pickled sklearn models per experiment
    ├── evaluations/
    ├── reports/
    │   ├── final_report.md
    │   └── summary.json
    ├── memory/                 # supervisor + per-stage memory snapshots
    ├── runs/                   # workflow run metadata (mirrors SQLite, human-readable)
    └── workspace/              # Coder's scratch/execution directory, wiped per run
```

MLflow's own tracking store (sqlite + artifact files) lives outside `projects/`, e.g.
`./mlruns/` + `./mlflow.db` at the repo root, with one MLflow **experiment** per
project (`experiment_name = project_id`) and one MLflow **run** per model training
attempt.

## 5. Agents

| Agent | Uses LLM? | Responsibility |
|---|---|---|
| **Supervisor** | Yes | Planner/router/reviewer. Understands goal + state, dispatches to the right agent, reviews each agent's structured output, decides pass/retry/improve, routes the Model↔Evaluator loop, triggers Report. Never does EDA/modeling itself. |
| **Profile** | **No — plain Python** | Deterministic dataset profiling: shape, dtypes, missingness, duplicates, cardinality, constant/near-constant columns, target distribution, initial `task_type` guess (one of the three allowed types, or "ambiguous"). |
| **EDA** | Yes | Adaptive, task-driven analysis. Decides which analyses matter (skew, outliers, leakage, class imbalance, feature-target relationships, correlations) given the task type — never runs a fixed checklist. Uses Coder for computation. Output is **findings only**, in text/JSON — no images. |
| **Feature Engineering** | Yes | Turns EDA findings into a versioned, reproducible feature pipeline (encoding, scaling, imputation, transforms, interactions). Tracks per-feature metadata: source, transformation, reason, EDA evidence, leakage check, inference-time availability. |
| **Model** | Yes | Chooses validation strategy + candidate sklearn models based on task type, data size/shape, and target metric (e.g. `LogisticRegression`/`LinearRegression` baseline, `RandomForest*`, `GradientBoosting*`, optionally `SVC`/`SVR`, `KNeighbors*`). Trains via Coder, logs every attempt to MLflow. |
| **Evaluator** | Yes | Independent reviewer — does not trust Model's self-report. Chooses relevant checks per task (train/val gap, overfitting, leakage, class imbalance, metric appropriateness). Returns `PASS` or `IMPROVE` with structured reasons and a recommended next stage (`feature_engineering` or `model`). |
| **Report** | Yes | Summarizes the finished project from existing artifacts only (no re-analysis): objective, profile, EDA findings, features, experiments, best model, limitations, recommendations. Pure markdown + JSON, no charts. |
| **Coder** *(sub-agent, not a graph stage)* | Yes | Reusable code-writing/execution helper invoked by EDA, Feature Engineering, Model, and Evaluator. Receives a narrow, precise task (no project history dump), writes Python, runs it via the Execution Manager, captures stdout/stderr/exit code, debugs+retries on failure, returns a structured result. |

## 6. LangGraph workflow

```text
START → supervisor → profile → supervisor → eda → supervisor → features
      → supervisor → model → supervisor → evaluator → supervisor
                                                          │
                                          ┌───────────────┴───────────────┐
                                          │                               │
                                        PASS                          IMPROVE
                                          │                               │
                                          ▼                               ▼
                                        report          supervisor picks next stage:
                                                         "feature_engineering" (default)
                                                         or "model" (model-only issue)
                                                                  │
                                                                  ▼
                                                          features → model → evaluator → supervisor (loop)
```

The Supervisor is the only node with conditional routing logic. The Model↔Evaluator
loop is bounded by a configurable `max_iterations` (default 3). On reaching the limit
without a PASS, go straight to Report with the best model found so far and an explicit
"iteration limit reached" note.

## 7. State schema (tabular-only)

```python
class TaskType(str, Enum):
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"
    AMBIGUOUS = "ambiguous"

class ProjectState(TypedDict):
    project_id: str
    run_id: str
    user_goal: str
    target_column: str | None
    target_metric: str | None          # e.g. "f1", "roc_auc", "rmse", "r2"
    description: str | None
    constraints: dict

    dataset_id: str
    dataset_version: str

    task_type: TaskType | None

    profile_summary: dict
    eda_findings: dict
    feature_summary: dict
    model_summary: dict
    evaluation_summary: dict

    current_stage: str
    iteration: int
    max_iterations: int

    best_experiment_id: str | None     # MLflow run_id
    best_metric_value: float | None

    supervisor_memory: dict
    artifacts: list[dict]              # references only, never raw content

    next_action: str | None
    status: Literal["SUCCESS", "FAILED", "NEEDS_INPUT", "RETRY", "RUNNING"]
```

No raw dataset content, no full source files, no long conversation history goes into
this state — only summaries and artifact references.

## 8. Memory

- **Supervisor** keeps persistent per-project memory: goal, target, key findings,
  decisions made, best experiment, current stage, iteration count, known issues,
  recommendations, artifact references. Nothing raw.
- Other agents only receive: the relevant stage-specific summary + whatever the
  Supervisor decides to forward — never the full history of every other agent.
- Never store: full Python files, raw logs, duplicated dataset content, entire
  conversation transcripts.

## 9. Tool registry

Expose tools through one internal registry so each agent only gets what it needs.
Build this as a small local tool-server layer (MCP-style: named tools with typed
input/output schemas, addressable by name) rather than hard-wiring tool objects into
each agent — this keeps it swappable later without being over-engineered for v1.

| Tool | Used by |
|---|---|
| `read_file` / `write_file` / `list_dir` | Coder, all stage agents |
| `run_python` (→ Execution Manager → subprocess) | Coder only |
| `dataset_tools` (load/sample/schema a versioned dataset) | Profile, EDA, Feature Eng |
| `mlflow_log` (log params/metrics/tags/artifacts, register best run) | Model, Evaluator |
| `artifact_index` (register an artifact in SQLite) | all stage agents |

No plotting tool exists in this registry — do not add one.

## 10. ModelRouter & Ollama config

```python
router = ModelRouter()
model = router.get_model("supervisor")   # same call shape for every agent role
```

- All roles (`supervisor`, `eda`, `features`, `model`, `evaluator`, `report`, `coder`)
  default to the **same** Ollama model for v1: env `OLLAMA_MODEL` (default
  `gpt-oss:120b`).
- Client points at env `OLLAMA_BASE_URL` (default `http://localhost:11434`), i.e. the
  local Ollama daemon running the cloud-backed model (`ollama run gpt-oss:120b-cloud`
  after `ollama signin`). Optional `OLLAMA_API_KEY` env var, only sent as a header if
  set — leave unset by default.
- **Assumption flag:** if the user's actual Ollama Cloud setup uses a different base
  URL or auth mechanism, only `.env` / the router's config needs to change — no agent
  code should reference Ollama specifics directly.
- Use structured output (Pydantic schemas via LangChain's `with_structured_output` or
  equivalent) for every agent's return value — Profile summaries, EDA findings,
  feature metadata, evaluator verdicts must all be typed, not free text.

## 11. MLflow design

- One MLflow **experiment** per project (`experiment_name = project_id`).
- One MLflow **run** per model training attempt, logging: params (model type,
  hyperparameters), metrics (target metric + a small standard set for the task type),
  tags (`dataset_version`, `feature_version`, `evaluator_status`), and artifacts
  (pickled model, predictions file).
- Leaderboard = query runs for a project's experiment, sorted by the **target
  metric**, with an explicit per-metric direction map (e.g. `rmse`/`mae` → lower is
  better; `f1`/`roc_auc`/`accuracy`/`r2` → higher is better). Never assume
  higher-is-better globally.

## 12. Storage split

- **SQLite (SQLModel):** `Project`, `Dataset` (+version), `WorkflowRun`,
  `EDAFinding`, `FeatureVersion`, `ArtifactIndex`, `Event`, `SupervisorMemory`.
- **Filesystem:** everything under `projects/<id>/...` as in §4.
- **MLflow's own store:** experiments/runs/model artifacts — do not duplicate this
  data into SQLite; query MLflow directly for the leaderboard and experiment detail.

## 13. Code execution (Coder + Execution Manager)

```text
Coder → Execution Manager → subprocess → per-run temp working dir → stdout/stderr/artifacts
```

- Each run gets its own temp working directory under `projects/<id>/workspace/`,
  wiped/recreated per invocation.
- Capture stdout, stderr, and exit code; detect failure; allow Coder to debug and
  retry (bounded retry count, e.g. 2).
- **No timeout enforcement** — explicit user choice, do not add one.
- Basic path validation only (no path traversal outside the project workspace) — do
  not build full sandboxing/resource limits for v1.

## 14. Error handling

Every agent returns one of: `SUCCESS`, `FAILED`, `NEEDS_INPUT`, `RETRY`. On repeated
failure, the Supervisor decides: retry / try an alternate approach / surface a
`NEEDS_INPUT` state (do not silently continue past a failed critical step).

## 15. Definition of done (v1)

A user can: create a project → upload a CSV → set target (+ optional metric) → start
a run → watch Supervisor drive Profile → EDA → Features → Model → Evaluator, looping
as needed → see the model leaderboard (table, MLflow-backed) → see the final report →
trace the best model back to its dataset version, feature version, and MLflow run —
all with **zero images/plots** generated or displayed anywhere in the system.

## 16. How to use these files with Antigravity

1. Save this file at `docs/PROJECT_SPEC.md` in the repo before starting anything.
2. Run `01_PHASE1_CORE_AGENTS.md` as one Agent Manager task. Let it finish and
   verify its Definition of Done.
3. Then run `02_PHASE2_BACKEND.md` as a separate task.
4. Then run `03_PHASE3_FRONTEND.md` as a separate task.

Don't paste all three phase prompts into a single task — Antigravity performs better
with one focused goal per task than one giant multi-feature prompt.
