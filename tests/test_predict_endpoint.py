import io
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import init_db

client = TestClient(app)


def test_predict_endpoint_flow():
    init_db()

    # 1. Project house_price_predection should exist on disk
    train_csv_path = "projects/house_price_predection/datasets/dataset_v1/data.csv"
    train_df = pd.read_csv(train_csv_path)

    # Make test dataframe with 10 rows without SalePrice
    test_df = train_df.head(10).drop(columns=["SalePrice"])

    csv_buf = io.BytesIO()
    test_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue()

    # Query leaderboard to get a valid run ID
    lb_res = client.get("/projects/house_price_predection/models?metric=rmse")
    assert lb_res.status_code == 200
    runs = lb_res.json()["leaderboard"]
    assert len(runs) > 0
    run_id = runs[0]["run_id"]

    # 2. Test valid prediction with explicit id_column
    res = client.post(
        f"/projects/house_price_predection/models/{run_id}/predict",
        files={"test_file": ("test.csv", csv_bytes, "text/csv")},
        data={"id_column": "Id"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/csv")
    assert "submission.csv" in res.headers.get("content-disposition", "")

    # Parse response CSV
    res_df = pd.read_csv(io.StringIO(res.text))
    assert list(res_df.columns) == ["Id", "SalePrice"]
    assert len(res_df) == 10
    assert not res_df["SalePrice"].isna().any()

    # 3. Test valid prediction with auto-detected ID column (Id)
    res_auto = client.post(
        f"/projects/house_price_predection/models/{run_id}/predict",
        files={"test_file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert res_auto.status_code == 200, res_auto.text
    res_auto_df = pd.read_csv(io.StringIO(res_auto.text))
    assert list(res_auto_df.columns) == ["Id", "SalePrice"]
    assert len(res_auto_df) == 10

    # 4. Test missing columns validation error (must return 400 with missing columns named)
    bad_df = pd.DataFrame({"random_column": [1, 2, 3]})
    bad_buf = io.BytesIO()
    bad_df.to_csv(bad_buf, index=False)

    res_missing = client.post(
        f"/projects/house_price_predection/models/{run_id}/predict",
        files={"test_file": ("bad.csv", bad_buf.getvalue(), "text/csv")},
    )
    assert res_missing.status_code == 400
    detail = res_missing.json().get("detail", "")
    assert "Missing required feature column(s)" in detail
    assert "LotArea" in detail or "OverallQual" in detail

    # 5. Test invalid file extension
    res_ext = client.post(
        f"/projects/house_price_predection/models/{run_id}/predict",
        files={"test_file": ("bad.txt", b"some text", "text/plain")},
    )
    assert res_ext.status_code == 400
    assert "CSV" in res_ext.json().get("detail", "")

    # 6. Test empty CSV
    empty_buf = io.BytesIO(b"")
    res_empty = client.post(
        f"/projects/house_price_predection/models/{run_id}/predict",
        files={"test_file": ("empty.csv", empty_buf.getvalue(), "text/csv")},
    )
    assert res_empty.status_code == 400

    # 7. Test non-existent project
    res_404 = client.post(
        f"/projects/non_existent_project_xyz/models/{run_id}/predict",
        files={"test_file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert res_404.status_code == 404
