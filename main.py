"""
CLI entry point.

Usage:
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --mode full_pipeline
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --mode eda_only
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --guided

If the pipeline pauses for human approval (guided mode or destructive action),
the CLI will prompt for a decision (approved / modify / reject) and resume the
graph rather than leaving the run stranded. The same Command(resume=...) path
the server uses is used here, so headless/CLI runs fully work without a server.
"""
import argparse
import sys

from langgraph.types import Command

from state import build_initial_state
from graph import build_graph
from tools.logger import get_logger


def _stream_graph(graph, stream_input, config, logger):
    """Run graph.stream and log each completed node. Returns True if the run paused."""
    for event in graph.stream(stream_input, config=config):
        for node in event:
            logger.info("Node '%s' completed.", node)

    final_state = graph.get_state(config)
    return bool(final_state.next), final_state


def main():
    parser = argparse.ArgumentParser(description="Run the multi-agent ML pipeline.")
    parser.add_argument("--dataset", required=True, help="Path to a .csv or .parquet dataset")
    parser.add_argument("--mode", choices=["eda_only", "full_pipeline"], default="full_pipeline")
    parser.add_argument("--guided", action="store_true", help="Require approval on every feature step")
    args = parser.parse_args()

    initial_state = build_initial_state(
        dataset_path=args.dataset,
        mode=args.mode,
        guided_mode=args.guided,
    )
    run_id = initial_state["run_id"]
    logger = get_logger(run_id)
    logger.info("Starting run %s for dataset %s (mode=%s, guided=%s)",
                run_id, args.dataset, args.mode, args.guided)

    graph = build_graph()
    config = {"configurable": {"thread_id": run_id}}

    stream_input = initial_state

    while True:
        paused, final_state = _stream_graph(graph, stream_input, config, logger)

        if not paused:
            print("\nRun complete. Final report:\n")
            print(final_state.values.get("report", "(no report generated — check --mode/next_agent routing)"))
            break

        # Paused for human approval — prompt for decision
        reason = final_state.values.get("approval_reason", "unknown")
        feature_plan = final_state.values.get("feature_plan") or {}
        print(f"\n{'='*60}")
        print(f"⏸  Run paused — approval required")
        print(f"   Reason: {reason}")
        if feature_plan.get("description"):
            print(f"   Proposed step: {feature_plan['description']}")
        diff = feature_plan.get("structural_diff") or {}
        if diff.get("dropped_columns"):
            print(f"   Dropped columns: {', '.join(diff['dropped_columns'])}")
        if diff.get("row_delta") is not None and diff["row_delta"] != 0:
            print(f"   Row delta: {diff['row_delta']}")
        print(f"{'='*60}")
        print("Choices: [approved] continue  [modify] re-engineer  [reject] abort retry")

        while True:
            try:
                choice = input("Decision [approved/modify/reject]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(1)

            if choice in ("approved", "modify", "reject"):
                break
            print(f"  Invalid choice '{choice}'. Enter approved, modify, or reject.")

        logger.info("CLI resume decision: %s", choice)
        stream_input = Command(resume={"approval_status": choice})

        if choice == "reject":
            print("Rejected — pipeline will route to supervisor for next action.")
        elif choice == "modify":
            print("Modify — pipeline will return to Features for re-engineering.")
        else:
            print("Approved — pipeline resuming...")


if __name__ == "__main__":
    main()
