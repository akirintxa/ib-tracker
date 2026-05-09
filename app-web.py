from flask import Flask, jsonify, send_from_directory, request, session, redirect, url_for
from flask_cors import CORS
import yfinance as yf
import csv
import glob
import os
from collections import defaultdict
from datetime import datetime
from functools import wraps

# Configuración de entorno para el Proxy de PythonAnywhere
os.environ['HTTP_PROXY'] = "http://proxy.server:3128"
os.environ['HTTPS_PROXY'] = "http://proxy.server:3128"

basedir = '/home/akirintxa/ib-tracker'
app = Flask(__name__, static_folder=basedir, static_url_path='')
app.secret_key = 'tu_llave_secreta_aqui'
CORS(app)

PASSWORD = "ib-tracker-secret"

TICKER_NAMES = {
    'VOO': 'Vanguard S&P 500', 'QQQ': 'Invesco QQQ', 'NVDA': 'NVIDIA',
    'MSFT': 'Microsoft', 'META': 'Meta Platforms', 'GOOGL': 'Alphabet',
    'GLD': 'SPDR Gold', 'XLE': 'Energy SPDR', 'XLF': 'Financial SPDR',
    'XLI': 'Industrial SPDR', 'XLP': 'Cons. Staples SPDR', 'RGTI': 'Rigetti Computing',
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'error': 'No autorizado'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if data and data.get("password") == PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False}), 401

@app.route("/")
def index():
    return send_from_directory(basedir, "portafolio-dashboard.html")

DATA_DIR = os.path.join(basedir, "data")

def parse_csv():
    files = glob.glob(os.path.join(DATA_DIR, 'U13493500*.csv'))
    trades, dividends, seen = [], [], set()
    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if tuple(row) in seen or len(row) < 13 or row[0] != 'Transaction History' or row[1] != 'Data':
                        continue
                    seen.add(tuple(row))
                    dt, tx_type, sym, q, p, net, desc = row[2], row[5], row[6].strip(), row[7], row[8], row[12], row[4]
                    if tx_type in ('Buy', 'Sell'):
                        trades.append({'date': dt, 'symbol': sym, 'type': tx_type, 'qty': float(q), 'price': float(p), 'net': float(net)})
                    elif tx_type == 'Dividend':
                        dividends.append({'date': dt, 'symbol': sym, 'type': 'dividend', 'amount': float(net), 'description': desc})
                    elif tx_type == 'Foreign Tax Withholding':
                        dividends.append({'date': dt, 'symbol': sym, 'type': 'tax', 'amount': float(net), 'description': desc})
        except: continue
    return trades, dividends

def compute_dividends_data(entries):
    bt, bq = defaultdict(lambda: {'g': 0.0, 't': 0.0}), defaultdict(lambda: {'g': 0.0, 't': 0.0})
    for e in entries:
        s, d, amt = e['symbol'], e['date'], e['amount']
        try:
            dt = datetime.strptime(d, '%Y-%m-%d')
            ql = f"{dt.year}-Q{(dt.month-1)//3+1}"
        except: continue
        if e['type'] == 'dividend':
            bt[s]['g'] += amt; bq[ql]['g'] += amt
        else:
            bt[s]['t'] += abs(amt); bq[ql]['t'] += abs(amt)
    ticker_list = []
    for s in bt:
        ticker_list.append({'ticker': s, 'name': TICKER_NAMES.get(s, s), 'net': round(bt[s]['g']-bt[s]['t'], 2), 'gross': round(bt[s]['g'], 2), 'tax': round(bt[s]['t'], 2)})
    return {
        'byTicker': ticker_list,
        'byQuarter': [{'quarter': q, 'net': round(bq[q]['g']-bq[q]['t'], 2), 'gross': round(bq[q]['g'], 2), 'tax': round(bq[q]['t'], 2)} for q in sorted(bq.keys())],
        'totalNet': round(sum(v['g']-v['t'] for v in bt.values()), 2),
        'totalGross': round(sum(v['g'] for v in bt.values()), 2),
        'totalTax': round(sum(v['t'] for v in bt.values()), 2)
    }

@app.route("/api/portfolio")
@login_required
def portfolio():
    try:
        trades, div_raw = parse_csv()
        if not trades: return jsonify({'error': 'No hay datos'}), 404
        buys_cost, buys_qty, sells_qty, first_p = defaultdict(float), defaultdict(float), defaultdict(float), {}
        for t in sorted(trades, key=lambda x: x['date']):
            s = t['symbol']
            if t['type'] == 'Buy':
                buys_cost[s] += abs(t['net']); buys_qty[s] += t['qty']
                if s not in first_p: first_p[s] = t['price']
            elif t['type'] == 'Sell':
                sells_qty[s] += abs(t['qty'])
        holdings, tickers_to_fetch = [], []
        for s in buys_qty:
            nq = buys_qty[s] - sells_qty[s]
            if nq < 0.0001: continue
            avg = buys_cost[s] / buys_qty[s] if buys_qty[s] > 0 else 0
            holdings.append({'ticker': s, 'name': TICKER_NAMES.get(s, s), 'qty': round(nq, 4), 'avgPrice': round(avg, 4), 'totalCost': round(avg * nq, 2), 'firstBuyPrice': first_p.get(s, 0)})
            tickers_to_fetch.append(s)
        prices = {}
        if tickers_to_fetch:
            try:
                data = yf.download(tickers_to_fetch, period="1d", progress=False, auto_adjust=True)
                for s in tickers_to_fetch:
                    try:
                        val = data['Close'].iloc[-1] if len(tickers_to_fetch) == 1 else data['Close'][s].dropna().iloc[-1]
                        prices[s] = round(float(val), 4)
                    except: prices[s] = next((h['avgPrice'] for h in holdings if h['ticker'] == s), 0)
            except:
                for s in tickers_to_fetch: prices[s] = next((h['avgPrice'] for h in holdings if h['ticker'] == s), 0)
        return jsonify({
            'holdings': holdings, 'prices': prices,
            'dividends': compute_dividends_data(div_raw),
            'trades': sorted(trades, key=lambda x: x['date'], reverse=True),
            'vooBase': next((h['firstBuyPrice'] for h in holdings if h['ticker'] == 'VOO'), None),
            'firstDate': min((t['date'] for t in trades if t['type'] == 'Buy'), default=None),
            'tickerNames': TICKER_NAMES
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run()