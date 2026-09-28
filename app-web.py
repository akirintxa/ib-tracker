"""
Punto de entrada para PythonAnywhere.

Toda la lógica vive en app.py; este archivo solo fija el modo "web"
(proxy de PythonAnywhere, precio a costo si Yahoo falla) y expone `app`
para que el archivo WSGI existente siga funcionando sin cambios.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("IB_TRACKER_MODE", "web")

from app import app  # noqa: E402

application = app

if __name__ == "__main__":
    app.run()
