import pytest


@pytest.fixture
def client(app_module, data_dir, monkeypatch):
    monkeypatch.setattr(
        app_module, "fetch_prices", lambda tickers: {t: 123.0 for t in tickers}
    )
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_portfolio_requiere_login(client):
    resp = client.get("/api/portfolio")
    assert resp.status_code == 401


def test_portfolio_con_csv_de_ejemplo(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.get_json()
    assert {h["ticker"] for h in data["holdings"]} == {"VOO", "MSFT"}
    assert data["prices"] == {"VOO": 123.0, "MSFT": 123.0}
    assert data["vooBase"] == 100.0
    assert data["firstDate"] == "2024-01-10"
    assert data["dividends"]["totalNet"] == 27.62
    # Transacciones ordenadas de la más reciente a la más antigua
    dates = [t["date"] for t in data["trades"]]
    assert dates == sorted(dates, reverse=True)
