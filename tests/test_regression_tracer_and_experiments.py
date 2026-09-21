"""
Regression tests for:
- Trace logger canonical writing (collapse dual-write)
- SQLite hot path payload truncation (full in JSONL, truncated in SQLite)
- Storage retention & rotation policy (rotate_and_prune_storage)
- Schema migrations for runs_index.db (schema_migrations, versioned DDL, ALTER TABLE)
- Composite indices on events (run_id, phase) and (run_id, agent, event_type)
- Explicit baseline + tags/labels on runs and list_runs filtering
- Materialized/cached get_run_attempts and get_run_errors
"""
import os
import json
import sqlite3
import pytest
from tools.tracer import (
    _get_db,
    record_event,
    register_run,
    get_run,
    list_runs,
    set_run_baseline,
    set_run_tags,
    add_run_tag,
    set_run_labels,
    get_run_attempts,
    get_run_errors,
    get_run_events,
    rotate_and_prune_storage,
    run_migrations,
    _run_events_path,
    DB_PATH,
    BASE_RUNS_DIR,
)
from tools.logger import log_event, read_events


def test_schema_migrations_applied():
    """Verify versioned migrations run idempotently and apply all required columns and indices."""
    run_migrations()
    conn = _get_db()
    try:
        # 1. Verify schema_migrations table
        cur = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC")
        rows = cur.fetchall()
        versions = [r["version"] for r in rows]
        assert 1 in versions
        assert 2 in versions
        assert 3 in versions
        assert 4 in versions

        # 2. Verify runs table columns
        cur = conn.execute("PRAGMA table_info(runs)")
        cols = {r["name"] for r in cur.fetchall()}
        assert "is_baseline" in cols
        assert "baseline_run_id" in cols
        assert "tags" in cols
        assert "labels" in cols

        # 3. Verify composite indices
        cur = conn.execute("PRAGMA index_list(events)")
        idx_names = {r["name"] for r in cur.fetchall()}
        assert "idx_events_run_phase" in idx_names
        assert "idx_events_run_agent_type" in idx_names

        # 4. Verify run_materialized_cache table
        cur = conn.execute("PRAGMA table_info(run_materialized_cache)")
        mat_cols = {r["name"] for r in cur.fetchall()}
        assert "run_id" in mat_cols
        assert "last_seq" in mat_cols
        assert "attempts_json" in mat_cols
    finally:
        conn.close()


def test_sqlite_payload_truncation_full_in_jsonl():
    """Verify hot SQLite payload is truncated while JSONL retains full byte-for-byte fidelity."""
    import uuid
    run_id = f"test_run_trunc_{uuid.uuid4().hex[:8]}"
    long_code = "# " + ("A" * 3500)
    long_stdout = "OUTPUT: " + ("B" * 3500)

    record_event(
        run_id=run_id,
        agent="coder_agent",
        event_type="code_execution",
        code=long_code,
        stdout=long_stdout,
    )

    # 1. Check SQLite payload_json -> truncated
    conn = _get_db()
    try:
        cur = conn.execute("SELECT payload_json FROM events WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        assert row is not None
        payload = json.loads(row["payload_json"])
        assert len(payload["code"]) < len(long_code)
        assert "[TRUNCATED" in payload["code"]
        assert len(payload["stdout"]) < len(long_stdout)
        assert "[TRUNCATED" in payload["stdout"]
    finally:
        conn.close()

    # 2. Check JSONL on disk -> 100% full content
    jsonl_path = _run_events_path(run_id)
    assert os.path.exists(jsonl_path)
    with open(jsonl_path, "r", encoding="utf-8") as f:
        line = f.readline()
        record_from_file = json.loads(line)
        assert record_from_file["code"] == long_code
        assert record_from_file["stdout"] == long_stdout


def test_canonical_logger_writer():
    """Verify tools.logger.log_event writes directly through canonical tracer and read_events reads back."""
    import uuid
    run_id = f"test_canonical_{uuid.uuid4().hex[:8]}"
    rec = log_event(run_id, "eda_agent", "step_end", step="distribution_check", result_count=42)
    assert rec["run_id"] == run_id
    assert rec["agent"] == "eda_agent"

    events = read_events(run_id)
    assert len(events) >= 1
    found = [e for e in events if e.get("step") == "distribution_check"]
    assert len(found) == 1
    assert found[0]["result_count"] == 42


def test_baseline_and_tags_filtering():
    """Verify explicit baseline and tags/labels metadata and list_runs query filtering."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    run_base = f"test_run_base_{uid}"
    run_candidate = f"test_run_cand_{uid}"

    register_run(run_base, "data.csv", is_baseline=True, baseline_score=0.90, tags=["benchmark", "cv_v1"])
    register_run(run_candidate, "data.csv", is_baseline=False, tags=["experiment", "cv_v1"])

    set_run_labels(run_base, {"model": "xgboost", "environment": "prod"})
    add_run_tag(run_candidate, "lightgbm")

    # Verify get_run
    base_meta = get_run(run_base)
    assert base_meta["is_baseline"] == 1
    assert base_meta["baseline_score"] == 0.90
    assert "benchmark" in base_meta["tags"]
    labels = json.loads(base_meta["labels"])
    assert labels["model"] == "xgboost"

    cand_meta = get_run(run_candidate)
    assert cand_meta["is_baseline"] == 0
    assert "lightgbm" in cand_meta["tags"]

    # Filter by is_baseline
    baselines = list_runs(limit=10, is_baseline=True)
    baseline_ids = [r["run_id"] for r in baselines]
    assert run_base in baseline_ids
    assert run_candidate not in baseline_ids

    # Filter by tag
    benchmarks = list_runs(limit=10, tag="benchmark")
    benchmark_ids = [r["run_id"] for r in benchmarks]
    assert run_base in benchmark_ids
    assert run_candidate not in benchmark_ids

    cv_v1_runs = list_runs(limit=10, tag="cv_v1")
    cv_v1_ids = [r["run_id"] for r in cv_v1_runs]
    assert run_base in cv_v1_ids
    assert run_candidate in cv_v1_ids


def test_materialized_attempts_and_errors_caching():
    """Verify get_run_attempts and get_run_errors cache in memory and materialize in SQLite."""
    import uuid
    run_id = f"test_run_mat_{uuid.uuid4().hex[:8]}"

    record_event(
        run_id=run_id,
        agent="modeler_agent",
        event_type="attempt_result",
        model_name="RandomForestClassifier",
        cv_score=0.82,
        duration_ms=450,
    )
    record_event(
        run_id=run_id,
        agent="coder_agent",
        event_type="step_error",
        error="ValueError: invalid column target",
        parent_agent="modeler_agent",
    )

    # 1. First call computes and materializes
    attempts_1 = get_run_attempts(run_id)
    errors_1 = get_run_errors(run_id)
    assert len(attempts_1) == 1
    assert attempts_1[0]["model_name"] == "RandomForestClassifier"
    assert len(errors_1) == 1

    # Check that SQLite table run_materialized_cache has the row
    conn = _get_db()
    try:
        cur = conn.execute("SELECT last_seq, attempts_json, errors_json FROM run_materialized_cache WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["last_seq"] == 2
        assert "RandomForestClassifier" in row["attempts_json"]
        assert "ValueError" in row["errors_json"]
    finally:
        conn.close()

    # 2. Second call returns from cache
    attempts_2 = get_run_attempts(run_id)
    assert attempts_2 == attempts_1

    # 3. Add a new event -> updates seq and invalidates cache
    record_event(
        run_id=run_id,
        agent="modeler_agent",
        event_type="attempt_result",
        model_name="GradientBoostingClassifier",
        cv_score=0.87,
        duration_ms=600,
    )
    attempts_3 = get_run_attempts(run_id)
    assert len(attempts_3) == 2
    assert attempts_3[1]["model_name"] == "GradientBoostingClassifier"


def test_rotate_and_prune_storage(tmp_path):
    """Verify retention policy removes older runs and clears DB records."""
    dummy_runs_dir = tmp_path / "runs"
    dummy_logs_dir = tmp_path / "logs"
    dummy_art_dir = tmp_path / "artifacts"
    dummy_runs_dir.mkdir()
    dummy_logs_dir.mkdir()
    dummy_art_dir.mkdir()

    # Create 4 run dirs with synthetic timestamps
    run_ids = [f"retention_test_run_{i}" for i in range(4)]
    for i, rid in enumerate(run_ids):
        rdir = dummy_runs_dir / rid
        rdir.mkdir()
        (rdir / "events.jsonl").write_text("{}\n", encoding="utf-8")
        (dummy_logs_dir / f"{rid}.log").write_text("log\n", encoding="utf-8")
        register_run(rid, "data.csv")
        record_event(run_id=rid, agent="profiler", event_type="step_end")

    # Run prune with max_runs=2 -> should keep only 2 runs
    res = rotate_and_prune_storage(
        max_runs=2,
        max_age_days=365,
        runs_dir=str(dummy_runs_dir),
        logs_dir=str(dummy_logs_dir),
        artifacts_dir=str(dummy_art_dir),
    )

    assert len(res["pruned_run_ids"]) == 2
    remaining_dirs = os.listdir(str(dummy_runs_dir))
    assert len(remaining_dirs) == 2

    # Verify SQLite rows were pruned for removed runs
    conn = _get_db()
    try:
        cur = conn.execute("SELECT run_id FROM runs WHERE run_id IN (?, ?)", tuple(res["pruned_run_ids"]))
        assert len(cur.fetchall()) == 0
    finally:
        conn.close()
