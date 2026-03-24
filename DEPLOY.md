# Voxa — Guide de déploiement V2
## PythonAnywhere · Multi-dashboard unifié · Scheduler

---

## Architecture V2

```
Voxa/
├── server.py               # ← NOUVEAU : serveur Flask partagé
├── wsgi.py                 # ← NOUVEAU : point d'entrée WSGI unique
├── app_router.py           # Landing page multi-client (/)
├── dashboard.py            # Dashboard PSG (/psg/)
├── dashboard_betclic.py    # Dashboard Betclic (/betclic/)
├── tracker.py              # Tracker PSG (Claude API)
├── tracker_betclic.py      # Tracker Betclic (4 marchés)
├── email_reporter.py       # Envoi email automatique
├── voxa.db                 # Base PSG
├── voxa_betclic.db         # Base Betclic
└── .env                    # Clés API (JAMAIS sur GitHub)
```

### Ce qui a changé vs V1

| Avant (V1)                           | Maintenant (V2)                        |
|--------------------------------------|----------------------------------------|
| 3 apps Dash séparées, 3 Flask servers | 1 seul Flask server partagé (server.py)|
| PythonAnywhere ne servait qu'un dashboard | Les 3 apps tournent sur la même URL |
| DB_PATH relatif → crash au Reload     | DB_PATH absolu via BASE_DIR            |
| Routes /export/csv en conflit         | Routes uniques /export/psg/csv etc.    |

### URLs en production

| URL                                    | Contenu                      |
|----------------------------------------|------------------------------|
| lucsharper.pythonanywhere.com/         | Landing page sélection client |
| lucsharper.pythonanywhere.com/psg/     | Dashboard PSG                |
| lucsharper.pythonanywhere.com/betclic/ | Dashboard Betclic            |
| lucsharper.pythonanywhere.com/health   | Healthcheck JSON             |

---

## 1. Déploiement PythonAnywhere

### A. Push GitHub (depuis le Mac)
```bash
cd /Users/lucmonteil/Voxa
git add server.py wsgi.py app_router.py dashboard.py dashboard_betclic.py tracker.py tracker_betclic.py DEPLOY.md
git commit -m "V2 — unified multi-dashboard, shared Flask server"
git push
```

### B. Pull PythonAnywhere
```bash
cd ~/Voxa && git pull
```

### C. Virtualenv (si pas déjà fait)
```bash
workon voxa
pip install dash dash-bootstrap-components plotly pandas python-dotenv
```

### D. Configurer le WSGI

Onglet **Web** → clic sur le fichier WSGI → **remplacer TOUT** par :

```python
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, '/home/lucsharper/Voxa')
load_dotenv('/home/lucsharper/Voxa/.env')

from wsgi import application
```

### E. Virtualenv dans l'onglet Web

Vérifier que le champ **Virtualenv** pointe vers :
```
/home/lucsharper/.virtualenvs/voxa
```

### F. Reload → Tester

Clic **Reload** → ouvrir lucsharper.pythonanywhere.com

---

## 2. Scheduler PythonAnywhere (onglet Tasks)

| Heure | Commande |
|-------|----------|
| 02:00 | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/tracker.py` |
| 02:30 | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/tracker_betclic.py` |

Important : utiliser le chemin complet du python du virtualenv.

```bash
mkdir -p ~/Voxa/logs
```

---

## 3. Workflow Git quotidien

```bash
# Mac — modifier → push
cd /Users/lucmonteil/Voxa
git add -A && git commit -m "description" && git push

# PythonAnywhere — pull → reload
cd ~/Voxa && git pull
# Puis Reload dans onglet Web
```

---

## 4. Tests locaux

```bash
# Dashboards individuels
python3 dashboard.py             # http://localhost:8050 (PSG)
python3 dashboard_betclic.py     # http://localhost:8051 (Betclic)
python3 app_router.py            # http://localhost:8060 (landing)

# Trackers
python3 tracker.py --demo
python3 tracker_betclic.py --demo
python3 tracker.py --report
```

---

## 5. Ajouter un nouveau client

1. Créer `tracker_nouveauclient.py` et `dashboard_nouveauclient.py`
2. Dans le dashboard : `url_base_pathname="/nouveauclient/"`
3. Dans `wsgi.py` ajouter : `import dashboard_nouveauclient`
4. Dans `app_router.py` ajouter le client au dict `CLIENTS`
5. Push + pull + Reload

---

## 6. Troubleshooting

**Dashboard ne charge pas** → onglet Web → Error log

**ModuleNotFoundError: No module named 'server'** → vérifier sys.path dans le fichier WSGI

**Données pas à jour** → vérifier les tâches schedulées avec le bon chemin python virtualenv