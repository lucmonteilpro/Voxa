"""
Voxa — WSGI Dispatcher v2.1
============================
Architecture :
  /           → app_router   (landing + auth + demo + API) — server partagé
  /psg/       → dashboard    (PSG Dash — server propre)
  /betclic/   → dashboard_betclic (Betclic Dash — server propre)

Pourquoi cette architecture :
  Dash 4.0 enregistre un blueprint Flask par app.
  Deux apps Dash ne peuvent PAS partager le même Flask server
  (conflit blueprint _dash_assets interne au routing DispatcherMiddleware).
  Solution : seule app_router partage server.py (landing + auth).
  Les dashboards métier gardent leur propre Flask server.

PythonAnywhere WSGI :
    from wsgi import application
"""

from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Landing + auth + demo + API → server.py partagé via app_router
from app_router import server as landing_server

# Dashboards métier → Flask servers propres
from dashboard         import server as psg_server
from dashboard_betclic import server as betclic_server

application = DispatcherMiddleware(landing_server, {
    "/psg":     psg_server,
    "/betclic": betclic_server,
})