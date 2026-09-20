"""
Unified Tracer, Dual-Persistence & Run Control Engine for ML_agent.

Provides:
  - Versioned event schema conforming to telemetry requirements
  - Dual persistence:
      1. Append-only JSONL event stream in `runs/<run_id>/events.jsonl` (and mirrored to `logs/<run_id>.events.jsonl`)
      2. Thread-safe SQLite index at `runs/runs_index.db` for fast queries, aggregation, and run comparison
  - Error signature computation and retry loop detection
  - State snapshotting & state diff generation
  - Run control primitives: Pause, Resume, Stop, Escalate, Prompt injection
  - ZIP debug bundle exporter and run comparison engine
"""
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from utils.safe import safe_json, to_float, safe_diff, safe_round

logger = logging.getLogger("tools.tracer")

BASE_RUNS_DIR = os.environ.get("PIPELINE_RUNS_DIR", "runs")
LOG_DIR = os.environ.get("PIPELINE_LOG_DIR", "logs")
DB_PATH = os.path.join(BASE_RUNS_DIR, "runs_index.db")

os.makedirs(BASE_RUNS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Run Controls (Pause, Resume, Stop, Escalate, Retry injection)
# ---------------------------------------------------------------------------
class RunControl:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._pause_event = threading.Event()
        self._pause_event.set()  # set = running, clear = paused
        self.stopped = False
        self.force_escalate = False
        self.prompt_override: Optional[str] = None
        self.retry_node: Optional[str] = None

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def wait_if_paused(self, timeout: Optional[float] = None) -> bool:
        """Blocks while paused. Returns False if timeout expired or stopped."""
        while not self._pause_event.is_set():
            if self.stopped:
                return False
            time.sleep(0.2)
        return True

    def stop(self):
        self.stopped = True
        self._pause_event.set()  # Unblock any waiting thread

    def escalate(self):
        self.force_escalate = True

    def consume_escalate(self) -> bool:
        if self.force_escalate:
            self.force_escalate = False
            return True
        return False

    def set_prompt_override(self, prompt: str, node: Optional[str] = None):
        self.prompt_override = prompt
        self.retry_node = node

    def consume_prompt_override(self) -> Optional[str]:
        p = self.prompt_override
        self.prompt_override = None
        return p


_CONTROLS_LOCK = threading.Lock()
_RUN_CONTROLS: Dict[str, RunControl] = {}


def get_run_control(run_id: str) -> RunControl:
    with _CONTROLS_LOCK:
        if run_id not in _RUN_CONTROLS:
            _RUN_CONTROLS[run_id] = RunControl(run_id)
        return _RUN_CONTROLS[run_id]


# ---------------------------------------------------------------------------
# SQLite Index Initialization & Helpers
# ---------------------------------------------------------------------------
_DB_LOCK = threading.Lock()


def _get_db() -> sqlite3.Connection:
    """Open thread-safe connection to SQLite index with WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        created_at TEXT,
                        updated_at TEXT,
                        status TEXT,
                        stop_reason TEXT,
                        dataset_path TEXT,
                        mode TEXT,
                        guided_mode INTEGER,
                        best_score REAL,
                        baseline_score REAL,
                        metric_name TEXT,
                        total_attempts INTEGER DEFAULT 0,
                        total_tokens_in INTEGER DEFAULT 0,
                        total_tokens_out INTEGER DEFAULT 0,
                        total_cost_usd REAL DEFAULT 0.0,
                        duration_s REAL DEFAULT 0.0,
                        error_count INTEGER DEFAULT 0,
                        meta_json TEXT
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        run_id TEXT,
                        seq INTEGER,
                        ts TEXT,
                        agent TEXT,
                        event_type TEXT,
                        phase TEXT,
                        tier INTEGER,
                        attempt INTEGER,
                        intent TEXT,
                        decision TEXT,
                        metric_value REAL,
                        metric_delta REAL,
                        duration_ms INTEGER,
                        tokens_in INTEGER,
                        tokens_out INTEGER,
                        cost_usd REAL,
                        error_signature TEXT,
                        payload_json TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_err_sig ON events(error_signature);")
        finally:
            conn.close()


init_db()

# ---------------------------------------------------------------------------
# Error Signature Computation
# ---------------------------------------------------------------------------
_HEX_PATTERN = re.compile(r"0x[0-9a-fA-F]+")
_DIGIT_PATTERN = re.compile(r"\b\d+\b")
_PATH_PATTERN = re.compile(r"/[^ \n\t\r]+|\\[^ \n\t\r]+")
_QUOTED_PATTERN = re.compile(r"['\"][^'\"]*['\"]")


def compute_error_signature(error_type: str, message: str) -> str:
    """
    Generate a normalized, deterministic hash for an error.
    Strips memory addresses, file paths, line numbers, quoted strings, and timestamps
    so identical conceptual errors have the same signature for loop detection.
    """
    if not message:
        return f"{error_type}_empty"
    # Normalize message
    norm = _HEX_PATTERN.sub("<HEX>", str(message))
    norm = _PATH_PATTERN.sub("<PATH>", norm)
    norm = _DIGIT_PATTERN.sub("<NUM>", norm)
    norm = _QUOTED_PATTERN.sub("<STR>", norm)
    norm = norm.strip().lower()
    norm_hash = hashlib.sha256(f"{error_type}:{norm}".encode("utf-8")).hexdigest()[:10]
    return f"{error_type}:{norm_hash}"


# ---------------------------------------------------------------------------
# Run Sequence Numbers & State Tracking
# ---------------------------------------------------------------------------
_RUN_SEQS: Dict[str, int] = {}
_RUN_SEQS_LOCK = threading.Lock()


def _get_next_seq(run_id: str) -> int:
    with _RUN_SEQS_LOCK:
        curr = _RUN_SEQS.get(run_id, 0) + 1
        _RUN_SEQS[run_id] = curr
        return curr


def _run_dir(run_id: str) -> str:
    path = os.path.join(BASE_RUNS_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    return path


def _run_events_path(run_id: str) -> str:
    return os.path.join(_run_dir(run_id), "events.jsonl")


def _legacy_events_path(run_id: str) -> str:
    return os.path.join(LOG_DIR, f"{run_id}.events.jsonl")


# ---------------------------------------------------------------------------
# Event Recording & Ingestion
# ---------------------------------------------------------------------------
def record_event(
    run_id: str,
    agent: str,
    event_type: str,
    phase: Optional[str] = None,
    tier: Optional[int] = None,
    attempt: Optional[int] = None,
    intent: Optional[str] = None,
    prompt: Optional[str] = None,
    raw_response: Optional[str] = None,
    parsed_decision: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
    code_diff: Optional[str] = None,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    metric_value: Optional[float] = None,
    metric_delta: Optional[float] = None,
    decision: Optional[str] = None,
    reason: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cost_usd: Optional[float] = None,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
    error_trace: Optional[str] = None,
    state_snapshot: Optional[Dict[str, Any]] = None,
    state_replace: Optional[bool] = None,
    **extra_payload,
) -> Dict[str, Any]:
    """
    Standard entry point for recording an observability event.
    Guarantees strict schema, dual persistence (JSONL + SQLite),
    error signature generation, and live SSE publishing.
    """
    seq = _get_next_seq(run_id)
    event_id = f"{run_id}_{seq:05d}"
    ts = datetime.now(timezone.utc).isoformat()

    # Determine phase if not provided
    if not phase:
        if "profiler" in agent:
            phase = "profiler"
        elif "features" in agent:
            phase = "features"
        elif "modeler" in agent:
            phase = "modeler"
        elif "judge" in agent:
            phase = "judge"
        elif "supervisor" in agent:
            phase = "supervisor"
        elif "reporter" in agent:
            phase = "reporter"
        else:
            phase = agent

    # Clean numbers
    c_metric_val = to_float(metric_value, default=None)
    c_metric_delta = to_float(metric_delta, default=None)

    # Error signature computation
    err_sig = None
    if error or stderr:
        err_msg = error or (stderr if "Traceback" in (stderr or "") else None)
        if err_msg:
            err_type = extra_payload.get("error_type") or "RuntimeError"
            err_sig = compute_error_signature(err_type, err_msg)

    # Cost estimation (e.g., $0.001 / 1k tokens default estimate if not given)
    tin = tokens_in or extra_payload.get("prompt_tokens") or 0
    tout = tokens_out or extra_payload.get("completion_tokens") or 0
    if cost_usd is None and (tin or tout):
        cost_usd = round((tin * 0.0005 + tout * 0.0015) / 1000.0, 6)

    event_record = {
        "event_id": event_id,
        "run_id": run_id,
        "seq": seq,
        "ts": ts,
        "agent": agent,
        "event": event_type,
        "type": event_type,
        "phase": phase,
        "tier": tier,
        "attempt": attempt,
        "intent": intent,
        "prompt": prompt,
        "raw_response": raw_response,
        "parsed_decision": parsed_decision,
        "code": code,
        "code_diff": code_diff,
        "stdout": stdout,
        "stderr": stderr,
        "metric_value": c_metric_val,
        "metric_delta": c_metric_delta,
        "decision": decision,
        "reason": reason,
        "tokens_in": tin,
        "tokens_out": tout,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
        "error": error,
        "error_trace": error_trace,
        "error_signature": err_sig,
        "state_snapshot": state_snapshot,
        "state_replace": state_replace,
        **extra_payload,
    }

    clean_record = safe_json(event_record)
    serialized_line = json.dumps(clean_record) + "\n"

    # 1. Dual persistence: JSONL
    try:
        with open(_run_events_path(run_id), "a", encoding="utf-8") as f:
            f.write(serialized_line)
    except Exception as exc:
        logger.error("Failed writing run JSONL for %s: %s", run_id, exc)

    try:
        with open(_legacy_events_path(run_id), "a", encoding="utf-8") as f:
            f.write(serialized_line)
    except Exception as exc:
        logger.error("Failed writing legacy log JSONL for %s: %s", run_id, exc)

    # 2. Dual persistence: SQLite Indexing
    try:
        with _DB_LOCK:
            conn = _get_db()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO events (
                            event_id, run_id, seq, ts, agent, event_type, phase,
                            tier, attempt, intent, decision, metric_value,
                            metric_delta, duration_ms, tokens_in, tokens_out,
                            cost_usd, error_signature, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            run_id,
                            seq,
                            ts,
                            agent,
                            event_type,
                            phase,
                            tier,
                            attempt,
                            intent,
                            decision,
                            c_metric_val,
                            c_metric_delta,
                            duration_ms,
                            tin,
                            tout,
                            cost_usd,
                            err_sig,
                            json.dumps(clean_record),
                        ),
                    )

                    # Update run summary in SQLite
                    updates = ["updated_at = ?"]
                    params: List[Any] = [ts]

                    if c_metric_val is not None:
                        updates.append("best_score = MAX(COALESCE(best_score, -999999.0), ?)")
                        params.append(c_metric_val)
                    if attempt is not None:
                        updates.append("total_attempts = MAX(total_attempts, ?)")
                        params.append(attempt)
                    if tin > 0 or tout > 0:
                        updates.append("total_tokens_in = total_tokens_in + ?")
                        params.append(tin)
                        updates.append("total_tokens_out = total_tokens_out + ?")
                        params.append(tout)
                    if cost_usd:
                        updates.append("total_cost_usd = total_cost_usd + ?")
                        params.append(cost_usd)
                    if err_sig:
                        updates.append("error_count = error_count + 1")

                    params.append(run_id)
                    update_sql = f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?"
                    conn.execute(update_sql, params)
            finally:
                conn.close()
    except Exception as exc:
        logger.error("Failed indexing event to SQLite for %s: %s", run_id, exc)

    # 3. State JSON snapshot on disk if provided
    if state_snapshot:
        try:
            state_file = os.path.join(_run_dir(run_id), "state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(safe_json(state_snapshot), f, indent=2)
        except Exception:
            pass

    # 4. Save best model code if present
    if code and (decision == "accepted" or event_type == "best_model_saved"):
        try:
            code_file = os.path.join(_run_dir(run_id), "best_model_code.py")
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception:
            pass

    # 5. Broadcast to SSE subscribers via tools.logger
    try:
        from tools.logger import publish_to_subscribers
        publish_to_subscribers(run_id, clean_record)
    except Exception:
        pass

    return clean_record


# ---------------------------------------------------------------------------
# Run Registry Management in SQLite
# ---------------------------------------------------------------------------
def register_run(
    run_id: str,
    dataset_path: str,
    mode: str = "full_pipeline",
    guided_mode: bool = False,
    metric_name: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
):
    """Insert initial record for a run in SQLite."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs (
                        run_id, created_at, updated_at, status, dataset_path,
                        mode, guided_mode, metric_name, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        now,
                        now,
                        "running",
                        dataset_path,
                        mode,
                        1 if guided_mode else 0,
                        metric_name,
                        json.dumps(meta or {}),
                    ),
                )
        finally:
            conn.close()


def update_run_status(
    run_id: str,
    status: str,
    stop_reason: Optional[str] = None,
    best_score: Optional[float] = None,
    duration_s: Optional[float] = None,
):
    """Update lifecycle status and termination reason of a run."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE runs SET
                        status = ?,
                        stop_reason = COALESCE(?, stop_reason),
                        best_score = COALESCE(?, best_score),
                        duration_s = COALESCE(?, duration_s),
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (status, stop_reason, best_score, duration_s, now, run_id),
                )
        finally:
            conn.close()


def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent runs with high-level metrics for UI sidebar and comparison."""
    with _DB_LOCK:
        conn = _get_db()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM runs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full run metadata from SQLite."""
    with _DB_LOCK:
        conn = _get_db()
        try:
            cursor = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_run_events(run_id: str, since_seq: int = 0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieve structured events for a run.
    Supports `since_seq` for SSE catchup or polling replay.
    """
    with _DB_LOCK:
        conn = _get_db()
        try:
            sql = "SELECT payload_json FROM events WHERE run_id = ? AND seq > ? ORDER BY seq ASC"
            params: List[Any] = [run_id, since_seq]
            if limit:
                sql += " LIMIT ?"
                params.append(limit)
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                try:
                    results.append(json.loads(r["payload_json"]))
                except Exception:
                    pass
            return results
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Attempt Ledger & Metric Progression
# ---------------------------------------------------------------------------
def get_run_attempts(run_id: str) -> List[Dict[str, Any]]:
    """
    Extract structured attempt ledger from recorded events:
    model type, tier, CV score, delta, decision, duration, reason.
    """
    events = get_run_events(run_id)
    attempts = []
    baseline = None

    for ev in events:
        parent = ev.get("parent_agent")
        agent = ev.get("agent")
        if parent in ("eda_agent", "features_agent") or agent in ("eda_agent", "features_agent"):
            continue

        evt = ev.get("event") or ev.get("type")
        if evt in ("attempt_result", "model_evaluated", "candidate_evaluated") or (
            ev.get("agent") == "coder_agent" and "cv_score" in ev
        ):
            if ev.get("agent") == "coder_agent" and "cv_score" not in ev and not ev.get("model_family") and not ev.get("model_name"):
                continue
            val = to_float(ev.get("cv_score") or ev.get("metric_value"))
            if baseline is None and val is not None:
                baseline = val

            delta = safe_diff(val, baseline) if (val is not None and baseline is not None) else None

            attempts.append({
                "seq": ev.get("seq"),
                "attempt": ev.get("attempt", len(attempts) + 1),
                "tier": ev.get("tier", 1),
                "agent": ev.get("agent"),
                "model_name": ev.get("model_name") or ev.get("model_type") or "Unknown Model",
                "cv_score": val,
                "cv_score_str": f"{val:.4f}" if val is not None else "N/A",
                "delta": delta,
                "delta_str": f"{delta:+.4f}" if delta is not None else "—",
                "decision": ev.get("decision", "progress"),
                "reason": ev.get("reason") or ev.get("intent") or "Executed pipeline attempt",
                "duration_ms": ev.get("duration_ms", 0),
                "has_code": bool(ev.get("code")),
                "has_diff": bool(ev.get("code_diff")),
                "has_error": bool(ev.get("error") or ev.get("stderr")),
                "error_signature": ev.get("error_signature"),
                "ts": ev.get("ts"),
            })
    return attempts


# ---------------------------------------------------------------------------
# Error Center Aggregations
# ---------------------------------------------------------------------------
def get_run_errors(run_id: str) -> List[Dict[str, Any]]:
    """
    Aggregate errors for a run grouped by error_signature.
    Includes frequency count, first/last seen, tracebacks, and loop detection.
    """
    events = get_run_events(run_id)
    groups: Dict[str, Dict[str, Any]] = {}
    last_sig = None
    retry_loop_detected = False

    for ev in events:
        sig = ev.get("error_signature")
        if not sig and (ev.get("error") or ev.get("stderr")):
            err_type = ev.get("error_type") or "ExecutionError"
            msg = ev.get("error") or ev.get("stderr")
            sig = compute_error_signature(err_type, msg)

        if sig:
            if sig == last_sig:
                retry_loop_detected = True

            if sig not in groups:
                groups[sig] = {
                    "error_signature": sig,
                    "count": 0,
                    "agent": ev.get("agent"),
                    "first_seen": ev.get("ts"),
                    "last_seen": ev.get("ts"),
                    "message": ev.get("error") or (ev.get("stderr", "")[:300]),
                    "traceback": ev.get("error_trace") or ev.get("stderr"),
                    "consecutive_repeat": False,
                }
            groups[sig]["count"] += 1
            groups[sig]["last_seen"] = ev.get("ts")
            if sig == last_sig:
                groups[sig]["consecutive_repeat"] = True
            last_sig = sig
        else:
            last_sig = None

    result = list(groups.values())
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Run Comparison Engine
# ---------------------------------------------------------------------------
def compare_runs(run_id_a: str, run_id_b: str) -> Dict[str, Any]:
    """Compare two runs side-by-side."""
    ra = get_run(run_id_a) or {}
    rb = get_run(run_id_b) or {}

    attempts_a = get_run_attempts(run_id_a)
    attempts_b = get_run_attempts(run_id_b)

    # Read best model code
    code_a = ""
    code_b = ""
    file_a = os.path.join(_run_dir(run_id_a), "best_model_code.py")
    file_b = os.path.join(_run_dir(run_id_b), "best_model_code.py")
    if os.path.exists(file_a):
        with open(file_a, "r", encoding="utf-8") as f:
            code_a = f.read()
    if os.path.exists(file_b):
        with open(file_b, "r", encoding="utf-8") as f:
            code_b = f.read()

    return {
        "run_a": {
            "run_id": run_id_a,
            "status": ra.get("status"),
            "dataset_path": ra.get("dataset_path"),
            "mode": ra.get("mode"),
            "best_score": ra.get("best_score"),
            "total_attempts": len(attempts_a),
            "tokens_in": ra.get("total_tokens_in", 0),
            "tokens_out": ra.get("total_tokens_out", 0),
            "cost_usd": ra.get("total_cost_usd", 0.0),
            "duration_s": ra.get("duration_s", 0.0),
            "has_code": bool(code_a),
            "code": code_a,
        },
        "run_b": {
            "run_id": run_id_b,
            "status": rb.get("status"),
            "dataset_path": rb.get("dataset_path"),
            "mode": rb.get("mode"),
            "best_score": rb.get("best_score"),
            "total_attempts": len(attempts_b),
            "tokens_in": rb.get("total_tokens_in", 0),
            "tokens_out": rb.get("total_tokens_out", 0),
            "cost_usd": rb.get("total_cost_usd", 0.0),
            "duration_s": rb.get("duration_s", 0.0),
            "has_code": bool(code_b),
            "code": code_b,
        },
        "delta_best_score": safe_diff(rb.get("best_score"), ra.get("best_score")),
        "delta_duration_s": (rb.get("duration_s") or 0) - (ra.get("duration_s") or 0),
    }


# ---------------------------------------------------------------------------
# Run Debug Bundle Export (ZIP)
# ---------------------------------------------------------------------------
def export_run_bundle(run_id: str, zip_path: Optional[str] = None) -> str:
    """
    Package run artifacts into a single zip file for export:
    state.json, events.jsonl, best_model_code.py, metrics.csv, error_log.json, report.md.
    """
    rdir = _run_dir(run_id)
    if not zip_path:
        zip_path = os.path.join(rdir, f"{run_id}_debug_bundle.zip")

    # Generate metrics.csv on the fly
    attempts = get_run_attempts(run_id)
    metrics_csv_path = os.path.join(rdir, "metrics.csv")
    try:
        with open(metrics_csv_path, "w", encoding="utf-8") as f:
            f.write("attempt,tier,model_name,cv_score,delta,decision,duration_ms,ts\n")
            for a in attempts:
                f.write(f"{a['attempt']},{a['tier']},{a['model_name']},{a['cv_score'] or ''},{a['delta'] or ''},{a['decision']},{a['duration_ms']},{a['ts']}\n")
    except Exception:
        pass

    # Generate error_log.json on the fly
    errors = get_run_errors(run_id)
    error_log_path = os.path.join(rdir, "error_log.json")
    try:
        with open(error_log_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2)
    except Exception:
        pass

    # Check report path
    report_path = os.path.join("artifacts", "reports", f"{run_id}_report.md")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # events.jsonl
        evt_path = _run_events_path(run_id)
        if os.path.exists(evt_path):
            zf.write(evt_path, arcname="events.jsonl")

        # state.json
        state_path = os.path.join(rdir, "state.json")
        if os.path.exists(state_path):
            zf.write(state_path, arcname="state.json")

        # best_model_code.py
        code_path = os.path.join(rdir, "best_model_code.py")
        if os.path.exists(code_path):
            zf.write(code_path, arcname="best_model_code.py")

        # metrics.csv
        if os.path.exists(metrics_csv_path):
            zf.write(metrics_csv_path, arcname="metrics.csv")

        # error_log.json
        if os.path.exists(error_log_path):
            zf.write(error_log_path, arcname="error_log.json")

        # report.md
        if os.path.exists(report_path):
            zf.write(report_path, arcname="report.md")

    return zip_path
