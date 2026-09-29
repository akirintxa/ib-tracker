import json
from datetime import datetime, timedelta

import pandas as pd
from yfinance.exceptions import YFDataException


class FakeFundsData:
    def __init__(self, top_holdings=None, error=None):
        self._top = top_holdings
        self._error = error

    @property
    def top_holdings(self):
        if self._error:
            raise self._error
        return self._top


def fake_ticker_factory(by_ticker, calls):
    class FakeTicker:
        def __init__(self, symbol):
            calls.append(symbol)
            self.funds_data = by_ticker[symbol]

    return FakeTicker


VOO_TOP = pd.DataFrame(
    {
        "Symbol": ["NVDA", "MSFT", "AAPL"],
        "Name": ["NVIDIA Corp", "Microsoft Corp", "Apple Inc"],
        "Holding Percent": [0.0781, 0.0702, 0.0655],
    }
).set_index("Symbol")


def test_top_holdings_de_etf_y_accion(app_module, data_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module.yf,
        "Ticker",
        fake_ticker_factory(
            {
                "VOO": FakeFundsData(VOO_TOP),
                "MSFT": FakeFundsData(error=YFDataException("MSFT: No Fund data found.")),
            },
            calls,
        ),
    )
    result = app_module.get_etf_holdings(["VOO", "MSFT"])
    assert result == {
        "VOO": [
            {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 7.81},
            {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 7.02},
            {"symbol": "AAPL", "name": "Apple Inc", "weight": 6.55},
        ]
    }
    # La acción queda en caché como "sin composición" para no volver a consultarla
    saved = json.loads((data_dir / "etf_holdings_cache.json").read_text())
    assert saved["MSFT"]["holdings"] == []
    assert len(saved["VOO"]["holdings"]) == 3


def test_usa_cache_vigente_sin_red(app_module, data_dir, monkeypatch):
    calls = []
    by_ticker = {"VOO": FakeFundsData(VOO_TOP)}
    monkeypatch.setattr(app_module.yf, "Ticker", fake_ticker_factory(by_ticker, calls))
    now = datetime(2026, 9, 1, 12, 0)
    app_module.get_etf_holdings(["VOO"], now=now)
    app_module.get_etf_holdings(["VOO"], now=now + timedelta(days=6))
    assert calls == ["VOO"]
    # Pasada la semana se vuelve a consultar
    app_module.get_etf_holdings(["VOO"], now=now + timedelta(days=8))
    assert calls == ["VOO", "VOO"]


def test_falla_de_red_no_borra_cache(app_module, data_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module.yf,
        "Ticker",
        fake_ticker_factory({"VOO": FakeFundsData(VOO_TOP)}, calls),
    )
    now = datetime(2026, 9, 1, 12, 0)
    app_module.get_etf_holdings(["VOO"], now=now)

    # Sin red: se devuelve el caché vencido y no se pisa
    def sin_red(*args, **kwargs):
        raise RuntimeError("sin red")

    monkeypatch.setattr(app_module.yf, "Ticker", sin_red)
    result = app_module.get_etf_holdings(["VOO"], now=now + timedelta(days=30))
    assert [h["symbol"] for h in result["VOO"]] == ["NVDA", "MSFT", "AAPL"]
    saved = json.loads((data_dir / "etf_holdings_cache.json").read_text())
    assert saved["VOO"]["fetchedAt"] == now.isoformat(timespec="seconds")


def test_sin_red_y_sin_cache_devuelve_vacio(app_module, data_dir):
    assert app_module.get_etf_holdings(["VOO", "MSFT"]) == {}
    assert not (data_dir / "etf_holdings_cache.json").exists()


def test_endpoint_requiere_login(app_module, data_dir):
    client = app_module.app.test_client()
    assert client.get("/api/etf-holdings").status_code == 401


def test_endpoint_consulta_solo_tickers_del_portafolio(app_module, data_dir, monkeypatch):
    seen = []

    def fake_get(tickers, now=None):
        seen.extend(tickers)
        return {"VOO": [{"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 7.81}]}

    monkeypatch.setattr(app_module, "get_etf_holdings", fake_get)
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    resp = client.get("/api/etf-holdings?tickers=EVIL")
    assert resp.status_code == 200
    assert resp.get_json()["holdings"]["VOO"][0]["symbol"] == "NVDA"
    assert set(seen) == {"VOO", "MSFT"}
