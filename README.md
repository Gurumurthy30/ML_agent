# Multi-Agent ML Pipeline

An autonomous Machine Learning pipeline powered by **LangGraph** that mimics how experienced data scientists work: profiling data, discovering patterns, iteratively engineering features on evolving datasets, and training/evaluating candidate model families.

---

## Architecture

```
               ┌───────────────┐
               │  Supervisor   │◄─────────────────────────────┐
               └──────┬────────┘                              │
                      │                                       │
     ┌────────────────┼────────────────┬──────────────┐       │
     ▼                ▼                ▼              ▼       │
┌──────────┐    ┌──────────┐     ┌───────────┐  ┌───────────┐ │
│ Profiler │    │   EDA    │     │ Features  │  │  Modeler  │ │
└────┬─────┘    └────┬─────┘     └─────┬─────┘  └─────┬─────┘ │
     │               │                 │              │       │
     └───────────────┴─────────────────┼──────────────┴───────┘
                                       ▼ (Completion)
                                     [ END ]
```

- **Supervisor**: Central router orchestrating phase transitions based on dataset state, completion flags, and safety budgets.
- **Profiler**: Automated statistical analysis and Kaggle-style multi-modality sniffing (tabular, image, audio, free text).
- **EDA Agent**: Hypothesis-driven exploratory data analysis generating narrative findings and correlation signals.
- **Features Agent**: Incremental feature engineering with structural-diff checking and transformation pipelines.
- **Coder Sub-Agent**: Generates and executes pandas/sklearn code in isolated subprocesses with automated retry-and-repair loops.
- **Modeler Agent**: Incremental model exploration, hyperparameter tuning, and candidate validation scoring across diverse algorithm families.

---

## Setup & Prerequisites

Python 3.10+ is required.

```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install core pipeline dependencies
pip install -r requirements.txt

# (Optional) Install heavy multi-modal modeling libraries (torch, torchvision, librosa, transformers)
pip install -r requirements-modalities.txt
```

### Environment Variables
Create a `.env` file at the repository root (see `.env.example`):

```bash
# --- LLM Authentication ---
OLLAMA_API_KEY=your_ollama_api_key_here

# --- Optional LangSmith Observability ---
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=ML_agent
```

### Pipeline Configuration (`config.py`)
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

```powershell
# Full autonomous pipeline
.venv\Scripts\python.exe main.py --dataset data/sample.csv --mode full_pipeline

# EDA only
.venv\Scripts\python.exe main.py --dataset data/sample.csv --mode eda_only
```

---

## Key Features

- **Autonomous Execution**: Direct end-to-end execution without manual blocking or halts.
- **Multi-Algorithm Exploration**: Automated model family exploration (LightGBM, XGBoost, Random Forest, Logistic Regression, etc.) with cross-validation scoring.
- **Loop Escape Control**: Force-advance stuck coder loops or repetitive exploration attempts without aborting the entire run.
- **MCP Code Execution**: Code is executed via an MCP server subprocess with automatic fallback to direct in-process execution.
- **Scoped Memory**: Each agent maintains private and shared summarization memory to avoid repeating mistakes and guide exploration.
- **Run Telemetry**: Dual-persistence event logging (JSONL + SQLite) for run inspection and debugging.

---

## Test Suite

```powershell
.venv\Scripts\python -m pytest tests/ -v
```
