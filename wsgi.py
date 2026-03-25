"""
Voxa — WSGI Dispatcher v2.0
Monte les 3 apps Dash sur une seule URL via DispatcherMiddleware.

    /           → app_router   (landing page)
    /psg/...    → dashboard    (PSG)
    /betclic/...→ dashboard_betclic (Betclic)

PythonAnywhere WSGI :
    from wsgi import application
"""

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app_router import server as landing_server
from dashboard import server as psg_server
from dashboard_betclic import server as betclic_server

# Chaque app a son propre Flask server.
# DispatcherMiddleware route selon le préfixe URL :
#   requête /psg/xxx → strip /psg → forward /xxx à psg_server
#   requête /betclic/xxx → strip /betclic → forward /xxx à betclic_server
#   tout le reste → landing_server

application = DispatcherMiddleware(landing_server, {
    "/psg":     psg_server,
    "/betclic": betclic_server,
})