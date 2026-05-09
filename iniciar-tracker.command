#!/bin/bash
# Script para iniciar el tracker y el acceso remoto simultáneamente
cd "$(dirname "$0")"

# Título de la ventana de Terminal (macOS)
echo -n -e "\033]0;IB Tracker + Acceso Remoto\007"

echo "=================================================="
echo "    INICIANDO IB TRACKER + ACCESO REMOTO          "
echo "=================================================="

# Función para limpiar procesos al salir
cleanup() {
    echo ""
    echo ">>> Cerrando servidor y limpiando..."
    kill $PYTHON_PID 2>/dev/null
    exit
}

# Capturar señales de salida para cerrar el proceso de Python
trap cleanup SIGINT SIGTERM EXIT

echo ">>> 1. Iniciando servidor backend..."
./venv/bin/python app.py &
PYTHON_PID=$!

# Esperar un poco para que el servidor arranque y no se mezcle tanto el output
sleep 3

echo ""
echo ">>> 2. Configurando acceso remoto (Serveo)..."
echo "La URL pública aparecerá abajo (ej: https://xxxx.serveo.net)"
echo "--------------------------------------------------"
echo "CONSEJO: Si no aparece una URL, presiona Enter o verifica tu conexión."
echo "--------------------------------------------------"

# Ejecutar SSH en primer plano para que el usuario vea la URL de Serveo
ssh -R 80:localhost:8080 serveo.net
