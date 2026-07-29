import csv
import glob
import json
import os
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from functools import wraps

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

# Forzar la ruta al directorio donde está el script
basedir = os.path.abspath(os.path.dirname(__file__))

# Crear subcarpeta data si no existe
DATA_DIR = os.path.join(basedir, "data")
os.makedirs(DATA_DIR, exist_ok=True)
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.json")

app = Flask(__name__, static_folder=basedir, static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
CORS(app)
app.secret_key = "ib-tracker-secret-key-change-me"  # Cambia esto por algo seguro
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB — reportes IB pueden ser grandes
)

# Configuración de seguridad
PASSCODE = "1234"  # <--- CAMBIA TU CONTRASEÑA AQUÍ


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)

    return decorated_function


@app.errorhandler(404)
def api_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Ruta no encontrada"}), 404
    return e.get_response()


@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"error": "El archivo es demasiado grande (máx. 50 MB)"}), 413


@app.errorhandler(500)
def api_server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Error interno del servidor"}), 500
    return e.get_response()


# Nombres legibles para los tickers conocidos
TICKER_NAMES = {
    "VOO": "Vanguard S&P 500",
    "QQQ": "Invesco QQQ",
    "NVDA": "NVIDIA",
    "MSFT": "Microsoft",
    "META": "Meta Platforms",
    "GOOGL": "Alphabet",
    "GLD": "SPDR Gold",
    "XLE": "Energy SPDR",
    "XLF": "Financial SPDR",
    "XLI": "Industrial SPDR",
    "XLP": "Cons. Staples SPDR",
    "RGTI": "Rigetti Computing",
}


def find_csv_files():
    """Busca todos los archivos CSV del broker en el directorio data."""
    pattern = os.path.join(DATA_DIR, "U13493500*.csv")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(
            f"No se encontró ningún archivo CSV con patrón U13493500*.csv en {DATA_DIR}"
        )
    return files


def parse_csv():
    """
    Parsea todos los archivos CSV encontrados y extrae transacciones,
    evitando duplicados si los archivos se solapan en fechas.
    """
    csv_paths = find_csv_files()
    trades = []
    dividends = []

    # Usamos un Set para recordar las filas exactas que ya procesamos
    # y así evitar duplicar transacciones si hay solapamiento entre dos archivos CSV
    seen_rows = set()

    for csv_path in csv_paths:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                # Convertir la fila a tupla para poder meterla en el set
                row_tuple = tuple(row)
                if row_tuple in seen_rows:
                    continue

                if len(row) < 3 or row[0] != "Transaction History":
                    continue
                if row[1] != "Data":
                    continue

                seen_rows.add(row_tuple)

                # Columnas: Date, Account, Description, Transaction Type, Symbol,
                #           Quantity, Price, Price Currency, Gross Amount, Commission, Net Amount
                date_str = row[2].strip()
                description = row[4].strip()
                tx_type = row[5].strip()
                symbol = row[6].strip()
                qty_str = row[7].strip()
                price_str = row[8].strip()
                gross_str = row[10].strip()
                commission_str = row[11].strip()
                net_str = row[12].strip()

                if tx_type in ("Buy", "Sell"):
                    try:
                        trades.append(
                            {
                                "date": date_str,
                                "symbol": symbol,
                                "type": tx_type,
                                "qty": float(qty_str),
                                "price": float(price_str),
                                "gross": float(gross_str),
                                "commission": float(commission_str),
                                "net": float(net_str),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

                elif tx_type == "Dividend":
                    try:
                        dividends.append(
                            {
                                "date": date_str,
                                "symbol": symbol,
                                "type": "dividend",
                                "amount": float(net_str),
                                "description": description,
                            }
                        )
                    except (ValueError, IndexError):
                        continue

                elif tx_type == "Foreign Tax Withholding":
                    try:
                        dividends.append(
                            {
                                "date": date_str,
                                "symbol": symbol,
                                "type": "tax",
                                "amount": float(net_str),  # negativo
                                "description": description,
                            }
                        )
                    except (ValueError, IndexError):
                        continue

    return trades, dividends


def compute_holdings(trades):
    """
    Calcula posiciones actuales.
    Precio promedio = suma de |Net Amount| de compras / suma de Quantity de compras.
    Esto incluye comisiones en el cost basis.
    Si una posición tiene qty ≈ 0, se considera cerrada y se excluye.
    """
    # Agrupar por símbolo
    buys = defaultdict(lambda: {"total_cost": 0.0, "total_qty": 0.0})
    sells = defaultdict(lambda: {"total_proceeds": 0.0, "total_qty": 0.0})
    first_buy_price = {}  # Para VOO_BASE y similares

    # Ordenar por fecha para obtener primera compra correctamente
    sorted_trades = sorted(trades, key=lambda t: t["date"])

    for trade in sorted_trades:
        sym = trade["symbol"]
        if trade["type"] == "Buy":
            # Net amount para compras es negativo, tomamos valor absoluto
            cost = abs(trade["net"])
            buys[sym]["total_cost"] += cost
            buys[sym]["total_qty"] += trade["qty"]
            if sym not in first_buy_price:
                first_buy_price[sym] = trade["price"]
        elif trade["type"] == "Sell":
            sells[sym]["total_proceeds"] += trade["net"]  # positivo
            sells[sym]["total_qty"] += abs(trade["qty"])

    holdings = []
    for sym in buys:
        buy_qty = buys[sym]["total_qty"]
        sell_qty = sells[sym]["total_qty"] if sym in sells else 0.0
        net_qty = buy_qty - sell_qty

        # Excluir posiciones cerradas (qty ≈ 0)
        if net_qty < 0.0001:
            continue

        # Precio promedio de compra (con comisiones incluidas)
        avg_price = (
            buys[sym]["total_cost"] / buys[sym]["total_qty"]
            if buys[sym]["total_qty"] > 0
            else 0
        )
        total_cost = avg_price * net_qty

        holdings.append(
            {
                "ticker": sym,
                "name": TICKER_NAMES.get(sym, sym),
                "qty": round(net_qty, 4),
                "avgPrice": round(avg_price, 4),
                "totalCost": round(total_cost, 2),
                "firstBuyPrice": first_buy_price.get(sym, 0),
            }
        )

    return holdings


def compute_dividends(dividend_entries):
    """
    Agrupa dividendos por ticker y por trimestre.
    Retorna:
      - by_ticker: {symbol: {gross, tax, net}}
      - by_quarter: [{quarter, gross, tax, net}] ordenado cronológicamente
      - detail: [{date, symbol, gross, tax, net}] por cada evento de dividendo
      - total_gross, total_tax, total_net
    """
    # Agrupar por ticker
    by_ticker = defaultdict(lambda: {"gross": 0.0, "tax": 0.0, "net": 0.0})
    # Agrupar por trimestre
    by_quarter = defaultdict(lambda: {"gross": 0.0, "tax": 0.0, "net": 0.0})
    # Agrupar por (date, symbol) para emparejar dividendo + tax
    events = defaultdict(lambda: {"gross": 0.0, "tax": 0.0})

    for entry in dividend_entries:
        sym = entry["symbol"]
        date_str = entry["date"]

        # Determinar trimestre
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            q = (dt.month - 1) // 3 + 1
            quarter_label = f"{dt.year}-Q{q}"
        except ValueError:
            continue

        if entry["type"] == "dividend":
            amount = entry["amount"]
            by_ticker[sym]["gross"] += amount
            by_quarter[quarter_label]["gross"] += amount
            events[(date_str, sym)]["gross"] += amount
        elif entry["type"] == "tax":
            amount = abs(entry["amount"])
            by_ticker[sym]["tax"] += amount
            by_quarter[quarter_label]["tax"] += amount
            events[(date_str, sym)]["tax"] += amount

    # Calcular netos
    for sym in by_ticker:
        by_ticker[sym]["net"] = by_ticker[sym]["gross"] - by_ticker[sym]["tax"]

    for q in by_quarter:
        by_quarter[q]["net"] = by_quarter[q]["gross"] - by_quarter[q]["tax"]

    # Ordenar trimestres cronológicamente
    sorted_quarters = sorted(by_quarter.keys())
    quarters_list = []
    for q in sorted_quarters:
        quarters_list.append(
            {
                "quarter": q,
                "gross": round(by_quarter[q]["gross"], 2),
                "tax": round(by_quarter[q]["tax"], 2),
                "net": round(by_quarter[q]["net"], 2),
            }
        )

    # Construir detalle
    detail = []
    for (date_str, sym), vals in sorted(events.items()):
        detail.append(
            {
                "date": date_str,
                "symbol": sym,
                "gross": round(vals["gross"], 2),
                "tax": round(vals["tax"], 2),
                "net": round(vals["gross"] - vals["tax"], 2),
            }
        )

    # Totales
    total_gross = sum(v["gross"] for v in by_ticker.values())
    total_tax = sum(v["tax"] for v in by_ticker.values())
    total_net = total_gross - total_tax

    # Convertir by_ticker a lista
    ticker_list = []
    for sym in sorted(
        by_ticker.keys(), key=lambda s: by_ticker[s]["net"], reverse=True
    ):
        ticker_list.append(
            {
                "ticker": sym,
                "name": TICKER_NAMES.get(sym, sym),
                "gross": round(by_ticker[sym]["gross"], 2),
                "tax": round(by_ticker[sym]["tax"], 2),
                "net": round(by_ticker[sym]["net"], 2),
            }
        )

    return {
        "byTicker": ticker_list,
        "byQuarter": quarters_list,
        "detail": detail,
        "totalGross": round(total_gross, 2),
        "totalTax": round(total_tax, 2),
        "totalNet": round(total_net, 2),
    }


def _month_key(date_str):
    return date_str[:7]


def _iter_months(start_date_str, end_date=None):
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = end_date or datetime.today()
    year, month = start.year, start.month
    months = []
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _month_end_date(period):
    year, month = map(int, period.split("-"))
    last_day = monthrange(year, month)[1]
    month_end = f"{year}-{month:02d}-{last_day:02d}"
    today = datetime.today().strftime("%Y-%m-%d")
    return month_end if month_end <= today else today


def compute_cashflow_history(trades, dividend_entries):
    """Snapshots mensuales de capital invertido y dividendos acumulados."""
    buy_dates = [t["date"] for t in trades if t["type"] == "Buy"]
    if not buy_dates:
        return {
            "granularity": "monthly",
            "series": [],
            "firstDate": None,
            "totals": {"netInvested": 0, "cumulativeDividends": 0},
        }

    first_date = min(buy_dates)
    months = _iter_months(first_date)

    monthly_buys = defaultdict(float)
    monthly_sells = defaultdict(float)
    for t in trades:
        mk = _month_key(t["date"])
        if t["type"] == "Buy":
            monthly_buys[mk] += abs(t["net"])
        elif t["type"] == "Sell":
            monthly_sells[mk] += t["net"]

    monthly_div_net = defaultdict(float)
    for e in dividend_entries:
        monthly_div_net[_month_key(e["date"])] += e["amount"]

    cum_invested = 0.0
    cum_divs = 0.0
    series = []
    for period in months:
        contributions = monthly_buys[period] - monthly_sells[period]
        cum_invested += contributions
        month_divs = monthly_div_net[period]
        cum_divs += month_divs
        series.append(
            {
                "period": period,
                "netInvested": round(cum_invested, 2),
                "cumulativeDividends": round(cum_divs, 2),
                "monthlyDividends": round(month_divs, 2),
                "monthlyContributions": round(contributions, 2),
            }
        )

    return {
        "granularity": "monthly",
        "series": series,
        "firstDate": first_date,
        "totals": {
            "netInvested": round(cum_invested, 2),
            "cumulativeDividends": round(cum_divs, 2),
        },
    }


def load_price_cache():
    if os.path.exists(PRICE_CACHE_PATH):
        try:
            with open(PRICE_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_price_cache(cache):
    with open(PRICE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def invalidate_price_cache():
    if os.path.exists(PRICE_CACHE_PATH):
        os.remove(PRICE_CACHE_PATH)


def replay_holdings_by_month(trades, periods):
    """Posiciones activas al cierre de cada mes."""
    sorted_trades = sorted(trades, key=lambda t: t["date"])
    holdings = defaultdict(float)
    result = {}
    trade_idx = 0

    for period in periods:
        month_end = _month_end_date(period)
        while (
            trade_idx < len(sorted_trades)
            and sorted_trades[trade_idx]["date"] <= month_end
        ):
            t = sorted_trades[trade_idx]
            if t["type"] == "Buy":
                holdings[t["symbol"]] += t["qty"]
            elif t["type"] == "Sell":
                holdings[t["symbol"]] -= abs(t["qty"])
            trade_idx += 1
        result[period] = {
            sym: round(qty, 4) for sym, qty in holdings.items() if qty >= 0.0001
        }

    return result


def price_on_or_before(ticker_prices, date_str):
    if not ticker_prices:
        return None
    best = None
    for d in sorted(ticker_prices.keys()):
        if d <= date_str:
            best = ticker_prices[d]
        else:
            break
    return best


def fetch_historical_prices(tickers, start_date, cache=None):
    """Descarga precios históricos y los persiste en caché local."""
    if cache is None:
        cache = load_price_cache()

    updated = False
    for ticker in tickers:
        if ticker not in cache:
            cache[ticker] = {}
        try:
            data = yf.download(
                ticker, start=start_date, auto_adjust=True, progress=False
            )
            if data is None or getattr(data, "empty", False):
                continue

            closes = data.get("Close")
            if closes is None:
                continue

            if isinstance(closes, pd.DataFrame):
                if ticker in closes.columns:
                    closes = closes[ticker]
                elif len(closes.columns) > 0:
                    first_column = closes.columns[0]
                    closes = closes[first_column]
                else:
                    continue

            series = closes.dropna()
            for idx, close in series.items():
                date = pd.Timestamp(str(idx))
                date_str = date.strftime("%Y-%m-%d")
                price = round(float(close), 4)
                if cache[ticker].get(date_str) != price:
                    cache[ticker][date_str] = price
                    updated = True
        except Exception as e:
            print(f"Error descargando histórico de {ticker}: {e}")

    if updated:
        save_price_cache(cache)
    return cache


def compute_portfolio_history(trades, dividend_entries, cashflow_history):
    """Valor de mercado y rentabilidad mensual usando precios históricos."""
    series_cf = cashflow_history.get("series", [])
    if not series_cf:
        return {"series": [], "benchmark": [], "cachedAt": None}

    first_date = cashflow_history["firstDate"]
    periods = [s["period"] for s in series_cf]
    holdings_by_period = replay_holdings_by_month(trades, periods)

    all_tickers = set()
    for holdings in holdings_by_period.values():
        all_tickers.update(holdings.keys())
    all_tickers.add("VOO")

    cache = fetch_historical_prices(list(all_tickers), first_date)
    voo_first_price = price_on_or_before(cache.get("VOO", {}), first_date)

    result_series = []
    benchmark = []
    for cf_point in series_cf:
        period = cf_point["period"]
        month_end = _month_end_date(period)
        holdings = holdings_by_period.get(period, {})

        market_value = 0.0
        for sym, qty in holdings.items():
            price = price_on_or_before(cache.get(sym, {}), month_end)
            if price is not None:
                market_value += qty * price

        net_inv = cf_point["netInvested"]
        cum_divs = cf_point["cumulativeDividends"]
        total_return_pct = None
        price_return_pct = None
        if net_inv > 0:
            total_return_pct = round(
                ((market_value + cum_divs - net_inv) / net_inv) * 100, 2
            )
            price_return_pct = round(((market_value - net_inv) / net_inv) * 100, 2)

        result_series.append(
            {
                **cf_point,
                "marketValue": round(market_value, 2),
                "totalReturnPct": total_return_pct,
                "priceReturnPct": price_return_pct,
            }
        )

        voo_price = price_on_or_before(cache.get("VOO", {}), month_end)
        voo_return = None
        if voo_first_price and voo_price:
            voo_return = round(
                ((voo_price - voo_first_price) / voo_first_price) * 100, 2
            )
        benchmark.append({"period": period, "vooReturnPct": voo_return})

    return {
        "series": result_series,
        "benchmark": benchmark,
        "cachedAt": datetime.now().isoformat(timespec="seconds"),
    }


def fetch_prices(tickers):
    """Obtiene precios actuales de Yahoo Finance."""
    resultados = {}
    try:
        data = yf.download(
            tickers, period="1d", interval="1m", progress=False, auto_adjust=True
        )
        for ticker in tickers:
            try:
                if data is None:
                    raise ValueError("No data returned")

                close_data = data.get("Close")
                if close_data is None:
                    raise ValueError("Close data not available")

                if isinstance(close_data, pd.DataFrame):
                    if ticker in close_data.columns:
                        series = close_data[ticker]
                    elif len(close_data.columns) > 0:
                        first_column = close_data.columns[0]
                        series = close_data[first_column]
                    else:
                        raise ValueError("Close data has no columns")
                else:
                    series = close_data

                precio = float(series.dropna().iloc[-1])
                resultados[ticker] = round(precio, 4)
            except Exception:
                # fallback individual
                try:
                    t = yf.Ticker(ticker)
                    precio = t.fast_info["last_price"]
                    resultados[ticker] = round(float(precio), 4)
                except Exception:
                    pass
    except Exception as e:
        print(f"Error general descargando precios: {e}")
        # Fallback: intentar uno por uno
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                precio = t.fast_info["last_price"]
                resultados[ticker] = round(float(precio), 4)
            except Exception:
                pass
    return resultados


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    if data and data.get("password") == PASSCODE:
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"error": "Contraseña incorrecta"}), 401


@app.route("/")
def index():
    return send_from_directory(basedir, "portafolio-dashboard.html")


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_csv():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400
        file = request.files["file"]
        filename = (file.filename or "").strip()
        if not file or filename == "":
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400

        if not filename.lower().endswith(".csv"):
            return jsonify({"error": "Debe ser un archivo .csv"}), 400

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"U13493500.UPLOADED.{timestamp}.csv"
        filepath = os.path.join(DATA_DIR, filename)
        file.save(filepath)
        invalidate_price_cache()
        return jsonify({"success": True, "message": "Archivo subido correctamente"})
    except OSError as e:
        return jsonify({"error": f"No se pudo guardar el archivo: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al subir: {e}"}), 500


@app.route("/api/history")
@login_required
def history():
    """Histórico de valor de mercado y rentabilidad (carga bajo demanda)."""
    try:
        trades, dividend_entries = parse_csv()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    cashflow = compute_cashflow_history(trades, dividend_entries)
    try:
        result = compute_portfolio_history(trades, dividend_entries, cashflow)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Error calculando histórico: {e}"}), 500


@app.route("/api/portfolio")
@login_required
def portfolio():
    """Endpoint principal: parsea CSV, calcula holdings y dividendos, obtiene precios."""
    try:
        trades, dividend_entries = parse_csv()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    holdings = compute_holdings(trades)
    dividends = compute_dividends(dividend_entries)

    # Obtener precios actuales
    tickers = [h["ticker"] for h in holdings]
    prices = fetch_prices(tickers)

    # Encontrar la fecha de la primera compra general (para el footer)
    all_buy_dates = [t["date"] for t in trades if t["type"] == "Buy"]
    first_date = min(all_buy_dates) if all_buy_dates else None

    # Encontrar primera compra de VOO (para comparación vs S&P 500)
    voo_base = None
    for h in holdings:
        if h["ticker"] == "VOO":
            voo_base = h["firstBuyPrice"]
            break

    # Ordenar transacciones de más reciente a más antigua
    trades_sorted = sorted(trades, key=lambda t: t["date"], reverse=True)
    cashflow_history = compute_cashflow_history(trades, dividend_entries)

    return jsonify(
        {
            "holdings": holdings,
            "prices": prices,
            "dividends": dividends,
            "trades": trades_sorted,
            "vooBase": voo_base,
            "firstDate": first_date,
            "tickerNames": TICKER_NAMES,
            "cashflowHistory": cashflow_history,
        }
    )


@app.route("/precios")
def precios():
    try:
        trades, _ = parse_csv()
        holdings = compute_holdings(trades)
        tickers = [h["ticker"] for h in holdings]
    except Exception:
        tickers = [
            "VOO",
            "QQQ",
            "NVDA",
            "MSFT",
            "META",
            "GOOGL",
            "GLD",
            "XLE",
            "XLF",
            "XLI",
            "XLP",
        ]
    return jsonify(fetch_prices(tickers))


if __name__ == "__main__":
    # Verificar que existen CSVs al arrancar
    try:
        csv_files = find_csv_files()
        print(f"\n✓ Se encontraron {len(csv_files)} archivo(s) CSV de transacciones.")
        for f in csv_files:
            print(f"  - {os.path.basename(f)}")
    except FileNotFoundError as e:
        print(f"\n⚠ {e}")

    print("\n✓ Servidor iniciado. Accesible localmente en http://localhost:8080")
    print(
        "✓ Para otros dispositivos en tu Wi-Fi, usa tu dirección IP (ej: http://192.168.1.X:8080)\n"
    )

    import threading
    import webbrowser

    # Abrir el navegador automáticamente con un ligero retraso para asegurar que el servidor esté listo
    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:8080")).start()

    app.run(host="0.0.0.0", port=8080, debug=False)
