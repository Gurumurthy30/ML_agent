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
        self.escaped = False
        self.prompt_override: Optional[str] = None
        self.retry_node: Optional[str] = None
        self._lock = threading.Lock()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def wait_if_paused(self, timeout: Optional[float] = None) -> bool:
        """Blocks while paused. Returns False if timeout expired or stopped."""
        start_t = time.time()
        while not self._pause_event.is_set():
            if self.stopped:
                return False
            if timeout is not None and (time.time() - start_t) >= timeout:
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

    def escape(self):
        with self._lock:
            self.escaped = True

    def consume_escape(self) -> bool:
        with self._lock:
            if self.escaped:
                self.escaped = False
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


def run_migrations():
    """
    Applies schema migrations idempotently to runs_index.db.
    Maintains a schema_migrations table and executes versioned DDL steps.
    """
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    );
                """)
                cur = conn.execute("SELECT version FROM schema_migrations")
                applied = {row["version"] for row in cur.fetchall()}

                # Migration 1: Base schema (runs and events tables + initial indices)
                if 1 not in applied:
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
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (1, "base_schema", datetime.now(timezone.utc).isoformat())
                    )

                # Migration 2: Add explicit baseline & tags/labels to runs table
                if 2 not in applied:
                    cur = conn.execute("PRAGMA table_info(runs)")
                    existing_cols = {row["name"] for row in cur.fetchall()}
                    if "is_baseline" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN is_baseline INTEGER DEFAULT 0;")
                    if "baseline_run_id" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN baseline_run_id TEXT DEFAULT NULL;")
                    if "tags" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN tags TEXT DEFAULT '[]';")
                    if "labels" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN labels TEXT DEFAULT '{}';")
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (2, "baseline_and_tags_labels", datetime.now(timezone.utc).isoformat())
                    )

                # Migration 3: Composite indices covering (run_id, phase) and (run_id, agent, event_type)
                if 3 not in applied:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_phase ON events(run_id, phase);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_agent_type ON events(run_id, agent, event_type);")
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (3, "phase_and_agent_indices", datetime.now(timezone.utc).isoformat())
                    )

                # Migration 4: Materialized cache table for attempts and errors
                if 4 not in applied:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS run_materialized_cache (
                            run_id TEXT PRIMARY KEY,
                            last_seq INTEGER,
                            attempts_json TEXT,
                            errors_json TEXT,
                            updated_at TEXT
                        );
                    """)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (4, "run_materialized_cache", datetime.now(timezone.utc).isoformat())
                    )

                # Migration 5: Adaptive controller state persistence across worker processes
                if 5 not in applied:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS adaptive_ideas (
                            run_id TEXT NOT NULL,
                            idea_id TEXT NOT NULL,
                            phase TEXT NOT NULL,
                            tier INTEGER NOT NULL,
                            summary TEXT NOT NULL,
                            details_json TEXT,
                            outcome TEXT,
                            ts REAL
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_adaptive_ideas_run_phase ON adaptive_ideas(run_id, phase);")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS adaptive_errors (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            run_id TEXT NOT NULL,
                            sig TEXT NOT NULL,
                            error_type TEXT,
                            ts REAL
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_adaptive_errors_run ON adaptive_errors(run_id);")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS adaptive_runs (
                            run_id TEXT PRIMARY KEY,
                            start_time REAL
                        );
                    """)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (5, "adaptive_controller_persistence", datetime.now(timezone.utc).isoformat())
                    )

                # Migration 6: Add report and report_path columns to runs table
                if 6 not in applied:
                    cur = conn.execute("PRAGMA table_info(runs)")
                    existing_cols = {row["name"] for row in cur.fetchall()}
                    if "report" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN report TEXT DEFAULT NULL;")
                    if "report_path" not in existing_cols:
                        conn.execute("ALTER TABLE runs ADD COLUMN report_path TEXT DEFAULT NULL;")
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (6, "report_storage", datetime.now(timezone.utc).isoformat())
                    )
        finally:
            conn.close()


def init_db():
    run_migrations()


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
# SQLite Payload Truncation (Hot path compact index, full in JSONL)
# ---------------------------------------------------------------------------
SQLITE_PAYLOAD_MAX_STR_LEN = 2048


def _truncate_for_sqlite(val: Any, max_len: int = SQLITE_PAYLOAD_MAX_STR_LEN, key: Optional[str] = None) -> Any:
    """Truncate large text payloads (code, stdout, stderr, prompt) for compact SQLite storage,
    leaving the full content in the JSONL files on disk. Excludes report, feedback, and notes."""
    if key in ("report", "feedback", "judge_feedback", "retry_note", "modify_note", "decision_payload"):
        return val
    if isinstance(val, str):
        if len(val) > max_len:
            return val[:max_len] + f"... [TRUNCATED {len(val) - max_len} chars in SQLite index; full payload in JSONL]"
        return val
    elif isinstance(val, dict):
        return {k: _truncate_for_sqlite(v, max_len=max_len, key=k) for k, v in val.items()}
    elif isinstance(val, list):
        return [_truncate_for_sqlite(v, max_len=max_len, key=key) for v in val]
    return val


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

    # Normalize synonym fields across layers
    if decision is None and "verdict" in extra_payload:
        decision = extra_payload["verdict"]
    if tier is None and "retry_tier" in extra_payload:
        tier = extra_payload["retry_tier"]
    if reason is None and "reasoning" in extra_payload:
        reason = extra_payload["reasoning"]

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
                    sqlite_clean_record = _truncate_for_sqlite(clean_record)
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
                            json.dumps(sqlite_clean_record),
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
    is_baseline: bool = False,
    baseline_score: Optional[float] = None,
    tags: Optional[List[str]] = None,
    labels: Optional[Dict[str, str]] = None,
    meta: Optional[Dict[str, Any]] = None,
):
    """Insert initial record for a run in SQLite."""
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(tags or [])
    labels_json = json.dumps(labels or {})
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs (
                        run_id, created_at, updated_at, status, dataset_path,
                        mode, guided_mode, metric_name, is_baseline, baseline_score,
                        tags, labels, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        1 if is_baseline else 0,
                        baseline_score,
                        tags_json,
                        labels_json,
                        json.dumps(meta or {}),
                    ),
                )
        finally:
            conn.close()


create_run = register_run


def set_run_baseline(run_id: str, is_baseline: bool = True, baseline_score: Optional[float] = None) -> None:
    """Explicitly mark a run as baseline or update its baseline reference."""
    now = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE runs SET
                        is_baseline = ?,
                        baseline_score = COALESCE(?, baseline_score),
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (1 if is_baseline else 0, baseline_score, now, run_id),
                )
        finally:
            conn.close()


def set_run_tags(run_id: str, tags: List[str]) -> None:
    """Set the full list of tags for UI filtering."""
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(list(tags))
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    "UPDATE runs SET tags = ?, updated_at = ? WHERE run_id = ?",
                    (tags_json, now, run_id),
                )
        finally:
            conn.close()


def add_run_tag(run_id: str, tag: str) -> None:
    """Add a single tag to a run if not already present."""
    run = get_run(run_id)
    if not run:
        return
    existing_tags = []
    try:
        existing_tags = json.loads(run.get("tags") or "[]")
    except Exception:
        pass
    if tag not in existing_tags:
        existing_tags.append(tag)
        set_run_tags(run_id, existing_tags)


def set_run_labels(run_id: str, labels: Dict[str, str]) -> None:
    """Set arbitrary key-value labels for run metadata."""
    now = datetime.now(timezone.utc).isoformat()
    labels_json = json.dumps(dict(labels))
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    "UPDATE runs SET labels = ?, updated_at = ? WHERE run_id = ?",
                    (labels_json, now, run_id),
                )
        finally:
            conn.close()


def update_run_status(
    run_id: str,
    status: str,
    stop_reason: Optional[str] = None,
    best_score: Optional[float] = None,
    duration_s: Optional[float] = None,
    report: Optional[str] = None,
    report_path: Optional[str] = None,
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
                        report = COALESCE(?, report),
                        report_path = COALESCE(?, report_path),
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (status, stop_reason, best_score, duration_s, report, report_path, now, run_id),
                )
        finally:
            conn.close()


def list_runs(
    limit: int = 50,
    tag: Optional[str] = None,
    is_baseline: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Retrieve recent runs with high-level metrics for UI sidebar and comparison,
    supporting filtering by tag and/or is_baseline status."""
    with _DB_LOCK:
        conn = _get_db()
        try:
            clauses = []
            params: List[Any] = []
            if is_baseline is not None:
                clauses.append("is_baseline = ?")
                params.append(1 if is_baseline else 0)
            if tag:
                clauses.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT * FROM runs {where_sql} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
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
# Materialized View Cache & Attempt/Error Aggregations
# ---------------------------------------------------------------------------
_ATTEMPTS_CACHE: Dict[str, Tuple[int, List[Dict[str, Any]]]] = {}
_ERRORS_CACHE: Dict[str, Tuple[int, List[Dict[str, Any]]]] = {}
_MATERIALIZED_CACHE_LOCK = threading.Lock()


def _get_current_max_seq(run_id: str) -> int:
    with _RUN_SEQS_LOCK:
        if run_id in _RUN_SEQS:
            return _RUN_SEQS[run_id]
    with _DB_LOCK:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT MAX(seq) FROM events WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            return row[0] if (row and row[0] is not None) else 0
        finally:
            conn.close()


def _persist_materialized_cache(
    run_id: str,
    last_seq: int,
    attempts: Optional[List[Dict[str, Any]]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                cur = conn.execute("SELECT attempts_json, errors_json FROM run_materialized_cache WHERE run_id = ?", (run_id,))
                row = cur.fetchone()
                prev_att = row["attempts_json"] if row else None
                prev_err = row["errors_json"] if row else None

                att_json = json.dumps(safe_json(attempts)) if attempts is not None else prev_att
                err_json = json.dumps(safe_json(errors)) if errors is not None else prev_err

                conn.execute(
                    """
                    INSERT OR REPLACE INTO run_materialized_cache (run_id, last_seq, attempts_json, errors_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, last_seq, att_json, err_json, now),
                )
        except Exception as exc:
            logger.debug("Could not persist materialized cache for %s: %s", run_id, exc)
        finally:
            conn.close()


def _compute_run_attempts(run_id: str) -> List[Dict[str, Any]]:
    events = get_run_events(run_id)
    attempts = []
    baseline = None

    for ev in events:
        parent = ev.get("parent_agent")
        agent = ev.get("agent")
        if parent in ("eda_agent", "features_agent") or agent in ("eda_agent", "features_agent"):
            continue

        evt = ev.get("event") or ev.get("type")
        # Accept attempt_result (modeler success/fail), model_evaluated, candidate_evaluated,
        # and coder events that carry a cv_score.
        is_modeler_attempt = evt in ("attempt_result", "modeler_iteration", "model_evaluated", "candidate_evaluated")
        is_coder_scored = ev.get("agent") == "coder_agent" and "cv_score" in ev

        if is_modeler_attempt or is_coder_scored:
            if ev.get("agent") == "coder_agent" and not ev.get("model_family") and not ev.get("model_name"):
                continue
            # Modeler emits `score` (not `cv_score`) on success; fall back to cv_score/metric_value for other sources
            val = to_float(ev.get("score") or ev.get("cv_score") or ev.get("metric_value"))
            if baseline is None and val is not None:
                baseline = val

            delta = safe_diff(val, baseline) if (val is not None and baseline is not None) else None

            attempts.append({
                "seq": ev.get("seq"),
                "attempt": ev.get("attempt", len(attempts) + 1),
                "tier": ev.get("tier", 1),
                "agent": ev.get("agent"),
                # modeler emits model_family; fall back to model_name/model_type for other agents
                "model_name": ev.get("model_family") or ev.get("model_name") or ev.get("model_type") or "Unknown Model",
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
                # Extended fields for the All Code/Results tab
                "code": ev.get("code"),
                "stdout": ev.get("stdout"),
                "stderr": ev.get("stderr"),
                "iteration": ev.get("iteration"),
                "success": ev.get("success", val is not None),
                "failure_reason": ev.get("failure_reason"),
                "metric_name": ev.get("metric_name") or ev.get("metric"),
                "is_improvement": ev.get("is_improvement"),
            })
    return attempts


def get_run_attempts(run_id: str) -> List[Dict[str, Any]]:
    """
    Extract structured attempt ledger from recorded events.
    Cached in memory and materialized in SQLite.
    """
    curr_seq = _get_current_max_seq(run_id)
    with _MATERIALIZED_CACHE_LOCK:
        if run_id in _ATTEMPTS_CACHE:
            cached_seq, cached_attempts = _ATTEMPTS_CACHE[run_id]
            if cached_seq == curr_seq:
                return [dict(a) for a in cached_attempts]

    with _DB_LOCK:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT last_seq, attempts_json FROM run_materialized_cache WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row and row["last_seq"] == curr_seq and row["attempts_json"]:
                attempts = json.loads(row["attempts_json"])
                with _MATERIALIZED_CACHE_LOCK:
                    _ATTEMPTS_CACHE[run_id] = (curr_seq, attempts)
                return [dict(a) for a in attempts]
        except Exception:
            pass
        finally:
            conn.close()

    attempts = _compute_run_attempts(run_id)
    with _MATERIALIZED_CACHE_LOCK:
        _ATTEMPTS_CACHE[run_id] = (curr_seq, attempts)
    _persist_materialized_cache(run_id, curr_seq, attempts=attempts)
    return attempts


def get_run_iterations(run_id: str, agent: str = "modeler_agent") -> List[Dict[str, Any]]:
    """
    Return all iteration events for a given agent — including failed ones.
    Used by the All Code & Results tab in the frontend, which needs every attempt
    regardless of whether a score was produced.
    """
    events = get_run_events(run_id)
    results = []
    for ev in events:
        ev_agent = ev.get("agent") or ""
        ev_event = ev.get("event") or ev.get("type") or ""
        ev_parent = ev.get("parent_agent") or ""

        # Include direct attempt_result/modeler_iteration events AND coder sub-events
        # parented to the target agent
        is_agent_direct = ev_agent == agent and ev_event in (
            "attempt_result", "modeler_iteration", "features_iteration", "iteration_result", "loop_decision"
        )
        is_coder_child = ev_parent == agent and ev_agent == "coder_agent"

        if is_agent_direct or is_coder_child:
            val = to_float(ev.get("score") or ev.get("cv_score") or ev.get("metric_value"))
            results.append({
                "seq": ev.get("seq"),
                "ts": ev.get("ts"),
                "agent": ev_agent,
                "event_type": ev_event,
                "iteration": ev.get("iteration") or ev.get("parent_iteration"),
                "model_family": ev.get("model_family") or ev.get("model_name"),
                "task_spec": ev.get("task_spec"),
                "score": val,
                "cv_score_str": f"{val:.4f}" if val is not None else "N/A",
                "metric_name": ev.get("metric_name") or ev.get("metric"),
                "is_improvement": ev.get("is_improvement"),
                "success": ev.get("success", val is not None),
                "failure_reason": ev.get("failure_reason") or ev.get("reason"),
                "code": ev.get("code"),
                "stdout": ev.get("stdout"),
                "stderr": ev.get("stderr"),
                "duration_ms": ev.get("duration_ms"),
                "tier": ev.get("tier"),
                "decision": ev.get("decision"),
            })

    # Sort by seq ascending so the thread is in execution order
    results.sort(key=lambda x: x.get("seq") or 0)
    return results





def _compute_run_errors(run_id: str) -> List[Dict[str, Any]]:
    events = get_run_events(run_id)
    groups: Dict[str, Dict[str, Any]] = {}
    last_sig = None

    for ev in events:
        sig = ev.get("error_signature")
        if not sig and (ev.get("error") or ev.get("stderr")):
            err_type = ev.get("error_type") or "ExecutionError"
            msg = ev.get("error") or ev.get("stderr")
            sig = compute_error_signature(err_type, msg)

        if sig:
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


def get_run_errors(run_id: str) -> List[Dict[str, Any]]:
    """
    Aggregate errors for a run grouped by error_signature.
    Cached in memory and materialized in SQLite.
    """
    curr_seq = _get_current_max_seq(run_id)
    with _MATERIALIZED_CACHE_LOCK:
        if run_id in _ERRORS_CACHE:
            cached_seq, cached_errors = _ERRORS_CACHE[run_id]
            if cached_seq == curr_seq:
                return [dict(e) for e in cached_errors]

    with _DB_LOCK:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT last_seq, errors_json FROM run_materialized_cache WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row and row["last_seq"] == curr_seq and row["errors_json"]:
                errors = json.loads(row["errors_json"])
                with _MATERIALIZED_CACHE_LOCK:
                    _ERRORS_CACHE[run_id] = (curr_seq, errors)
                return [dict(e) for e in errors]
        except Exception:
            pass
        finally:
            conn.close()

    errors = _compute_run_errors(run_id)
    with _MATERIALIZED_CACHE_LOCK:
        _ERRORS_CACHE[run_id] = (curr_seq, errors)
    _persist_materialized_cache(run_id, curr_seq, errors=errors)
    return errors


# ---------------------------------------------------------------------------
# Storage Retention and Rotation Policy
# ---------------------------------------------------------------------------
def rotate_and_prune_storage(
    max_runs: int = 50,
    max_age_days: int = 30,
    runs_dir: str = BASE_RUNS_DIR,
    logs_dir: str = LOG_DIR,
    artifacts_dir: str = "artifacts",
) -> Dict[str, Any]:
    """
    Retention and rotation policy for runs, logs, artifacts, and SQLite index entries.
    Keeps at most `max_runs` recent runs and deletes records/files older than `max_age_days`.
    """
    import shutil
    cutoff_ts = time.time() - (max_age_days * 86400)
    pruned_runs = []
    pruned_logs = []
    pruned_artifacts = []

    # 1. Identify run directories in runs_dir
    run_entries = []
    if os.path.exists(runs_dir):
        for entry in os.listdir(runs_dir):
            full_p = os.path.join(runs_dir, entry)
            if os.path.isdir(full_p):
                mtime = os.path.getmtime(full_p)
                run_entries.append((entry, full_p, mtime))

    run_entries.sort(key=lambda x: x[2], reverse=True)

    runs_to_remove = set()
    for idx, (r_id, path, mtime) in enumerate(run_entries):
        if idx >= max_runs or mtime < cutoff_ts:
            runs_to_remove.add(r_id)
            try:
                shutil.rmtree(path, ignore_errors=True)
                pruned_runs.append(r_id)
            except Exception as e:
                logger.warning("Could not delete run dir %s: %s", path, e)

    # 2. Prune log files in logs_dir
    if os.path.exists(logs_dir):
        for fname in os.listdir(logs_dir):
            full_p = os.path.join(logs_dir, fname)
            if os.path.isfile(full_p):
                mtime = os.path.getmtime(full_p)
                matched_run = next((r for r in runs_to_remove if fname.startswith(r)), None)
                if matched_run or mtime < cutoff_ts:
                    try:
                        os.remove(full_p)
                        pruned_logs.append(fname)
                    except Exception as e:
                        logger.warning("Could not delete log file %s: %s", full_p, e)

    # 3. Prune artifacts
    if os.path.exists(artifacts_dir):
        for root, dirs, files in os.walk(artifacts_dir):
            for f in files:
                full_p = os.path.join(root, f)
                mtime = os.path.getmtime(full_p)
                matched_run = next((r for r in runs_to_remove if r in f or r in root), None)
                if matched_run or mtime < cutoff_ts:
                    try:
                        os.remove(full_p)
                        pruned_artifacts.append(os.path.relpath(full_p, artifacts_dir))
                    except Exception as e:
                        logger.warning("Could not delete artifact %s: %s", full_p, e)

    # 4. Prune SQLite tables
    if runs_to_remove:
        with _DB_LOCK:
            conn = _get_db()
            try:
                with conn:
                    placeholders = ",".join(["?"] * len(runs_to_remove))
                    r_list = list(runs_to_remove)
                    conn.execute(f"DELETE FROM events WHERE run_id IN ({placeholders})", r_list)
                    conn.execute(f"DELETE FROM runs WHERE run_id IN ({placeholders})", r_list)
                    conn.execute(f"DELETE FROM run_materialized_cache WHERE run_id IN ({placeholders})", r_list)
                    conn.execute(f"DELETE FROM adaptive_ideas WHERE run_id IN ({placeholders})", r_list)
                    conn.execute(f"DELETE FROM adaptive_errors WHERE run_id IN ({placeholders})", r_list)
                    conn.execute(f"DELETE FROM adaptive_runs WHERE run_id IN ({placeholders})", r_list)
            except Exception as exc:
                logger.warning("Error pruning SQLite records for removed runs: %s", exc)
            finally:
                conn.close()

    with _MATERIALIZED_CACHE_LOCK:
        for r_id in runs_to_remove:
            _ATTEMPTS_CACHE.pop(r_id, None)
            _ERRORS_CACHE.pop(r_id, None)

    return {
        "pruned_run_ids": pruned_runs,
        "pruned_log_files": pruned_logs,
        "pruned_artifact_files": pruned_artifacts,
    }


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


# ---------------------------------------------------------------------------
# Adaptive Controller Persistence Helpers
# ---------------------------------------------------------------------------
def record_adaptive_idea(
    run_id: str,
    phase: str,
    tier: int,
    idea_summary: str,
    details: Optional[Dict[str, Any]] = None,
    outcome: str = "evaluated",
) -> Dict[str, Any]:
    norm_idea = idea_summary.strip().lower()
    idea_hash = hashlib.sha256(f"{phase}:{tier}:{norm_idea}".encode("utf-8")).hexdigest()[:12]
    now_ts = time.time()
    details_str = json.dumps(safe_json(details or {}))

    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                cur = conn.execute("SELECT 1 FROM adaptive_ideas WHERE run_id = ? AND idea_id = ?", (run_id, idea_hash))
                if cur.fetchone():
                    conn.execute(
                        """
                        UPDATE adaptive_ideas SET phase = ?, tier = ?, summary = ?, details_json = ?, outcome = ?, ts = ?
                        WHERE run_id = ? AND idea_id = ?
                        """,
                        (phase, tier, idea_summary, details_str, outcome, now_ts, run_id, idea_hash),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO adaptive_ideas (run_id, idea_id, phase, tier, summary, details_json, outcome, ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (run_id, idea_hash, phase, tier, idea_summary, details_str, outcome, now_ts),
                    )
        finally:
            conn.close()

    return {
        "idea_id": idea_hash,
        "phase": phase,
        "tier": tier,
        "summary": idea_summary,
        "details": details or {},
        "outcome": outcome,
        "timestamp": now_ts,
    }


def clear_adaptive_run(run_id: str) -> None:
    """Clear all adaptive controller records for a given run (useful for cleanup and test resets)."""
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute("DELETE FROM adaptive_ideas WHERE run_id = ?", (run_id,))
                conn.execute("DELETE FROM adaptive_errors WHERE run_id = ?", (run_id,))
                conn.execute("DELETE FROM adaptive_runs WHERE run_id = ?", (run_id,))
        finally:
            conn.close()


def get_adaptive_ideas(run_id: str, phase: Optional[str] = None) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_db()
        try:
            if phase:
                cur = conn.execute(
                    "SELECT idea_id, phase, tier, summary, details_json, outcome, ts FROM adaptive_ideas WHERE run_id = ? AND phase = ? ORDER BY ts ASC",
                    (run_id, phase),
                )
            else:
                cur = conn.execute(
                    "SELECT idea_id, phase, tier, summary, details_json, outcome, ts FROM adaptive_ideas WHERE run_id = ? ORDER BY ts ASC",
                    (run_id,),
                )
            rows = cur.fetchall()
            results = []
            for r in rows:
                try:
                    det = json.loads(r["details_json"]) if r["details_json"] else {}
                except Exception:
                    det = {}
                results.append({
                    "idea_id": r["idea_id"],
                    "phase": r["phase"],
                    "tier": r["tier"],
                    "summary": r["summary"],
                    "details": det,
                    "outcome": r["outcome"],
                    "timestamp": r["ts"],
                })
            return results
        finally:
            conn.close()


def record_adaptive_error(run_id: str, sig: str, error_type: str = "ExecutionError") -> None:
    now_ts = time.time()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO adaptive_errors (run_id, sig, error_type, ts) VALUES (?, ?, ?, ?)",
                    (run_id, sig, error_type, now_ts),
                )
        finally:
            conn.close()


def get_adaptive_error_signatures(run_id: str) -> List[str]:
    with _DB_LOCK:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT sig FROM adaptive_errors WHERE run_id = ? ORDER BY id ASC", (run_id,))
            return [row["sig"] for row in cur.fetchall()]
        finally:
            conn.close()


def set_adaptive_run_start(run_id: str, start_time: Optional[float] = None) -> None:
    st = start_time if start_time is not None else time.time()
    with _DB_LOCK:
        conn = _get_db()
        try:
            with conn:
                conn.execute("INSERT OR REPLACE INTO adaptive_runs (run_id, start_time) VALUES (?, ?)", (run_id, st))
        finally:
            conn.close()


def get_adaptive_run_start(run_id: str) -> Optional[float]:
    with _DB_LOCK:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT start_time FROM adaptive_runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            return row["start_time"] if row else None
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# CLI Administration Interface
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tracer administration & storage maintenance CLI")
    parser.add_argument("--prune", action="store_true", help="Execute retention policy: rotate and prune storage")
    parser.add_argument("--max-runs", type=int, default=50, help="Maximum number of runs to retain (default: 50)")
    parser.add_argument("--max-age-days", type=int, default=30, help="Maximum age of runs in days (default: 30)")
    args = parser.parse_args()

    if args.prune:
        result = rotate_and_prune_storage(max_runs=args.max_runs, max_age_days=args.max_age_days)
        print(f"Prune completed successfully:")
        print(f"  Pruned run directories: {len(result['pruned_run_ids'])}")
        print(f"  Pruned log files:       {len(result['pruned_log_files'])}")
        print(f"  Pruned artifacts:       {len(result['pruned_artifact_files'])}")
    else:
        parser.print_help()

