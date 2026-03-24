"""
Voxa — WSGI Entry Point v1.0
Point d'entrée unique pour PythonAnywhere.

Importe les 3 apps Dash qui se montent toutes sur le même
serveur Flask partagé (server.py), chacune avec son propre
url_base_pathname :
    /           → app_router   (landing page sélection client)
    /psg/       → dashboard    (dashboard PSG)
    /betclic/   → dashboard_betclic (dashboard Betclic)

PythonAnywhere WSGI config :
    import sys, os
    from dotenv import load_dotenv
    sys.path.insert(0, '/home/lucsharper/Voxa')
    load_dotenv('/home/lucsharper/Voxa/.env')
    from wsgi import application
"""

# L'ordre d'import compte : app_router en premier (il est sur "/"),
# puis les dashboards qui se montent sur /psg/ et /betclic/.
# Chaque import enregistre les routes Dash sur le serveur partagé.

import app_router        # noqa: F401 — enregistre les routes /
import dashboard         # noqa: F401 — enregistre les routes /psg/*
import dashboard_betclic # noqa: F401 — enregistre les routes /betclic/*

# Le serveur Flask partagé, prêt pour WSGI
from server import server as application