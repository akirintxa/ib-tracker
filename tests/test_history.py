import pytest


def _period(series, period):
    return next(s for s in series if s["period"] == period)


def test_cashflow_mensual(app_module, parsed):
    hist = app_module.compute_cashflow_history(*parsed)
    series = hist["series"]
    assert hist["firstDate"] == "2024-01-10"
    assert series[0]["period"] == "2024-01"

    jan = _period(series, "2024-01")
    assert jan["monthlyContributions"] == pytest.approx(1152.0)
    assert jan["netInvested"] == pytest.approx(1152.0)

    feb = _period(series, "2024-02")
    assert feb["netInvested"] == pytest.approx(2503.5)

    mar = _period(series, "2024-03")
    assert mar["monthlyContributions"] == pytest.approx(-558.0)
    assert mar["netInvested"] == pytest.approx(1945.5)
    assert mar["monthlyDividends"] == pytest.approx(14.02)

    jun = _period(series, "2024-06")
    assert jun["cumulativeDividends"] == pytest.approx(27.62)

    assert hist["totals"] == {"netInvested": 1945.5, "cumulativeDividends": 27.62}


def test_cashflow_sin_compras(app_module):
    hist = app_module.compute_cashflow_history([], [])
    assert hist["series"] == []
    assert hist["firstDate"] is None


def test_posiciones_al_cierre_de_cada_mes(app_module, parsed):
    periods = ["2024-01", "2024-02", "2024-03", "2024-04"]
    replay = app_module.replay_holdings_by_month(parsed[0], periods)
    assert replay["2024-01"] == {"VOO": 10, "RGTI": 100}
    assert replay["2024-02"] == {"VOO": 15, "RGTI": 100, "MSFT": 2}
    assert replay["2024-03"] == {"VOO": 12, "MSFT": 2}
    assert replay["2024-04"] == replay["2024-03"]


def test_iter_months_cruza_de_anio(app_module):
    from datetime import datetime

    months = app_module._iter_months("2023-11-15", datetime(2024, 2, 1))
    assert months == ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_price_on_or_before(app_module):
    prices = {"2024-01-02": 10.0, "2024-01-05": 11.0}
    assert app_module.price_on_or_before(prices, "2024-01-01") is None
    assert app_module.price_on_or_before(prices, "2024-01-04") == 10.0
    assert app_module.price_on_or_before(prices, "2024-02-01") == 11.0
    assert app_module.price_on_or_before({}, "2024-01-01") is None


def test_valor_de_mercado_y_rentabilidad(app_module, parsed, monkeypatch):
    prices = {
        "VOO": {"2024-01-10": 100.0, "2024-01-31": 105.0, "2024-02-29": 115.0},
        "RGTI": {"2024-01-31": 1.6, "2024-02-29": 1.8},
        "MSFT": {"2024-02-29": 410.0},
    }
    monkeypatch.setattr(
        app_module,
        "fetch_historical_prices",
        lambda tickers, start_date, cache=None: prices,
    )
    cashflow = app_module.compute_cashflow_history(*parsed)
    result = app_module.compute_portfolio_history(*parsed, cashflow)

    jan = _period(result["series"], "2024-01")
    assert jan["marketValue"] == pytest.approx(10 * 105 + 100 * 1.6)
    expected = round((1210 + 0 - 1152) / 1152 * 100, 2)
    assert jan["totalReturnPct"] == expected
    assert jan["priceReturnPct"] == expected

    feb = _period(result["series"], "2024-02")
    assert feb["marketValue"] == pytest.approx(15 * 115 + 100 * 1.8 + 2 * 410)

    bench = {b["period"]: b["vooReturnPct"] for b in result["benchmark"]}
    assert bench["2024-01"] == 5.0
    assert bench["2024-02"] == 15.0
