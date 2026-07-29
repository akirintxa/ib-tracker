#!/usr/bin/env python3
"""Test script to verify CSV parsing logic without Flask/yfinance dependencies."""
import csv
import glob
import os
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import datetime

basedir = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(basedir, "data")
os.makedirs(DATA_DIR, exist_ok=True)

TICKER_NAMES = {
    'VOO': 'Vanguard S&P 500', 'QQQ': 'Invesco QQQ', 'NVDA': 'NVIDIA',
    'MSFT': 'Microsoft', 'META': 'Meta Platforms', 'GOOGL': 'Alphabet',
    'GLD': 'SPDR Gold', 'XLE': 'Energy SPDR', 'XLF': 'Financial SPDR',
    'XLI': 'Industrial SPDR', 'XLP': 'Cons. Staples SPDR', 'RGTI': 'Rigetti Computing',
}

def find_csv_files():
    pattern = os.path.join(DATA_DIR, 'U13493500*.csv')
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No CSV found matching U13493500*.csv in {DATA_DIR}")
    return files

def parse_csv():
    csv_paths = find_csv_files()
    trades, dividends = [], []
    seen_rows = set()
    for csv_path in csv_paths:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                row_tuple = tuple(row)
                if row_tuple in seen_rows:
                    continue
                if len(row) < 3 or row[0] != 'Transaction History' or row[1] != 'Data':
                    continue
                seen_rows.add(row_tuple)

                date_str = row[2].strip()
                tx_type = row[5].strip()
                symbol = row[6].strip()
                qty_str = row[7].strip()
                price_str = row[8].strip()
                gross_str = row[10].strip()
                commission_str = row[11].strip()
                net_str = row[12].strip()

                if tx_type in ('Buy', 'Sell'):
                    try:
                        trades.append({'date': date_str, 'symbol': symbol, 'type': tx_type,
                            'qty': float(qty_str), 'price': float(price_str),
                            'gross': float(gross_str), 'commission': float(commission_str),
                            'net': float(net_str)})
                    except (ValueError, IndexError):
                        continue
                elif tx_type == 'Dividend':
                    try:
                        dividends.append({'date': date_str, 'symbol': symbol, 'type': 'dividend', 'amount': float(net_str)})
                    except (ValueError, IndexError):
                        continue
                elif tx_type == 'Foreign Tax Withholding':
                    try:
                        dividends.append({'date': date_str, 'symbol': symbol, 'type': 'tax', 'amount': float(net_str)})
                    except (ValueError, IndexError):
                        continue
    return trades, dividends

def compute_holdings(trades):
    buys = defaultdict(lambda: {'total_cost': 0.0, 'total_qty': 0.0})
    sells = defaultdict(lambda: {'total_proceeds': 0.0, 'total_qty': 0.0})
    first_buy_price = {}
    sorted_trades = sorted(trades, key=lambda t: t['date'])
    for trade in sorted_trades:
        sym = trade['symbol']
        if trade['type'] == 'Buy':
            cost = abs(trade['net'])
            buys[sym]['total_cost'] += cost
            buys[sym]['total_qty'] += trade['qty']
            if sym not in first_buy_price:
                first_buy_price[sym] = trade['price']
        elif trade['type'] == 'Sell':
            sells[sym]['total_proceeds'] += trade['net']
            sells[sym]['total_qty'] += abs(trade['qty'])
    holdings = []
    for sym in buys:
        buy_qty = buys[sym]['total_qty']
        sell_qty = sells[sym]['total_qty'] if sym in sells else 0.0
        net_qty = buy_qty - sell_qty
        if net_qty < 0.0001:
            print(f"  [EXCLUDED] {sym}: net qty = {net_qty:.4f} (closed position)")
            continue
        avg_price = buys[sym]['total_cost'] / buys[sym]['total_qty']
        holdings.append({'ticker': sym, 'name': TICKER_NAMES.get(sym, sym),
            'qty': round(net_qty, 4), 'avgPrice': round(avg_price, 4),
            'totalCost': round(avg_price * net_qty, 2),
            'firstBuyPrice': first_buy_price.get(sym, 0)})
    return holdings

def compute_dividends(entries):
    by_ticker = defaultdict(lambda: {'gross': 0.0, 'tax': 0.0})
    by_quarter = defaultdict(lambda: {'gross': 0.0, 'tax': 0.0})
    for entry in entries:
        sym = entry['symbol']
        try:
            dt = datetime.strptime(entry['date'], '%Y-%m-%d')
            q = (dt.month - 1) // 3 + 1
            ql = f"{dt.year}-Q{q}"
        except ValueError:
            continue
        if entry['type'] == 'dividend':
            by_ticker[sym]['gross'] += entry['amount']
            by_quarter[ql]['gross'] += entry['amount']
        elif entry['type'] == 'tax':
            by_ticker[sym]['tax'] += abs(entry['amount'])
            by_quarter[ql]['tax'] += abs(entry['amount'])
    total_gross = sum(v['gross'] for v in by_ticker.values())
    total_tax = sum(v['tax'] for v in by_ticker.values())
    return by_ticker, by_quarter, total_gross, total_tax


def _month_key(date_str):
    return date_str[:7]


def _iter_months(start_date_str, end_date=None):
    start = datetime.strptime(start_date_str, '%Y-%m-%d')
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


def compute_cashflow_history(trades, dividend_entries):
    buy_dates = [t['date'] for t in trades if t['type'] == 'Buy']
    if not buy_dates:
        return {'granularity': 'monthly', 'series': [], 'firstDate': None,
                'totals': {'netInvested': 0, 'cumulativeDividends': 0}}
    first_date = min(buy_dates)
    months = _iter_months(first_date)
    monthly_buys, monthly_sells, monthly_div_net = defaultdict(float), defaultdict(float), defaultdict(float)
    for t in trades:
        mk = _month_key(t['date'])
        if t['type'] == 'Buy':
            monthly_buys[mk] += abs(t['net'])
        elif t['type'] == 'Sell':
            monthly_sells[mk] += t['net']
    for e in dividend_entries:
        monthly_div_net[_month_key(e['date'])] += e['amount']
    cum_invested = cum_divs = 0.0
    series = []
    for period in months:
        contributions = monthly_buys[period] - monthly_sells[period]
        cum_invested += contributions
        month_divs = monthly_div_net[period]
        cum_divs += month_divs
        series.append({
            'period': period, 'netInvested': round(cum_invested, 2),
            'cumulativeDividends': round(cum_divs, 2),
            'monthlyDividends': round(month_divs, 2),
            'monthlyContributions': round(contributions, 2),
        })
    return {'granularity': 'monthly', 'series': series, 'firstDate': first_date,
            'totals': {'netInvested': round(cum_invested, 2), 'cumulativeDividends': round(cum_divs, 2)}}


def _month_end_date(period):
    year, month = map(int, period.split('-'))
    last_day = monthrange(year, month)[1]
    month_end = f"{year}-{month:02d}-{last_day:02d}"
    today = datetime.today().strftime('%Y-%m-%d')
    return month_end if month_end <= today else today


def replay_holdings_by_month(trades, periods):
    sorted_trades = sorted(trades, key=lambda t: t['date'])
    holdings, result, trade_idx = defaultdict(float), {}, 0
    for period in periods:
        month_end = _month_end_date(period)
        while trade_idx < len(sorted_trades) and sorted_trades[trade_idx]['date'] <= month_end:
            t = sorted_trades[trade_idx]
            if t['type'] == 'Buy':
                holdings[t['symbol']] += t['qty']
            elif t['type'] == 'Sell':
                holdings[t['symbol']] -= abs(t['qty'])
            trade_idx += 1
        result[period] = {s: round(q, 4) for s, q in holdings.items() if q >= 0.0001}
    return result


def test_cashflow_history_synthetic():
    trades = [
        {'date': '2024-01-10', 'symbol': 'VOO', 'type': 'Buy', 'qty': 10, 'net': -1000},
        {'date': '2024-02-15', 'symbol': 'VOO', 'type': 'Buy', 'qty': 5, 'net': -500},
        {'date': '2024-03-20', 'symbol': 'VOO', 'type': 'Sell', 'qty': 3, 'net': 350},
    ]
    dividends = [
        {'date': '2024-02-01', 'symbol': 'VOO', 'type': 'dividend', 'amount': 20},
        {'date': '2024-02-01', 'symbol': 'VOO', 'type': 'tax', 'amount': -3},
    ]
    hist = compute_cashflow_history(trades, dividends)
    assert hist['firstDate'] == '2024-01-10'
    jan = next(s for s in hist['series'] if s['period'] == '2024-01')
    feb = next(s for s in hist['series'] if s['period'] == '2024-02')
    mar = next(s for s in hist['series'] if s['period'] == '2024-03')
    assert jan['netInvested'] == 1000
    assert jan['monthlyContributions'] == 1000
    assert feb['netInvested'] == 1500
    assert feb['cumulativeDividends'] == 17
    assert feb['monthlyDividends'] == 17
    assert mar['netInvested'] == 1150
    assert mar['monthlyContributions'] == -350
    print("  [OK] test_cashflow_history_synthetic")


def test_replay_holdings_synthetic():
    trades = [
        {'date': '2024-01-10', 'symbol': 'VOO', 'type': 'Buy', 'qty': 10, 'net': -1000},
        {'date': '2024-03-20', 'symbol': 'VOO', 'type': 'Sell', 'qty': 3, 'net': 350},
    ]
    periods = ['2024-01', '2024-02', '2024-03']
    holdings = replay_holdings_by_month(trades, periods)
    assert holdings['2024-01']['VOO'] == 10
    assert holdings['2024-02']['VOO'] == 10
    assert holdings['2024-03']['VOO'] == 7
    print("  [OK] test_replay_holdings_synthetic")


def test_market_value_calculation():
    """Verifica la fórmula de rentabilidad con datos ficticios."""
    net_inv, market, divs = 1000, 1200, 50
    total_return = round(((market + divs - net_inv) / net_inv) * 100, 2)
    assert total_return == 25.0
    print("  [OK] test_market_value_calculation")


# Run
print("=" * 60)
print("IB Portfolio Tracker — CSV Parsing Test")
print("=" * 60)

print("\n--- UNIT TESTS (synthetic) ---")
try:
    test_cashflow_history_synthetic()
    test_replay_holdings_synthetic()
    test_market_value_calculation()
except AssertionError as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

try:
    csv_files = find_csv_files()
except FileNotFoundError:
    print("\n(No CSV files in data/ — skipping live data tests)")
    sys.exit(0)
print(f"\nArchivos encontrados: {len(csv_files)}")
for f in csv_files:
    print(f" - {os.path.basename(f)}")

trades, div_entries = parse_csv()
print(f"Trades found: {len(trades)}")
print(f"Dividend entries found: {len(div_entries)}")

print("\n--- HOLDINGS (with commissions in cost basis) ---")
holdings = compute_holdings(trades)
for h in sorted(holdings, key=lambda x: x['totalCost'], reverse=True):
    print(f"  {h['ticker']:6s}  qty={h['qty']:10.4f}  avgPrice=${h['avgPrice']:8.4f}  cost=${h['totalCost']:10.2f}  firstBuy=${h['firstBuyPrice']}")

print(f"\n  Total positions: {len(holdings)}")
total_cost = sum(h['totalCost'] for h in holdings)
print(f"  Total capital invested: ${total_cost:,.2f}")

print("\n--- DIVIDENDS BY TICKER ---")
by_ticker, by_quarter, total_g, total_t = compute_dividends(div_entries)
for sym in sorted(by_ticker, key=lambda s: by_ticker[s]['gross'] - by_ticker[s]['tax'], reverse=True):
    v = by_ticker[sym]
    net = v['gross'] - v['tax']
    print(f"  {sym:6s}  gross=${v['gross']:7.2f}  tax=${v['tax']:6.2f}  net=${net:7.2f}")
print(f"\n  Total: gross=${total_g:.2f}  tax=${total_t:.2f}  net=${total_g - total_t:.2f}")

print("\n--- DIVIDENDS BY QUARTER ---")
for q in sorted(by_quarter):
    v = by_quarter[q]
    net = v['gross'] - v['tax']
    print(f"  {q}  gross=${v['gross']:7.2f}  tax=${v['tax']:6.2f}  net=${net:7.2f}")

# Verify VOO specifically
print("\n--- VOO VERIFICATION ---")
voo_trades = [t for t in trades if t['symbol'] == 'VOO' and t['type'] == 'Buy']
print(f"  VOO buys: {len(voo_trades)}")
voo_total_qty = sum(t['qty'] for t in voo_trades)
voo_total_cost = sum(abs(t['net']) for t in voo_trades)
print(f"  Total qty: {voo_total_qty:.4f}")
print(f"  Total cost (incl commissions): ${voo_total_cost:.2f}")
print(f"  Avg price: ${voo_total_cost/voo_total_qty:.4f}")
