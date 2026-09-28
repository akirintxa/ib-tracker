import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("IB_TRACKER_PASSWORD", "test-password")

spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
assert spec is not None
assert spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fetch_historical_prices_handles_series_and_frame():
    import pandas as pd

    cache = {}
    tickers = ["VOO"]

    class DummyDataFrame:
        def __init__(self):
            self.empty = False
            self.columns = ["Close"]

        def get(self, key):
            if key != "Close":
                return None
            return pd.Series([100.0, 101.0], index=["2024-01-01", "2024-01-02"])

    class DummyYFinance:
        @staticmethod
        def download(*args, **kwargs):
            return {
                "Close": pd.Series([100.0, 101.0], index=["2024-01-01", "2024-01-02"])
            }

    module.yf.download = DummyYFinance.download
    result = module.fetch_historical_prices(tickers, "2024-01-01", cache=cache)
    assert result["VOO"]["2024-01-01"] == 100.0
    assert result["VOO"]["2024-01-02"] == 101.0


def test_fetch_prices_handles_dataframe_close_data():
    import pandas as pd

    class DummyYFinance:
        @staticmethod
        def download(*args, **kwargs):
            return {"Close": pd.DataFrame({"VOO": [100.0, 101.0]})}

    module.yf.download = DummyYFinance.download
    result = module.fetch_prices(["VOO"])
    assert result["VOO"] == 101.0


def test_data_and_source_not_served_without_login():
    client = module.app.test_client()
    for path in [
        "/data/price_cache.json",
        "/data/U13493500.test.csv",
        "/app.py",
        "/.env",
        "/GEMINI.md",
        "/api/portfolio",
        "/precios",
    ]:
        assert client.get(path).status_code in (401, 404), path


def test_frontend_files_still_served():
    client = module.app.test_client()
    for path in ["/", "/dashboard.js", "/login_helper.js", "/favicon.svg"]:
        assert client.get(path).status_code == 200, path


def test_login_uses_env_password():
    client = module.app.test_client()
    bad = client.post("/api/login", json={"password": "1234"})
    assert bad.status_code == 401
    ok = client.post("/api/login", json={"password": os.environ["IB_TRACKER_PASSWORD"]})
    assert ok.status_code == 200


def test_logout_and_session_expiry():
    client = module.app.test_client()
    client.post("/api/login", json={"password": os.environ["IB_TRACKER_PASSWORD"]})
    with client.session_transaction() as sess:
        assert sess.permanent
    assert module.app.permanent_session_lifetime.total_seconds() == module.SESSION_MINUTES * 60
    client.post("/api/logout")
    assert client.get("/precios").status_code == 401
