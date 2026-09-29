import importlib.util
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_CSV = FIXTURES / "sample_transactions.csv"

TEST_PASSWORD = "test-password"

# Variables que app.py lee al importarse; se limpian para que el entorno de
# quien corre las pruebas no cambie el resultado.
APP_ENV_VARS = [
    "IB_TRACKER_MODE",
    "IB_TRACKER_PROXY",
    "IB_TRACKER_PRICE_FALLBACK",
    "IB_TRACKER_PORT",
    "IB_TRACKER_BASEDIR",
    "IB_TRACKER_SECRET_KEY",
    "IB_TRACKER_PASSWORD",
    "IB_TRACKER_SESSION_MINUTES",
    "PYTHONANYWHERE_DOMAIN",
    "HTTP_PROXY",
    "HTTPS_PROXY",
]


def load_app_module(**env):
    """Carga app.py con un entorno controlado y restaura os.environ al terminar."""
    saved = {k: os.environ.get(k) for k in APP_ENV_VARS}
    try:
        for k in APP_ENV_VARS:
            os.environ.pop(k, None)
        os.environ["IB_TRACKER_PASSWORD"] = TEST_PASSWORD
        os.environ.update(env)
        spec = importlib.util.spec_from_file_location(
            "ib_tracker_app", ROOT / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture(scope="session")
def app_module():
    """Módulo app.py en modo local, cargado una sola vez para toda la sesión."""
    return load_app_module(IB_TRACKER_MODE="local")


@pytest.fixture(autouse=True)
def no_network(app_module, monkeypatch):
    """Evita llamadas reales a Yahoo Finance; cada prueba mockea lo que necesite."""

    def _blocked(*args, **kwargs):
        raise RuntimeError("Acceso a red deshabilitado en las pruebas")

    monkeypatch.setattr(app_module.yf, "download", _blocked)
    monkeypatch.setattr(app_module.yf, "Ticker", _blocked)


@pytest.fixture
def data_dir(app_module, monkeypatch, tmp_path):
    """Directorio data/ temporal con el CSV de ejemplo anonimizado."""
    shutil.copy(SAMPLE_CSV, tmp_path / "U13493500_sample.csv")
    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        app_module, "PRICE_CACHE_PATH", str(tmp_path / "price_cache.json")
    )
    monkeypatch.setattr(
        app_module,
        "ETF_HOLDINGS_CACHE_PATH",
        str(tmp_path / "etf_holdings_cache.json"),
    )
    return tmp_path


@pytest.fixture
def parsed(app_module, data_dir):
    """(trades, dividend_entries) del CSV de ejemplo."""
    return app_module.parse_csv()
