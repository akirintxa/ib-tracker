#!/usr/bin/env python3
"""Test script to verify CSV parsing logic without Flask/yfinance dependencies."""
import csv
import glob
import os
import json
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

# Run
print("=" * 60)
print("IB Portfolio Tracker — CSV Parsing Test")
print("=" * 60)

csv_files = find_csv_files()
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
