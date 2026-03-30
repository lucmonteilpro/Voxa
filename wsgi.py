"""
Voxa — WSGI Dispatcher v4.0
============================
Architecture simplifiée — tout passe par dashboard_generic.

  /           → app_router   (landing + auth + demo + API)
  /{slug}/    → dashboard_generic (PSG, Betclic, Reims, etc.)

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

# Dashboard générique factory
from dashboard_generic import make_dashboard

import voxa_db as vdb


def _build_routes() -> dict:
    """Construit les routes pour tous les clients connus."""
    routes = {}

    # 1. Clients depuis voxa_db.CLIENTS_CONFIG (PSG, Betclic)
    for slug in vdb.CLIENTS_CONFIG:
        try:
            app = make_dashboard(slug)
            routes[f"/{slug}"] = app.server
            print(f"  ✓ /{slug}/ → {vdb.CLIENTS_CONFIG[slug]['name']}")
        except Exception as e:
            print(f"  ⚠ /{slug}/ erreur : {e}")

    # 2. Clients depuis configs/*.json (nouveaux clients)
    if CONFIG_DIR.exists():
        for config_path in sorted(CONFIG_DIR.glob("*.json")):
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                slug = cfg.get("slug", config_path.stem)
                if slug in routes or f"/{slug}" in routes:
                    continue  # déjà chargé via voxa_db
                db_path = BASE_DIR / f"voxa_{slug}.db"
                if not db_path.exists():
                    continue  # DB pas encore créée
                app = make_dashboard(slug)
                routes[f"/{slug}"] = app.server
                print(f"  ✓ /{slug}/ → {cfg.get('client_name', slug)}")
            except Exception as e:
                print(f"  ⚠ {config_path.name} ignoré : {e}")

    return routes


print("\n  VOXA — WSGI Dispatcher v4.0")
all_routes = _build_routes()
print(f"  {len(all_routes)} dashboard(s) chargé(s)\n")

application = DispatcherMiddleware(landing_server, all_routes)