# Voxa — Guide de déploiement V2
## PythonAnywhere · Architecture complète

---

## Architecture

```
wsgi.py (DispatcherMiddleware)
  /           → app_router.py  + server.py (Flask partagé)
                 Routes : /login /register /logout
                          /demo (competitive vote + GEO Score)
                          /settings (clé API)
                          /health (JSON)
                          /api/v1/vote|score|benchmark|history
  /psg/       → dashboard.py   (Dash PSG — Flask propre)
  /betclic/   → dashboard_betclic.py (Dash Betclic — Flask propre)

Modules :
  voxa_db.py     → lecture sur voxa.db + voxa_betclic.db + voxa_accounts.db
  voxa_engine.py → competitive_vote + AlertEngine + RecoEngine
```

---

## 1. Premier déploiement (ou mise à jour)

### A. Packages à installer (une seule fois)
```bash
workon voxa
pip install flask-login flask-bcrypt anthropic
```

### B. Vérification avant Reload (toujours)
```bash
cd ~/Voxa && git pull
python3 -c "from wsgi import application; print('WSGI OK')"
```
Si `WSGI OK` → Reload. Sinon → lire l'erreur.

### C. Créer le compte admin (une seule fois)
```bash
cd ~/Voxa
python3 -c "
import voxa_db as vdb
vdb.init_accounts_db()
try:
    aid = vdb.create_account('luc@sharper-media.com', 'voxa2026!', 'Luc Monteil', 'enterprise')
    c = vdb.conn_accounts()
    c.execute('UPDATE accounts SET is_admin=1 WHERE id=?', (aid,))
    c.commit(); c.close()
    print('Admin créé')
except: print('Admin existe déjà')
acc = vdb.get_account_by_email('luc@sharper-media.com')
print('API key:', acc['api_key'])
"
```

---

## 2. Workflow Git quotidien

### Mac
```bash
cd /Users/lucmonteil/Voxa
git add <fichiers modifiés>
git commit -m "description"
git push
```

### PythonAnywhere
```bash
cd ~/Voxa && git pull
python3 -c "from wsgi import application; print('WSGI OK')"
# Puis Reload dans l'onglet Web
```

---

## 3. Scheduler PythonAnywhere (onglet Tasks)

**Créer le dossier de logs :**
```bash
mkdir -p ~/Voxa/logs
```

**4 tâches à configurer :**

| Heure | Fréquence | Commande |
|-------|-----------|---------|
| 02:00 | Quotidien | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/tracker.py >> /home/lucsharper/Voxa/logs/tracker_psg.log 2>&1` |
| 02:30 | Quotidien | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/tracker_betclic.py >> /home/lucsharper/Voxa/logs/tracker_betclic.log 2>&1` |
| 03:00 | Quotidien | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/voxa_engine.py --all >> /home/lucsharper/Voxa/logs/engine.log 2>&1` |
| 06:00 | 1er du mois | `/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/email_reporter.py --client all >> /home/lucsharper/Voxa/logs/email.log 2>&1` |

**Important :** toujours utiliser le chemin complet du python du virtualenv.

**Vérifier les logs :**
```bash
tail -50 ~/Voxa/logs/tracker_psg.log
tail -50 ~/Voxa/logs/tracker_betclic.log
tail -20 ~/Voxa/logs/engine.log
```

---

## 4. Tests live

| URL | Résultat attendu |
|-----|-----------------|
| `/health` | JSON scores PSG + Betclic |
| `/demo` | Formulaire competitive vote |
| `/login` | Page connexion |
| `/settings` | Clé API + endpoints |
| `/psg/` | Dashboard PSG (tab Recommandations) |
| `/betclic/` | Dashboard Betclic (tab Insights) |
| `/api/v1/vote?brand=Betclic&vertical=bet` | JSON concurrents |
| `/api/v1/score?slug=betclic` | 401 sans clé |

---

## 5. Coûts infrastructure mensuels

| Composant | Coût |
|-----------|------|
| Claude Haiku (PSG + Betclic trackers) | ~12 € |
| Claude Haiku (engine recos) | ~2 € |
| Perplexity (Betclic) | ~30 € |
| PythonAnywhere Hacker | ~5 € |
| **TOTAL** | **~49 € / mois** |

Marge sur retainer Betclic 4 500€ : **98.9%**

---

## 6. Fichiers modifiés vs V1

| Fichier | Statut | Description |
|---------|--------|-------------|
| `server.py` | ★ NOUVEAU | Flask partagé — auth, /demo, /settings, /health, API |
| `voxa_db.py` | ★ NOUVEAU | Lecture DB existantes + voxa_accounts.db |
| `voxa_engine.py` | ★ NOUVEAU | Competitive vote + alertes + recommandations |
| `wsgi.py` | MODIFIÉ | Commentaires architecture clarifiés |
| `app_router.py` | MODIFIÉ | Import server partagé (3 lignes) |
| `dashboard.py` | MODIFIÉ | Tab Recommandations ajouté |
| `dashboard_betclic.py` | MODIFIÉ | Tab Insights enrichi (alertes + recos DB) |
| `tracker.py` | INCHANGÉ | |
| `tracker_betclic.py` | INCHANGÉ | |
| `email_reporter.py` | INCHANGÉ | |
| `voxa.db` | INCHANGÉ | |
| `voxa_betclic.db` | INCHANGÉ | |
| `voxa_accounts.db` | ★ NOUVEAU AUTO | Créé au premier démarrage |