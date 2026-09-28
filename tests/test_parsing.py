import shutil

import pytest


def test_parse_csv_extrae_solo_operaciones_validas(parsed):
    trades, dividends = parsed
    # 6 compras/ventas válidas; el depósito y la fila con precio vacío se ignoran
    assert len(trades) == 6
    assert {t["symbol"] for t in trades} == {"VOO", "RGTI", "MSFT"}
    assert len(dividends) == 6


def test_parse_csv_mapea_columnas(parsed):
    trades, _ = parsed
    first = next(t for t in trades if t["date"] == "2024-01-10")
    assert first == {
        "date": "2024-01-10",
        "symbol": "VOO",
        "type": "Buy",
        "qty": 10.0,
        "price": 100.0,
        "gross": -1000.0,
        "commission": -1.0,
        "net": -1001.0,
    }


def test_parse_csv_clasifica_dividendos_e_impuestos(parsed):
    _, dividends = parsed
    types = sorted((d["date"], d["symbol"], d["type"], d["amount"]) for d in dividends)
    assert types[:2] == [
        ("2024-03-14", "MSFT", "dividend", 1.5),
        ("2024-03-14", "MSFT", "tax", -0.23),
    ]


def test_parse_csv_deduplica_archivos_solapados(app_module, data_dir, parsed):
    shutil.copy(
        data_dir / "U13493500_sample.csv", data_dir / "U13493500_sample_copia.csv"
    )
    trades, dividends = app_module.parse_csv()
    assert len(trades) == len(parsed[0])
    assert len(dividends) == len(parsed[1])


def test_find_csv_files_sin_archivos(app_module, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        app_module.find_csv_files()
