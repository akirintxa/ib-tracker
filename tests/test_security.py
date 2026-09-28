"""Login por variable de entorno, sesión y archivos que el servidor expone."""
import pytest

from conftest import TEST_PASSWORD


@pytest.fixture
def client(app_module, data_dir):
    return app_module.app.test_client()


@pytest.mark.parametrize(
    "path",
    [
        "/data/price_cache.json",
        "/data/U13493500_sample.csv",
        "/app.py",
        "/.env",
        "/GEMINI.md",
        "/api/portfolio",
        "/api/history",
        "/precios",
    ],
)
def test_datos_y_codigo_no_se_sirven_sin_login(client, path):
    assert client.get(path).status_code in (401, 404)


@pytest.mark.parametrize(
    "path", ["/", "/dashboard.js", "/login_helper.js", "/favicon.svg"]
)
def test_archivos_del_frontend_se_sirven(client, path):
    assert client.get(path).status_code == 200


def test_login_usa_la_contrasena_del_entorno(client):
    assert client.post("/api/login", json={"password": "1234"}).status_code == 401
    assert client.post("/api/login", json={}).status_code == 401
    assert client.post("/api/login", data="no-json").status_code == 401
    ok = client.post("/api/login", json={"password": TEST_PASSWORD})
    assert ok.status_code == 200


def test_logout_y_expiracion_de_sesion(app_module, client):
    client.post("/api/login", json={"password": TEST_PASSWORD})
    with client.session_transaction() as sess:
        assert sess.permanent
    lifetime = app_module.app.permanent_session_lifetime.total_seconds()
    assert lifetime == app_module.SESSION_MINUTES * 60
    client.post("/api/logout")
    assert client.get("/precios").status_code == 401


def test_sin_contrasena_el_servidor_no_arranca(monkeypatch):
    from conftest import load_app_module

    with pytest.raises(RuntimeError, match="IB_TRACKER_PASSWORD"):
        load_app_module(IB_TRACKER_PASSWORD="")
