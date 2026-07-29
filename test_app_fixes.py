import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
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
