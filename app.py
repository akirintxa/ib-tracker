from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import yfinance as yf
import csv
import glob
import os
from collections import defaultdict
from datetime import datetime

# Forzar la ruta al directorio donde está el script
basedir = os.path.abspath(os.path.dirname(__file__))

# Crear subcarpeta data si no existe
DATA_DIR = os.path.join(basedir, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_folder=basedir, static_url_path='')
CORS(app)

# Nombres legibles para los tickers conocidos
TICKER_NAMES = {
    'VOO': 'Vanguard S&P 500',
    'QQQ': 'Invesco QQQ',
    'NVDA': 'NVIDIA',
    'MSFT': 'Microsoft',
    'META': 'Meta Platforms',
    'GOOGL': 'Alphabet',
    'GLD': 'SPDR Gold',
    'XLE': 'Energy SPDR',
    'XLF': 'Financial SPDR',
    'XLI': 'Industrial SPDR',
    'XLP': 'Cons. Staples SPDR',
    'RGTI': 'Rigetti Computing',
}


def find_csv_files():
    """Busca todos los archivos CSV del broker en el directorio data."""
    pattern = os.path.join(DATA_DIR, 'U13493500*.csv')
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
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                # Convertir la fila a tupla para poder meterla en el set
                row_tuple = tuple(row)
                if row_tuple in seen_rows:
                    continue
                
                if len(row) < 3 or row[0] != 'Transaction History':
                    continue
                if row[1] != 'Data':
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

                if tx_type in ('Buy', 'Sell'):
                    try:
                        trades.append({
                            'date': date_str,
                            'symbol': symbol,
                            'type': tx_type,
                            'qty': float(qty_str),
                            'price': float(price_str),
                            'gross': float(gross_str),
                            'commission': float(commission_str),
                            'net': float(net_str),
                        })
                    except (ValueError, IndexError):
                        continue

                elif tx_type == 'Dividend':
                    try:
                        dividends.append({
                            'date': date_str,
                            'symbol': symbol,
                            'type': 'dividend',
                            'amount': float(net_str),
                            'description': description,
                        })
                    except (ValueError, IndexError):
                        continue

                elif tx_type == 'Foreign Tax Withholding':
                    try:
                        dividends.append({
                            'date': date_str,
                            'symbol': symbol,
                            'type': 'tax',
                            'amount': float(net_str),  # negativo
                            'description': description,
                        })
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
    buys = defaultdict(lambda: {'total_cost': 0.0, 'total_qty': 0.0})
    sells = defaultdict(lambda: {'total_proceeds': 0.0, 'total_qty': 0.0})
    first_buy_price = {}  # Para VOO_BASE y similares

    # Ordenar por fecha para obtener primera compra correctamente
    sorted_trades = sorted(trades, key=lambda t: t['date'])

    for trade in sorted_trades:
        sym = trade['symbol']
        if trade['type'] == 'Buy':
            # Net amount para compras es negativo, tomamos valor absoluto
            cost = abs(trade['net'])
            buys[sym]['total_cost'] += cost
            buys[sym]['total_qty'] += trade['qty']
            if sym not in first_buy_price:
                first_buy_price[sym] = trade['price']
        elif trade['type'] == 'Sell':
            sells[sym]['total_proceeds'] += trade['net']  # positivo
            sells[sym]['total_qty'] += abs(trade['qty'])

    holdings = []
    for sym in buys:
        buy_qty = buys[sym]['total_qty']
        sell_qty = sells[sym]['total_qty'] if sym in sells else 0.0
        net_qty = buy_qty - sell_qty

        # Excluir posiciones cerradas (qty ≈ 0)
        if net_qty < 0.0001:
            continue

        # Precio promedio de compra (con comisiones incluidas)
        avg_price = buys[sym]['total_cost'] / buys[sym]['total_qty'] if buys[sym]['total_qty'] > 0 else 0
        total_cost = avg_price * net_qty

        holdings.append({
            'ticker': sym,
            'name': TICKER_NAMES.get(sym, sym),
            'qty': round(net_qty, 4),
            'avgPrice': round(avg_price, 4),
            'totalCost': round(total_cost, 2),
            'firstBuyPrice': first_buy_price.get(sym, 0),
        })

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
    by_ticker = defaultdict(lambda: {'gross': 0.0, 'tax': 0.0, 'net': 0.0})
    # Agrupar por trimestre
    by_quarter = defaultdict(lambda: {'gross': 0.0, 'tax': 0.0, 'net': 0.0})
    # Agrupar por (date, symbol) para emparejar dividendo + tax
    events = defaultdict(lambda: {'gross': 0.0, 'tax': 0.0})

    for entry in dividend_entries:
        sym = entry['symbol']
        date_str = entry['date']

        # Determinar trimestre
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            q = (dt.month - 1) // 3 + 1
            quarter_label = f"{dt.year}-Q{q}"
        except ValueError:
            continue

        if entry['type'] == 'dividend':
            amount = entry['amount']
            by_ticker[sym]['gross'] += amount
            by_quarter[quarter_label]['gross'] += amount
            events[(date_str, sym)]['gross'] += amount
        elif entry['type'] == 'tax':
            amount = abs(entry['amount'])
            by_ticker[sym]['tax'] += amount
            by_quarter[quarter_label]['tax'] += amount
            events[(date_str, sym)]['tax'] += amount

    # Calcular netos
    for sym in by_ticker:
        by_ticker[sym]['net'] = by_ticker[sym]['gross'] - by_ticker[sym]['tax']

    for q in by_quarter:
        by_quarter[q]['net'] = by_quarter[q]['gross'] - by_quarter[q]['tax']

    # Ordenar trimestres cronológicamente
    sorted_quarters = sorted(by_quarter.keys())
    quarters_list = []
    for q in sorted_quarters:
        quarters_list.append({
            'quarter': q,
            'gross': round(by_quarter[q]['gross'], 2),
            'tax': round(by_quarter[q]['tax'], 2),
            'net': round(by_quarter[q]['net'], 2),
        })

    # Construir detalle
    detail = []
    for (date_str, sym), vals in sorted(events.items()):
        detail.append({
            'date': date_str,
            'symbol': sym,
            'gross': round(vals['gross'], 2),
            'tax': round(vals['tax'], 2),
            'net': round(vals['gross'] - vals['tax'], 2),
        })

    # Totales
    total_gross = sum(v['gross'] for v in by_ticker.values())
    total_tax = sum(v['tax'] for v in by_ticker.values())
    total_net = total_gross - total_tax

    # Convertir by_ticker a lista
    ticker_list = []
    for sym in sorted(by_ticker.keys(), key=lambda s: by_ticker[s]['net'], reverse=True):
        ticker_list.append({
            'ticker': sym,
            'name': TICKER_NAMES.get(sym, sym),
            'gross': round(by_ticker[sym]['gross'], 2),
            'tax': round(by_ticker[sym]['tax'], 2),
            'net': round(by_ticker[sym]['net'], 2),
        })

    return {
        'byTicker': ticker_list,
        'byQuarter': quarters_list,
        'detail': detail,
        'totalGross': round(total_gross, 2),
        'totalTax': round(total_tax, 2),
        'totalNet': round(total_net, 2),
    }


def fetch_prices(tickers):
    """Obtiene precios actuales de Yahoo Finance."""
    resultados = {}
    try:
        data = yf.download(tickers, period="1d", interval="1m", progress=False, auto_adjust=True)
        for ticker in tickers:
            try:
                precio = float(data["Close"][ticker].dropna().iloc[-1])
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


@app.route("/")
def index():
    return send_from_directory(basedir, "portafolio-dashboard.html")


@app.route("/api/upload", methods=["POST"])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    if file and file.filename.endswith('.csv'):
        # Guardar en la carpeta data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"U13493500.UPLOADED.{timestamp}.csv"
        filepath = os.path.join(DATA_DIR, filename)
        file.save(filepath)
        return jsonify({'success': True, 'message': 'Archivo subido correctamente'})
    
    return jsonify({'error': 'Debe ser un archivo .csv'}), 400


@app.route("/api/portfolio")
def portfolio():
    """Endpoint principal: parsea CSV, calcula holdings y dividendos, obtiene precios."""
    try:
        trades, dividend_entries = parse_csv()
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    holdings = compute_holdings(trades)
    dividends = compute_dividends(dividend_entries)

    # Obtener precios actuales
    tickers = [h['ticker'] for h in holdings]
    prices = fetch_prices(tickers)

    # Encontrar la fecha de la primera compra general (para el footer)
    all_buy_dates = [t['date'] for t in trades if t['type'] == 'Buy']
    first_date = min(all_buy_dates) if all_buy_dates else None

    # Encontrar primera compra de VOO (para comparación vs S&P 500)
    voo_base = None
    for h in holdings:
        if h['ticker'] == 'VOO':
            voo_base = h['firstBuyPrice']
            break

    # Ordenar transacciones de más reciente a más antigua
    trades_sorted = sorted(trades, key=lambda t: t['date'], reverse=True)

    return jsonify({
        'holdings': holdings,
        'prices': prices,
        'dividends': dividends,
        'trades': trades_sorted,
        'vooBase': voo_base,
        'firstDate': first_date,
        'tickerNames': TICKER_NAMES,
    })


# Mantener endpoint legacy por compatibilidad
@app.route("/precios")
def precios():
    try:
        trades, _ = parse_csv()
        holdings = compute_holdings(trades)
        tickers = [h['ticker'] for h in holdings]
    except Exception:
        tickers = ["VOO", "QQQ", "NVDA", "MSFT", "META", "GOOGL", "GLD",
                    "XLE", "XLF", "XLI", "XLP"]
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

    print(f"\n✓ Servidor iniciado. Accesible localmente en http://localhost:8080")
    print(f"✓ Para otros dispositivos en tu Wi-Fi, usa tu dirección IP (ej: http://192.168.1.X:8080)\n")
    
    import threading
    import webbrowser
    # Abrir el navegador automáticamente con un ligero retraso para asegurar que el servidor esté listo
    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:8080")).start()

    app.run(host='0.0.0.0', port=8080, debug=False)
