import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_CSV = FIXTURES / "sample_transactions.csv"


def _load_app_module():
    spec = importlib.util.spec_from_file_location("ib_tracker_app", ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def app_module():
    """Módulo app.py cargado una sola vez para toda la sesión."""
    return _load_app_module()


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
    return tmp_path


@pytest.fixture
def parsed(app_module, data_dir):
    """(trades, dividend_entries) del CSV de ejemplo."""
    return app_module.parse_csv()
