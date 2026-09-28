import pytest


def _by_ticker(holdings):
    return {h["ticker"]: h for h in holdings}


def test_posiciones_abiertas(app_module, parsed):
    holdings = _by_ticker(app_module.compute_holdings(parsed[0]))
    # RGTI se compró y se vendió completo: posición cerrada, se excluye
    assert set(holdings) == {"VOO", "MSFT"}
    assert holdings["VOO"]["qty"] == 12
    assert holdings["MSFT"]["qty"] == 2


def test_costo_promedio_incluye_comisiones(app_module, parsed):
    holdings = _by_ticker(app_module.compute_holdings(parsed[0]))
    # VOO: (1001 + 551) / 15 acciones compradas
    assert holdings["VOO"]["avgPrice"] == pytest.approx(103.4667)
    assert holdings["VOO"]["totalCost"] == pytest.approx(1241.60)
    # MSFT: 800.5 / 2
    assert holdings["MSFT"]["avgPrice"] == pytest.approx(400.25)
    assert holdings["MSFT"]["totalCost"] == pytest.approx(800.50)


def test_primer_precio_de_compra_y_nombre(app_module, parsed):
    holdings = _by_ticker(app_module.compute_holdings(parsed[0]))
    assert holdings["VOO"]["firstBuyPrice"] == 100.0
    assert holdings["VOO"]["name"] == "Vanguard S&P 500"
    assert holdings["MSFT"]["name"] == "Microsoft"


def test_sin_operaciones(app_module):
    assert app_module.compute_holdings([]) == []
