import csv
import glob
import json
import os
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from functools import wraps

import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS

# Configuración de entorno para el Proxy de PythonAnywhere
os.environ["HTTP_PROXY"] = "http://proxy.server:3128"
os.environ["HTTPS_PROXY"] = "http://proxy.server:3128"

basedir = "/home/akirintxa/ib-tracker"
app = Flask(__name__, static_folder=basedir, static_url_path="")
app.secret_key = "tu_llave_secreta_aqui"
CORS(app)

PASSWORD = "akira"

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


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)

    return decorated_function


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if data and data.get("password") == PASSWORD:
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401


@app.route("/")
def index():
    return send_from_directory(basedir, "portafolio-dashboard.html")


DATA_DIR = os.path.join(basedir, "data")
os.makedirs(DATA_DIR, exist_ok=True)
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.json")


def parse_csv():
    files = glob.glob(os.path.join(DATA_DIR, "U13493500*.csv"))
    trades, dividends, seen = [], [], set()
    for f_path in files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if (
                        tuple(row) in seen
                        or len(row) < 13
                        or row[0] != "Transaction History"
                        or row[1] != "Data"
                    ):
                        continue
                    seen.add(tuple(row))
                    dt, tx_type, sym, q, p, net, desc = (
                        row[2],
                        row[5],
                        row[6].strip(),
                        row[7],
                        row[8],
                        row[12],
                        row[4],
                    )
                    if tx_type in ("Buy", "Sell"):
                        trades.append(
                            {
                                "date": dt,
                                "symbol": sym,
                                "type": tx_type,
                                "qty": float(q),
                                "price": float(p),
                                "net": float(net),
                            }
                        )
                    elif tx_type == "Dividend":
                        dividends.append(
                            {
                                "date": dt,
                                "symbol": sym,
                                "type": "dividend",
                                "amount": float(net),
                                "description": desc,
                            }
                        )
                    elif tx_type == "Foreign Tax Withholding":
                        dividends.append(
                            {
                                "date": dt,
                                "symbol": sym,
                                "type": "tax",
                                "amount": float(net),
                                "description": desc,
                            }
                        )
        except Exception:
            continue
    return trades, dividends


def compute_dividends_data(entries):
    bt, bq = (
        defaultdict(lambda: {"g": 0.0, "t": 0.0}),
        defaultdict(lambda: {"g": 0.0, "t": 0.0}),
    )
    for e in entries:
        s, d, amt = e["symbol"], e["date"], e["amount"]
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            ql = f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
        except Exception:
            continue
        if e["type"] == "dividend":
            bt[s]["g"] += amt
            bq[ql]["g"] += amt
        else:
            bt[s]["t"] += abs(amt)
            bq[ql]["t"] += abs(amt)
    ticker_list = []
    for s in bt:
        ticker_list.append(
            {
                "ticker": s,
                "name": TICKER_NAMES.get(s, s),
                "net": round(bt[s]["g"] - bt[s]["t"], 2),
                "gross": round(bt[s]["g"], 2),
                "tax": round(bt[s]["t"], 2),
            }
        )
    return {
        "byTicker": ticker_list,
        "byQuarter": [
            {
                "quarter": q,
                "net": round(bq[q]["g"] - bq[q]["t"], 2),
                "gross": round(bq[q]["g"], 2),
                "tax": round(bq[q]["t"], 2),
            }
            for q in sorted(bq.keys())
        ],
        "totalNet": round(sum(v["g"] - v["t"] for v in bt.values()), 2),
        "totalGross": round(sum(v["g"] for v in bt.values()), 2),
        "totalTax": round(sum(v["t"] for v in bt.values()), 2),
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
    monthly_buys, monthly_sells, monthly_div_net = (
        defaultdict(float),
        defaultdict(float),
        defaultdict(float),
    )
    for t in trades:
        mk = _month_key(t["date"])
        if t["type"] == "Buy":
            monthly_buys[mk] += abs(t["net"])
        elif t["type"] == "Sell":
            monthly_sells[mk] += t["net"]
    for e in dividend_entries:
        monthly_div_net[_month_key(e["date"])] += e["amount"]
    cum_invested = cum_divs = 0.0
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
    sorted_trades = sorted(trades, key=lambda t: t["date"])
    holdings, result, trade_idx = defaultdict(float), {}, 0
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
        result[period] = {s: round(q, 4) for s, q in holdings.items() if q >= 0.0001}
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
            if data is None or data.empty:
                continue
            closes = data["Close"]
            if not hasattr(closes, "items"):
                continue
            if hasattr(closes, "dropna"):
                closes = closes.dropna()
            for idx, close in closes.items():
                if isinstance(idx, datetime):
                    date_str = idx.strftime("%Y-%m-%d")
                else:
                    date_str = str(idx)[:10]
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
    series_cf = cashflow_history.get("series", [])
    if not series_cf:
        return {"series": [], "benchmark": [], "cachedAt": None}
    first_date = cashflow_history["firstDate"]
    periods = [s["period"] for s in series_cf]
    holdings_by_period = replay_holdings_by_month(trades, periods)
    all_tickers = set()
    for h in holdings_by_period.values():
        all_tickers.update(h.keys())
    all_tickers.add("VOO")
    cache = fetch_historical_prices(list(all_tickers), first_date)
    voo_first_price = price_on_or_before(cache.get("VOO", {}), first_date)
    result_series, benchmark = [], []
    for cf_point in series_cf:
        period = cf_point["period"]
        month_end = _month_end_date(period)
        holdings = holdings_by_period.get(period, {})
        market_value = sum(
            qty * price_on_or_before(cache.get(sym, {}), month_end)
            for sym, qty in holdings.items()
            if price_on_or_before(cache.get(sym, {}), month_end) is not None
        )
        net_inv, cum_divs = cf_point["netInvested"], cf_point["cumulativeDividends"]
        total_return_pct = price_return_pct = None
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


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_csv():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400
        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400
        filename = file.filename or ""
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
    try:
        trades, div_raw = parse_csv()
    except Exception as e:
        return jsonify({"error": str(e)}), 404
    cashflow = compute_cashflow_history(trades, div_raw)
    try:
        return jsonify(compute_portfolio_history(trades, div_raw, cashflow))
    except Exception as e:
        return jsonify({"error": f"Error calculando histórico: {e}"}), 500


@app.route("/api/portfolio")
@login_required
def portfolio():
    try:
        trades, div_raw = parse_csv()
        if not trades:
            return jsonify({"error": "No hay datos"}), 404
        buys_cost, buys_qty, sells_qty, first_p = (
            defaultdict(float),
            defaultdict(float),
            defaultdict(float),
            {},
        )
        for t in sorted(trades, key=lambda x: x["date"]):
            s = t["symbol"]
            if t["type"] == "Buy":
                buys_cost[s] += abs(t["net"])
                buys_qty[s] += t["qty"]
                if s not in first_p:
                    first_p[s] = t["price"]
            elif t["type"] == "Sell":
                sells_qty[s] += abs(t["qty"])
        holdings, tickers_to_fetch = [], []
        for s in buys_qty:
            nq = buys_qty[s] - sells_qty[s]
            if nq < 0.0001:
                continue
            avg = buys_cost[s] / buys_qty[s] if buys_qty[s] > 0 else 0
            holdings.append(
                {
                    "ticker": s,
                    "name": TICKER_NAMES.get(s, s),
                    "qty": round(nq, 4),
                    "avgPrice": round(avg, 4),
                    "totalCost": round(avg * nq, 2),
                    "firstBuyPrice": first_p.get(s, 0),
                }
            )
            tickers_to_fetch.append(s)
        prices = {}
        if tickers_to_fetch:
            try:
                data = yf.download(
                    tickers_to_fetch, period="1d", progress=False, auto_adjust=True
                )
                if data is None or "Close" not in data:
                    raise ValueError("Failed to fetch price data")
                close_data = data["Close"]
                for s in tickers_to_fetch:
                    try:
                        val = (
                            close_data.iloc[-1]
                            if len(tickers_to_fetch) == 1
                            else close_data[s].dropna().iloc[-1]
                        )
                        prices[s] = round(float(val), 4)
                    except Exception:
                        prices[s] = next(
                            (h["avgPrice"] for h in holdings if h["ticker"] == s), 0
                        )
            except Exception:
                for s in tickers_to_fetch:
                    prices[s] = next(
                        (h["avgPrice"] for h in holdings if h["ticker"] == s), 0
                    )
        cashflow_history = compute_cashflow_history(trades, div_raw)
        return jsonify(
            {
                "holdings": holdings,
                "prices": prices,
                "dividends": compute_dividends_data(div_raw),
                "trades": sorted(trades, key=lambda x: x["date"], reverse=True),
                "vooBase": next(
                    (h["firstBuyPrice"] for h in holdings if h["ticker"] == "VOO"), None
                ),
                "firstDate": min(
                    (t["date"] for t in trades if t["type"] == "Buy"), default=None
                ),
                "tickerNames": TICKER_NAMES,
                "cashflowHistory": cashflow_history,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run()
