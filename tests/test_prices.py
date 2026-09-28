import json

import pandas as pd


def test_fetch_historical_prices_con_series(app_module, data_dir, monkeypatch):
    def fake_download(*args, **kwargs):
        return {
            "Close": pd.Series([100.0, 101.0], index=["2024-01-01", "2024-01-02"])
        }

    monkeypatch.setattr(app_module.yf, "download", fake_download)
    result = app_module.fetch_historical_prices(["VOO"], "2024-01-01", cache={})
    assert result["VOO"] == {"2024-01-01": 100.0, "2024-01-02": 101.0}
    # El caché se persiste en el data/ temporal
    saved = json.loads((data_dir / "price_cache.json").read_text())
    assert saved == result


def test_fetch_historical_prices_con_dataframe(app_module, data_dir, monkeypatch):
    def fake_download(*args, **kwargs):
        return {"Close": pd.DataFrame({"VOO": [99.5]}, index=["2024-01-03"])}

    monkeypatch.setattr(app_module.yf, "download", fake_download)
    result = app_module.fetch_historical_prices(["VOO"], "2024-01-01", cache={})
    assert result["VOO"] == {"2024-01-03": 99.5}


def test_fetch_prices_con_dataframe(app_module, monkeypatch):
    def fake_download(*args, **kwargs):
        return {"Close": pd.DataFrame({"VOO": [100.0, 101.0]})}

    monkeypatch.setattr(app_module.yf, "download", fake_download)
    assert app_module.fetch_prices(["VOO"]) == {"VOO": 101.0}


def test_fetch_prices_sin_red_devuelve_vacio(app_module):
    assert app_module.fetch_prices(["VOO"]) == {}
