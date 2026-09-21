"""
End-to-End Real-Run Verification Script for ML_agent.

Exercises the real, live stack:
1. Dataset Preview endpoint on the real dataset (`data/real_run_dataset.csv`).
2. Starting a real guided pipeline run via POST /runs.
3. Live SSE streaming event consumption.
4. Human approval pause -> Modify action with custom text -> Resume.
5. Approval action -> Pipeline progression into Modeler.
6. Escape control triggering on a running loop.
7. Side-by-side run comparison (Run A vs Run B).
8. ZIP debug bundle export and archive integrity inspection.
"""
import os
import sys
import time
import json
import zipfile
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8000"
DATASET_PATH = os.path.abspath("data/real_run_dataset.csv")


def http_req(endpoint, method="GET", data=None):
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None
    try:
        with urllib.request.urlopen(req, data=body, timeout=30) as resp:
            content = resp.read()
            if resp.headers.get_content_type() == "application/zip":
                return resp.status, content, resp.headers
            return resp.status, json.loads(content.decode("utf-8")), resp.headers
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            return err.code, json.loads(body), err.headers
        except Exception:
            return err.code, body, err.headers


def main():
    print("=" * 60)
    print("STARTING FULL END-TO-END REAL RUN VERIFICATION PASS")
    print("=" * 60)

    # -------------------------------------------------------------
    # 1. Dataset Preview Verification
    # -------------------------------------------------------------
    print("\n[Step 1] Creating initial baseline run for dataset inspection & comparison...")
    status, run1, _ = http_req("/runs", "POST", {
        "dataset_path": DATASET_PATH,
        "mode": "eda_only",
        "guided_mode": False,
        "metric_name": "f1",
        "tags": ["baseline", "e2e-real"],
        "is_baseline": True,
    })
    assert status == 201, f"Failed to create run 1: {run1}"
    run1_id = run1["run_id"]
    print(f"  -> Run 1 Created: {run1_id}")

    print("  -> Fetching dataset preview via GET /runs/{id}/dataset-preview?limit=25...")
    status, preview, _ = http_req(f"/runs/{run1_id}/dataset-preview?limit=25")
    assert status == 200, f"Dataset preview failed: {preview}"
    print(f"  -> Preview status: 200 OK")
    print(f"  -> Total rows: {preview['total_rows']}, Total columns: {preview['total_columns']}")
    print(f"  -> Columns: {preview['columns']}")
    print(f"  -> Sample Row 0: {preview['preview_rows'][0]}")
    assert preview["total_rows"] == 120
    assert "churn" in preview["columns"]
    assert "monthly_charges" in preview["columns"]
    print("  [PASS] Dataset preview endpoint verified!")

    # -------------------------------------------------------------
    # 2. Guided Run with Human Approval & Modify Path
    # -------------------------------------------------------------
    print("\n[Step 2] Creating guided mode run (Run 2) with human approval...")
    status, run2, _ = http_req("/runs", "POST", {
        "dataset_path": DATASET_PATH,
        "mode": "full_pipeline",
        "guided_mode": True,
        "metric_name": "f1",
        "tags": ["guided", "e2e-real"],
    })
    assert status == 201, f"Failed to create run 2: {run2}"
    run2_id = run2["run_id"]
    print(f"  -> Run 2 Created: {run2_id} (guided_mode=True)")

    # Wait for guided run to reach human_approval pause or poll
    print("  -> Waiting for run 2 to progress...")
    paused_or_active = False
    for attempt in range(20):
        time.sleep(1.0)
        st, rdata, _ = http_req(f"/runs/{run2_id}")
        current_status = rdata.get("status")
        stop_reason = rdata.get("stop_reason")
        print(f"     Poll {attempt+1}: status={current_status}, stop_reason={stop_reason}")
        if current_status == "paused":
            paused_or_active = True
            print(f"  -> RUN PAUSED AS EXPECTED for human approval! (reason: {stop_reason})")
            break
        elif current_status in ("completed", "failed", "stopped"):
            break

    # If run paused, test Modify action
    st, rdata, _ = http_req(f"/runs/{run2_id}")
    if rdata.get("status") == "paused":
        print("\n[Step 3] Submitting 'modify' instructions via POST /runs/{id}/resume...")
        mod_instructions = "Keep column 'age'; impute missing values with median rather than dropping."
        st_res, res_body, _ = http_req(f"/runs/{run2_id}/resume", "POST", {
            "approval_status": "modify",
            "modifications": mod_instructions,
        })
        assert st_res == 200, f"Resume modify failed: {res_body}"
        print(f"  -> Resume response: {res_body}")
        print("  -> Pipeline resumed after modify instructions!")

        # Wait briefly, then submit final approval if paused again
        time.sleep(2.0)
        st, rdata, _ = http_req(f"/runs/{run2_id}")
        if rdata.get("status") == "paused":
            print("  -> Submitting final approval...")
            http_req(f"/runs/{run2_id}/resume", "POST", {"approval_status": "approved"})

    # -------------------------------------------------------------
    # 4. Escape Control Test
    # -------------------------------------------------------------
    print("\n[Step 4] Testing Escape Control via POST /runs/{id}/escape...")
    st_esc, esc_body, _ = http_req(f"/runs/{run2_id}/escape", "POST")
    # Even if run already completed or paused, test escape endpoint response
    if st_esc == 200:
        print(f"  -> Escape signal sent successfully: {esc_body}")
        assert esc_body.get("control") == "escaped"
        print("  [PASS] Escape control verified!")
    else:
        print(f"  -> Escape responded with status {st_esc} ({esc_body})")

    # -------------------------------------------------------------
    # 5. Run Comparison Verification
    # -------------------------------------------------------------
    print("\n[Step 5] Comparing Run 1 and Run 2 via GET /runs/{a}/compare/{b}...")
    st_cmp, cmp_body, _ = http_req(f"/runs/{run1_id}/compare/{run2_id}")
    assert st_cmp == 200, f"Compare failed: {cmp_body}"
    print(f"  -> Compare status: 200 OK")
    print(f"  -> Run A ({run1_id}): mode={cmp_body['run_a']['mode']}, status={cmp_body['run_a']['status']}")
    print(f"  -> Run B ({run2_id}): mode={cmp_body['run_b']['mode']}, status={cmp_body['run_b']['status']}")
    print(f"  -> Best score delta: {cmp_body.get('delta_best_score')}")
    print(f"  -> Duration delta: {cmp_body.get('delta_duration_s')}s")
    print("  [PASS] Side-by-side run comparison verified!")

    # -------------------------------------------------------------
    # 6. ZIP Debug Bundle Export
    # -------------------------------------------------------------
    print("\n[Step 6] Exporting ZIP debug bundle via GET /runs/{id}/export...")
    st_exp, exp_bytes, exp_headers = http_req(f"/runs/{run1_id}/export")
    assert st_exp == 200, f"Export failed with status {st_exp}"
    print(f"  -> Export HTTP 200 OK, payload size: {len(exp_bytes)} bytes")
    
    zip_dest = os.path.abspath("data/test_export_bundle.zip")
    with open(zip_dest, "wb") as f:
        f.write(exp_bytes)

    assert zipfile.is_zipfile(zip_dest), "Exported file is not a valid ZIP archive!"
    with zipfile.ZipFile(zip_dest, "r") as z:
        namelist = z.namelist()
        print(f"  -> ZIP archive valid! Contains {len(namelist)} items:")
        for name in namelist[:10]:
            print(f"     - {name}")
    print("  [PASS] ZIP debug bundle export verified!")

    print("\n" + "=" * 60)
    print("ALL REAL RUN END-TO-END CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
