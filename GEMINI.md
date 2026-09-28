# Gemini Context: IB Tracker

Este proyecto es un **Interactive Brokers (IB) Portfolio Tracker**, una aplicación web diseñada para visualizar y analizar el rendimiento de un portafolio de inversiones a partir de los reportes de transacciones exportados por Interactive Brokers.

## 🚀 Descripción General

La aplicación parsea dinámicamente archivos CSV de transacciones de IB, calcula las posiciones actuales (holdings), el costo promedio de compra (incluyendo comisiones), el historial de dividendos y un historial completo de operaciones. Utiliza Yahoo Finance para obtener precios en tiempo real y ofrece un dashboard interactivo con comparativas contra el S&P 500.

### Tecnologías Principales
- **Backend:** Python con Flask, Pandas, yfinance.
- **Frontend:** HTML5, Vanilla CSS, JavaScript (ES6+), Chart.js 4.
- **Datos:** Gestión de múltiples archivos CSV con deduplicación de transacciones.

---

## 📂 Estructura del Proyecto

- `app.py`: Único servidor Flask, para uso local y web. Maneja las rutas de la API, el parsing de múltiples CSVs, la obtención de precios y la subida de archivos. Las diferencias entre despliegues se controlan por variables de entorno (ver "Modo local y web").
- `app-web.py`: Punto de entrada para PythonAnywhere. Solo fija `IB_TRACKER_MODE=web` e importa `app` desde `app.py`.
- `data/`: Directorio donde se almacenan todos los archivos CSV de transacciones (`U13493500*.csv`).
- `portafolio-dashboard.html`: UI del dashboard (SPA) con pestañas para Posiciones, Comparativa vs S&P 500, Dividendos y Transacciones.
- `dashboard.js`: Lógica del frontend (fetch de datos, renderizado de gráficos y gestión de subida de archivos).
- `test_parsing.py`: Script de utilidad para probar la lógica de parsing de forma aislada.
- `requirements.txt`: Dependencias de Python.

---

## 🛠️ Configuración y Ejecución

### Instalación
```bash
pip install -r requirements.txt
```

### Credenciales
La contraseña y la llave de sesión se leen de variables de entorno, no del código:
- `IB_TRACKER_PASSWORD` (obligatoria): contraseña del dashboard.
- `IB_TRACKER_SECRET_KEY` (recomendada): llave para firmar la cookie de sesión; si falta, se genera una al azar en cada arranque.
- `IB_TRACKER_SESSION_MINUTES` (opcional, 30 por defecto): minutos de inactividad antes de que la sesión expire. El botón "Salir" cierra la sesión al instante.

Localmente, copia `.env.example` a `.env` y complétalo; `iniciar-tracker.command` lo carga solo. En PythonAnywhere, defínelas con `os.environ[...]` en el archivo WSGI antes de importar la app.

Solo se sirven `portafolio-dashboard.html`, `dashboard.js`, `login_helper.js` y `favicon.svg`; la carpeta `data/` y el código fuente no son accesibles por HTTP.

### Modo local y web
`app.py` funciona igual en tu equipo y en PythonAnywhere; lo que cambia se ajusta con variables de entorno:

| Variable | Uso | Por defecto |
|---|---|---|
| `IB_TRACKER_MODE` | `local` o `web` | `web` si existe `PYTHONANYWHERE_DOMAIN`, si no `local` |
| `IB_TRACKER_PROXY` | Proxy saliente para Yahoo Finance | `http://proxy.server:3128` en web, ninguno en local |
| `IB_TRACKER_PRICE_FALLBACK` | Si Yahoo no da precio, mostrar la posición a costo promedio | `1` en web, `0` en local |
| `IB_TRACKER_PORT` | Puerto en modo local | `8080` |
| `IB_TRACKER_BASEDIR` | Carpeta del proyecto (y de `data/`) | carpeta de `app.py` |

### Ejecución
1. El servidor se inicia con:
   ```bash
   python app.py
   ```
   *Alternativa rápida:* Haz doble clic en `iniciar-tracker.command`.
2. **Automatización:** El servidor abrirá automáticamente el navegador en `http://localhost:8080`.
3. **Acceso Remoto (Local):** El servidor escucha en `0.0.0.0`, permitiendo el acceso desde otros dispositivos en la misma red Wi-Fi usando la IP local del equipo.

### Gestión de Datos
- **Subida:** Puedes subir nuevos archivos CSV directamente desde el dashboard usando el botón "Subir CSV". Los archivos se guardan en la carpeta `data/` con un timestamp.
- **Procesamiento:** El sistema lee *todos* los CSVs en la carpeta `data/`, combinando las transacciones y eliminando duplicados automáticamente.

### Acceso Remoto (Fuera de casa - TODO EN UNO)
Para iniciar el tracker y habilitar el acceso remoto al mismo tiempo:
1. Ejecuta `iniciar-tracker.command`.
2. El terminal mostrará una dirección similar a `https://algo.serveo.net`. Esa es la URL que puedes abrir desde cualquier lugar.
3. Al cerrar la ventana del terminal, tanto el servidor como el túnel se detendrán automáticamente.

---

## 📝 Convenciones de Desarrollo

- **Deduplicación:** Se utiliza un set de tuplas (`seen_rows`) en el backend para evitar procesar la misma transacción múltiples veces si se suben reportes que se solapan en fechas.
- **Transacciones:** El endpoint `/api/portfolio` devuelve el historial completo de compras y ventas ordenado por fecha descendente.
- **UX:** El dashboard incluye estados de carga (spinners) para la obtención de precios y la subida de archivos.
- **Localización:** Formateo de moneda y números adaptado a `es-VE` para la visualización.

---

## 📌 Notas de Contexto para Gemini

- La lógica de negocio principal reside en las funciones `parse_csv`, `compute_holdings` y `compute_dividends` de `app.py`, compartidas por los modos local y web.
- Al añadir nuevos tickers, actualiza la constante `TICKER_NAMES` en `app.py` para que aparezcan con su nombre completo en el dashboard.
- Solo se sirven como estáticos `portafolio-dashboard.html` y los archivos de `FRONTEND_FILES` en `app.py`; la carpeta `data/` y el código no son accesibles por HTTP.
