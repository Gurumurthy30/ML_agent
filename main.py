import sys
import json
import time
from pathlib import Path

from config.settings import get_settings
from graph.state import AgentState
from graph.build_graph import build_app

def main():
    print("==================================================")
    print("      MLE Multi-Agent System (mle-agent)        ")
    print("==================================================")

    # 1. Load Settings
    try:
        settings = get_settings()
        print(f"[Config] Loaded settings. Server URL: {settings.model.server_url}, Mock Mode: {settings.mle_dojo.use_mock}")
    except Exception as e:
        print(f"[Config Error] Failed to load configuration: {e}")
        sys.exit(1)

    # 2. Check local_model_path requirement if not in mock mode
    if not settings.mle_dojo.use_mock:
        try:
            settings.model.validate_local_path(require_exists=True)
        except ValueError as ve:
            print(str(ve))
            sys.exit(1)
    else:
        print("[Notice] Running in mock_server.py mode (no live MLE-Dojo connection required).")

    # 3. Initialize AgentState
    initial_state: AgentState = {
        "task_context": {},
        "current_spec": None,
        "last_escalation": None,
        "last_redirect": None,
        "reasoning_mode": "default",
        "actions_remaining": settings.budget.actions_total,
        "time_remaining": float(settings.budget.time_total_minutes),
        "status": "planning"
    }

    # Clean state directory for new run
    state_dir = Path(__file__).parent / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_file = state_dir / "experiment_log.jsonl"
    if log_file.exists():
        log_file.unlink()

    # 4. Build and Run App Graph
    print("[Graph] Building LangGraph graph workflow...")
    app = build_app()

    start_wall_time = time.time()
    print("[Graph] Starting multi-agent optimization loop...")
    final_state = app.invoke(initial_state, config={"recursion_limit": 100}) if hasattr(app, 'invoke') and 'config' in app.invoke.__code__.co_varnames else app.invoke(initial_state)
    total_elapsed_sec = time.time() - start_wall_time

    # 5. Output Run Summary
    print("\n==================================================")
    print("             Execution Run Summary                ")
    print("==================================================")
    print(f"Final Status:      {final_state.get('status')}")
    print(f"Actions Remaining: {final_state.get('actions_remaining')} / {settings.budget.actions_total}")
    print(f"Time Remaining:    {final_state.get('time_remaining'):.2f} / {settings.budget.time_total_minutes:.2f} mins")
    print(f"Total Wall Clock:  {total_elapsed_sec:.2f} seconds")

    if log_file.exists():
        print(f"\nExperiment Log ({log_file}):")
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    print(f"  [{entry['experiment_id']}] {entry['model_type']} | CV Mean: {entry['cv_mean']} (std: {entry['cv_std']}) | Score: {entry['submission_score']}")

    print("\n[Done] Execution finished successfully.")

if __name__ == "__main__":
    main()
