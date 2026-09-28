import pytest


def test_totales(app_module, parsed):
    result = app_module.compute_dividends(parsed[1])
    assert result["totalGross"] == pytest.approx(32.50)
    assert result["totalTax"] == pytest.approx(4.88)
    assert result["totalNet"] == pytest.approx(27.62)


def test_por_ticker_ordenado_por_neto(app_module, parsed):
    by_ticker = app_module.compute_dividends(parsed[1])["byTicker"]
    assert [d["ticker"] for d in by_ticker] == ["VOO", "MSFT"]
    assert by_ticker[0] == {
        "ticker": "VOO",
        "name": "Vanguard S&P 500",
        "gross": 31.0,
        "tax": 4.65,
        "net": 26.35,
    }


def test_por_trimestre(app_module, parsed):
    by_quarter = app_module.compute_dividends(parsed[1])["byQuarter"]
    assert by_quarter == [
        {"quarter": "2024-Q1", "gross": 16.5, "tax": 2.48, "net": 14.02},
        {"quarter": "2024-Q2", "gross": 16.0, "tax": 2.4, "net": 13.6},
    ]


def test_detalle_empareja_dividendo_e_impuesto(app_module, parsed):
    detail = app_module.compute_dividends(parsed[1])["detail"]
    assert len(detail) == 3
    assert detail[0] == {
        "date": "2024-03-14",
        "symbol": "MSFT",
        "gross": 1.5,
        "tax": 0.23,
        "net": 1.27,
    }
