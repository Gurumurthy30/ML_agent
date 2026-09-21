# Multi-Agent ML Pipeline & Telemetry Studio

An autonomous, iterative Machine Learning pipeline powered by **LangGraph**, paired with a **FastAPI** telemetry backend and a modern **React 19** observability dashboard.

The system mimics how experienced data scientists work: profiling data, discovering patterns, iteratively engineering features on evolving datasets, hyperparameter tuning across candidate model families, and performing rigorous executive reviews with automated retry escalation and genuine human-in-the-loop safety gating.

---

## Architecture at a Glance

### 1. LangGraph Agent Pipeline
```
               ┌───────────────┐
               │  Supervisor   │◄─────────────────────────────┐
               └──────┬────────┘                              │
                      │                                       │
     ┌────────────────┼────────────────┬──────────────┐       │
     ▼                ▼                ▼              ▼       │
┌──────────┐    ┌──────────┐     ┌───────────┐  ┌───────────┐ │ (Retry / Loop)
│ Profiler │    │   EDA    │     │ Features  │  │  Modeler  │ │
└────┬─────┘    └────┬─────┘     └─────┬─────┘  └─────┬─────┘ │
     │               │                 │              │       │
     └───────────────┴─────────────────┼──────────────┴───────┘
                                       │
                         [Guided / Destructive Gate]
                                       ▼
                             ┌───────────────────┐
                             │  Human Approval   │ (Interactive Pause)
                             │   (UI Queue)      │
                             └─────────┬─────────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │ Judge Agent │───► [Reject: Tier 1/2] ──► Supervisor
                                └──────┬──────┘
                                       │ [Accept]
                                       ▼
                                ┌─────────────┐
                                │  Reporter   │───► Final Report & Artifacts
                                └─────────────┘
```

- **Supervisor**: Central router orchestrating phase transitions based on dataset state, convergence flags, and retry budgets.
- **Profiler**: Automated statistical analysis and Kaggle-style multi-modality sniffing (tabular, image, audio, free text).
- **EDA Agent**: Hypothesis-driven exploratory data analysis generating narrative findings and correlation signals.
- **Features Agent**: Incremental feature engineering with structural-diff checking and self-reported risk assessment.
- **Coder Sub-Agent**: Generates and executes pandas/sklearn code in isolated subprocesses with automated retry-and-repair loops.
- **Modeler Agent**: Incremental model exploration, hyperparameter tuning (Tier-0), and plateau backstops.
- **Judge Agent**: Rigorous executive evaluation against baseline thresholds, routing rejections to Tier 1 (model family) or Tier 2 (feature re-engineering).
- **Human Approval**: LangGraph `interrupt()` pause gate triggered on destructive transformations or guided mode.
- **Reporter**: Compiles comprehensive execution narratives, telemetry metrics, and persists to local RAG vector memory.

### 2. Backend & Frontend Architecture
- **FastAPI Layer (`api/main.py`)**: Asynchronous REST API managing background run lifecycles, database operations, and live log broadcasting.
- **Telemetry & Tracer (`tools/tracer.py`)**: Dual-persistence engine recording append-only JSONL event streams and thread-safe SQLite indexing (`runs/runs_index.db`).
- **Server-Sent Events (SSE)**: Real-time event streaming (`GET /runs/{id}/events`) combining historical replay and live pub/sub broadcasting.
- **React Frontend (`frontend/`)**: Modern React 19 + Tailwind CSS single-page application with 9 dedicated diagnostic tabs and an interactive Approval Queue.

---

## Setup & Prerequisites

### 1. Backend Setup
Python 3.10+ is required.

```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install core pipeline & API dependencies
pip install -r requirements.txt

# (Optional) Install heavy multi-modal modeling libraries (torch, torchvision, librosa, transformers)
pip install -r requirements-modalities.txt
```

### 2. Frontend Setup
Node.js 18+ is required.

```powershell
cd frontend
npm install
cd ..
```

### 3. Environment Variables
Create a `.env` file at the repository root (see `.env.example`):

```bash
# --- LLM Authentication ---
OLLAMA_API_KEY=your_ollama_api_key_here

# --- Optional LangSmith Observability ---
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=ML_agent
```

#### Pipeline Configuration (`config.py`)
All execution limits and convergence criteria can be customized via environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PIPELINE_GLOBAL_ITER_CEILING` | `200` | Hard circuit breaker preventing infinite supervisor cycling. |
| `PIPELINE_LOOP_SAFETY_CEILING` | `30` | Per-agent exploration ceiling, auto-scaled by data complexity. |
| `PIPELINE_METRIC_EPSILON` | `0.001` | Minimum delta required to count an iteration as an improvement. |
| `PIPELINE_TIER1_BUDGET` | `2` | Maximum automated Modeler retry attempts before escalation. |
| `PIPELINE_TIER2_BUDGET` | `2` | Maximum automated Features retry attempts before escalation. |
| `PIPELINE_CONVERGENCE_PATIENCE`| `3` | Consecutive non-improving steps before plateau detection triggers. |
| `PIPELINE_RUNS_DIR` | `runs` | Directory for SQLite indices, checkpoints, and event logs. |
| `PIPELINE_LOG_DIR` | `logs` | Directory for run execution logs. |

---

## Running the Pipeline

### Path A: Full Web Application (Recommended)

1. **Start the FastAPI Backend**:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
   ```

2. **Start the React Frontend Dev Server**:
   ```powershell
   cd frontend
   npm run dev
   ```

3. Open **`http://localhost:5173/`** in your browser.

### Path B: Command-Line Interface (CLI)

Run directly against any dataset file (`.csv` or `.parquet`):

```powershell
# Full autonomous pipeline
.venv\Scripts\python.exe main.py --dataset data/sample.csv --mode full_pipeline

# EDA only
.venv\Scripts\python.exe main.py --dataset data/sample.csv --mode eda_only

# Guided mode (requires manual approval on feature modifications)
.venv\Scripts\python.exe main.py --dataset data/sample.csv --guided
```

---

## Key Features

- **Guided Mode & Human Approval Hard-Block**: When enabled, or whenever a destructive feature transformation is proposed (e.g., column drop, row deletion), graph execution genuinely pauses with a checkpoint. Human operators can inspect the proposed code and schema diff, and choose to **Approve**, **Reject**, or provide **Modify** instructions (e.g., *"Keep age column and impute with median"*), which are threaded directly into the Features agent's prompt on resume.
- **Dataset Preview**: Live inspection of original and transformed datasets directly inside the UI, powered by `GET /runs/{id}/dataset-preview` with parquet/csv support and sanitized JSON streaming.
- **Multi-Tier Automated Retries**:
  - *Tier 0*: Internal hyperparameter tuning and model iteration within Modeler.
  - *Tier 1*: Judge-prompted model family re-selection routed back to Modeler.
  - *Tier 2*: Judge-prompted feature re-engineering routed back to Features.
- **Loop Escape Control (`⚡ Escape Loop`)**: Operators can force-advance stuck coder loops or repetitive exploration attempts without aborting the entire run.
- **Side-by-Side Run Comparison**: Compare candidate runs across scores, duration, token usage, and generated Python model code.
- **ZIP Debug Bundle Export**: Download self-contained debug archives containing `events.jsonl`, `state.json`, `best_model_code.py`, `metrics.csv`, and reports.

---

## Test Suite

The project includes unit, regression, fault-injection, and UI smoke test suites:

| Suite | Command | Passing Tests |
| :--- | :--- | :--- |
| **Backend Integration & Unit Tests** | `.venv\Scripts\pytest.exe tests/` | **112 / 112** |
| **Deterministic Smoke Test** | `.venv\Scripts\python.exe smoke_test.py` | **61 / 61** |
| **Frontend Component & Interaction Tests** | `cd frontend; npm test` | **27 / 27** |
| **Total Test Checks** | | **200 Passed (100%)** |

---

## Project History & Engineering Notes

For deep-dive documentation on architectural evolution, hardening rounds, and telemetry redesign:
- [AUDIT_REPORT.md](file:///c:/Users/gurum/Documents/4_Projects/ML_agent/AUDIT_REPORT.md): Full audit history covering fault injections, scoped memory redesign, reducer fixations, and stall detectors across Rounds 1–5.
- [FRONTEND_BUILD_REPORT.md](file:///c:/Users/gurum/Documents/4_Projects/ML_agent/FRONTEND_BUILD_REPORT.md): Design system decisions, React 19 setup, SSE connection management, and Approval Queue wiring.
