"""
Local logging utility for the multi-agent ML pipeline.

Provides:
  - get_logger(run_id): a standard Python logger writing to console (INFO+) and to
    a per-run log file `logs/<run_id>.log` (DEBUG+), for human-readable monitoring
    while a run is in progress.
  - log_event(run_id, agent, event_type, **payload): appends one structured JSON line
    to `logs/<run_id>.events.jsonl`. This is the machine-readable trace that the
    Reporter agent reads back to build the "monitor everything" section of the final
    report — exact counts/durations rather than an LLM trying to remember what happened.
  - read_events(run_id): reads back all structured events for a run.
  - step_timer(run_id, agent, step_name): context manager that auto-logs a
    step_start/step_end (or step_error) pair with duration, so every agent's timing
    shows up in the trace for free.
"""
import json
import logging
import os
import queue
import threading
import time
import contextlib
from datetime import datetime, timezone

LOG_DIR = os.environ.get("PIPELINE_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_loggers = {}
_subscribers_lock = threading.Lock()
_subscribers: dict[str, list[queue.Queue]] = {}


def subscribe(run_id: str) -> queue.Queue:
    """Backend API layer calls this once per SSE connection."""
    q = queue.Queue()
    with _subscribers_lock:
        _subscribers.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: queue.Queue) -> None:
    """Remove subscriber queue when an SSE connection closes."""
    with _subscribers_lock:
        if run_id in _subscribers:
            try:
                _subscribers[run_id].remove(q)
            except ValueError:
                pass
            if not _subscribers[run_id]:
                del _subscribers[run_id]


def publish_to_subscribers(run_id: str, record: dict) -> None:
    """Push an event record to all active subscribers for run_id."""
    with _subscribers_lock:
        queues = list(_subscribers.get(run_id, []))
    for q in queues:
        try:
            q.put_nowait(record)
        except Exception:
            pass



def get_logger(run_id: str) -> logging.Logger:
    if run_id in _loggers:
        return _loggers[run_id]

    logger = logging.getLogger(f"pipeline.{run_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(fmt)
        logger.addHandler(console)

        file_handler = logging.FileHandler(
            os.path.join(LOG_DIR, f"{run_id}.log"), encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    _loggers[run_id] = logger
    return logger


def _events_path(run_id: str) -> str:
    return os.path.join(LOG_DIR, f"{run_id}.events.jsonl")


def log_event(run_id: str, agent: str, event_type: str, **payload) -> dict:
    """Append one structured, machine-readable event to this run's trace via the canonical tracer."""
    from tools.tracer import record_event
    clean_record = record_event(run_id=run_id, agent=agent, event_type=event_type, **payload)

    # Mirror a short human-readable line into the normal logger too (trimmed so a
    # big payload like full_history doesn't spam the console/log file).
    from utils.safe import safe_json
    preview = {k: v for k, v in payload.items() if k not in ("full_history", "code")}
    get_logger(run_id).debug(
        "[%s] %s | %s", agent, event_type, json.dumps(safe_json(preview))[:500]
    )
    return clean_record


def read_events(run_id: str) -> list:
    """Read back the full structured event trace for a run.
    Uses tracer's get_run_events with fallback to direct jsonl file reading."""
    try:
        from tools.tracer import get_run_events
        evs = get_run_events(run_id)
        if evs:
            return evs
    except Exception:
        pass

    path = _events_path(run_id)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


@contextlib.contextmanager
def step_timer(run_id: str, agent: str, step_name: str, **extra):
    """Logs a step_start / step_end (or step_error) event pair with duration around
    whatever code runs inside the `with` block."""
    logger = get_logger(run_id)
    start = time.monotonic()
    log_event(run_id, agent, "step_start", step=step_name, **extra)
    logger.info("%s: starting %s", agent, step_name)
    try:
        yield
    except Exception as exc:
        duration = time.monotonic() - start
        log_event(
            run_id, agent, "step_error", step=step_name,
            duration_sec=round(duration, 3), error=str(exc),
        )
        logger.exception("%s: %s failed after %.2fs", agent, step_name, duration)
        raise
    else:
        duration = time.monotonic() - start
        log_event(
            run_id, agent, "step_end", step=step_name,
            duration_sec=round(duration, 3), **extra,
        )
        logger.info("%s: finished %s (%.2fs)", agent, step_name, duration)
