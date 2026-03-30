"""
Voxa — WSGI Dispatcher v3.0
============================
Architecture :
  /           → app_router   (landing + auth + demo + API)
  /psg/       → dashboard    (PSG Dash dédié)
  /betclic/   → dashboard_betclic (Betclic Dash dédié)
  /{slug}/    → dashboard_generic (généré automatiquement)

PythonAnywhere WSGI :
    from wsgi import application
"""

import json
from pathlib import Path
from werkzeug.middleware.dispatcher import DispatcherMiddleware

BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_DIR = BASE_DIR / "configs"

# Landing + auth + demo + API
from app_router import server as landing_server

# Dashboards dédiés
from dashboard         import server as psg_server
from dashboard_betclic import server as betclic_server

# Dashboard générique factory
from dashboard_generic import make_dashboard

STATIC_ROUTES = {
    "/psg":     psg_server,
    "/betclic": betclic_server,
}
DEDICATED = {"psg", "betclic"}

def _load_generic_routes():
    routes = {}
    if not CONFIG_DIR.exists():
        return routes
    for config_path in sorted(CONFIG_DIR.glob("*.json")):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            slug = cfg.get("slug", config_path.stem)
            if slug in DEDICATED:
                continue
            if not (BASE_DIR / f"voxa_{slug}.db").exists():
                continue
            app = make_dashboard(slug)
            routes[f"/{slug}"] = app.server
            print(f"  ✓ /{slug}/ → {cfg.get('client_name', slug)}")
        except Exception as e:
            print(f"  ⚠ {config_path.name} ignoré : {e}")
    return routes

generic_routes = _load_generic_routes()

application = DispatcherMiddleware(landing_server, {
    **STATIC_ROUTES,
    **generic_routes,
})