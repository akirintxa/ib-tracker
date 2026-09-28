# IB Portfolio Tracker

Dashboard web (Flask + Chart.js) que lee los CSV de transacciones exportados por
Interactive Brokers y muestra posiciones, costo promedio con comisiones,
dividendos, histórico mensual y comparativa contra el S&P 500 (VOO).

Más detalle de la arquitectura en [GEMINI.md](GEMINI.md).

## Ejecutar

```bash
pip install -r requirements.txt
cp .env.example .env   # define al menos IB_TRACKER_PASSWORD
./iniciar-tracker.command   # carga .env y abre http://localhost:8080
```

Si prefieres `python app.py`, exporta antes `IB_TRACKER_PASSWORD` en tu terminal
(`app.py` no lee `.env` por sí solo).

Coloca los reportes de IB en `data/` con el patrón `U13493500*.csv`
(la carpeta está en `.gitignore`), o súbelos desde el botón "Subir CSV".

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

La suite vive en `tests/` y no necesita red ni tus datos reales:

- `tests/fixtures/sample_transactions.csv` es un reporte de ejemplo
  anonimizado (cuenta `U0000000`, montos inventados) con compras, ventas,
  una posición cerrada, dividendos con retención y filas que deben ignorarse.
- Cada prueba copia ese CSV a un `data/` temporal, así que no toca tu carpeta
  `data/` ni el caché de precios.
- Las llamadas a Yahoo Finance están bloqueadas; las pruebas que las necesitan
  usan precios simulados.

| Archivo | Qué cubre |
| --- | --- |
| `test_parsing.py` | Lectura del CSV, filas ignoradas, deduplicación entre archivos |
| `test_holdings.py` | Posiciones abiertas y costo promedio con comisiones |
| `test_dividends.py` | Dividendos por ticker, por trimestre y retenciones |
| `test_history.py` | Histórico mensual de aportes, posiciones y rentabilidad |
| `test_prices.py` | Manejo de respuestas de yfinance (Series y DataFrame) |
| `test_api.py` | Endpoint `/api/portfolio` con login |
| `test_security.py` | Contraseña por entorno, logout, expiración y archivos expuestos |

Las pruebas cargan `app.py` con un entorno controlado (contraseña de prueba),
así que no importa qué tengas definido en tu `.env`. `app-web.py` duplica
parte de esa lógica y hoy no tiene pruebas propias.
