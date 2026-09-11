"""
main.py — CLI entry point for ML Agent v2

Usage:
  python main.py              # start the chat UI server
  python main.py --dry-run    # start server with DRY_RUN=true (no API calls, canned responses)
  python main.py --headless   # run a single headless session (no UI, console output only)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # picks up .env in the repo root


def _check_model_access(settings) -> None:
    """
    Validates availability of API keys across registered Multi-API Providers:
    - Deep-Thinking: NVIDIA NIM (NVIDIA_API_KEY)
    - Primary:       Groq (GROQ_API_KEY)
    - Fallback:      Google Gemini (GOOGLE_API_KEY)
    """
    found_keys = []
    for provider in [
        settings.model.deep_thinking_provider,
        settings.model.primary_provider,
        settings.model.fallback_provider,
    ]:
        if provider.api_key_env and os.environ.get(provider.api_key_env):
            found_keys.append(f"{provider.api_key_env} ({provider.name})")

    if not found_keys:
        print(
            "[CONFIG WARNING] No API keys found. Set at least one of:\n"
            "  NVIDIA_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY\n"
            "  (or run with --dry-run to use canned responses)\n"
        )
    else:
        print(f"[Config] Active provider keys: {', '.join(found_keys)}")


def _langsmith_status() -> str:
    tracing_on = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
    if not tracing_on:
        return "disabled (set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to enable)"
    project = os.environ.get("LANGSMITH_PROJECT", "default")
    return f"enabled — project '{project}'"


def main():
    dry_run = "--dry-run" in sys.argv
    headless = "--headless" in sys.argv

    if dry_run:
        os.environ["DRY_RUN"] = "true"
        print("[Config] DRY-RUN mode — provider calls bypassed, canned responses used.")

    from config.settings import get_settings
    settings = get_settings()

    print("==================================================")
    print("   ML Agent v2 — Chat-Native + MCP + Multi-Provider")
    print("==================================================")
    print(f"[Config] LangSmith tracing: {_langsmith_status()}")
    _check_model_access(settings)

    if headless:
        # Headless: run a single fake session for smoke-testing
        print("[Headless] Running smoke-test session...")
        from graph.state import AgentState
        from graph.build_graph import build_app

        initial_state: AgentState = {
            "session_id": "headless_test",
            "user_message": "Predict the target column from this tabular dataset.",
            "session_data_dir": str(Path("state/sessions/headless_test/data").resolve()),
            "task_context": {
                "modality": "tabular",
                "target_column": "target",
                "target_confidence": "name_matched",
                "task_type": "binary_classification",
                "metric": "roc_auc",
                "column_names": ["id", "feature_1", "feature_2", "target"],
                "session_data_dir": str(Path("state/sessions/headless_test/data").resolve()),
                "task_id": "headless_test",
                "task_name": "Headless Test Task",
                "sample_submission_format": {"id_column": "id", "pred_column": "target"},
            },
            "target_confidence": "name_matched",
            "current_spec": None,
            "last_escalation": None,
            "last_redirect": None,
            "reasoning_mode": "default",
            "actions_remaining": settings.budget.actions_total,
            "time_remaining": float(settings.budget.time_total_minutes),
            "status": "planning",
            "eda_report_markdown": "",
            "pending_human_question": None,
            "human_answer": None,
            "event_queue": [],
            "dry_run": dry_run or True,  # headless always dry-runs
        }

        Path("state/sessions/headless_test/data").mkdir(parents=True, exist_ok=True)
        log = Path("state/sessions/headless_test/experiment_log.jsonl")
        if log.exists():
            log.unlink()

        app_graph = build_app()
        final_state = app_graph.invoke(
            initial_state,
            config={"recursion_limit": 50, "configurable": {"thread_id": "headless_test"}},
        )

        print(f"\n[Headless] Final status: {final_state.get('status')}")
        print(f"[Headless] Events emitted: {len(final_state.get('event_queue', []))}")
        for ev in final_state.get("event_queue", [])[:10]:
            print(f"  [{ev.get('type')}] {ev.get('node', '')} {ev.get('content', ev.get('detail', ''))[:80]}")
        return

    # Default: start the chat UI server
    print("[Server] Starting ML Agent chat UI on http://127.0.0.1:8000")
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=not dry_run)


if __name__ == "__main__":
    main()