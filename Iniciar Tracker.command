#!/bin/bash
# Este script levanta el servidor de IB Tracker y abre el navegador
cd "$(dirname "$0")"

echo "======================================"
echo "    INICIANDO IB PORTFOLIO TRACKER    "
echo "======================================"
echo "Cargando datos y levantando servidor..."
echo "(No cierres esta ventana negra mientras uses la aplicación)"
echo ""

./venv/bin/python app.py
