"""
CLI entry point.

Usage:
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --mode full_pipeline
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --mode eda_only
    OLLAMA_API_KEY=... python main.py --dataset path/to/data.csv --guided
"""
import argparse

from state import build_initial_state
from graph import build_graph
from tools.logger import get_logger


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

    for event in graph.stream(initial_state, config=config):
        for node in event:
            logger.info("Node '%s' completed.", node)

    final_state = graph.get_state(config)
    if final_state.next:
        logger.warning("Run paused, awaiting human approval on thread_id=%s", run_id)
        print(f"\nPaused for human approval. Resume by re-running with thread_id={run_id} "
              f"and Command(resume={{'approval_status': 'approved'}}).")
    else:
        print("\nRun complete. Final report:\n")
        print(final_state.values.get("report", "(no report generated — check --mode/next_agent routing)"))


if __name__ == "__main__":
    main()
