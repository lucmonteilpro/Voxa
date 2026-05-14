# Voxa — Contexte projet (v3)

> Document maître à charger dans le project knowledge "Voxa" sur claude.ai
> et copié à la racine du repo en `CLAUDE.md` pour Claude Code.
> Maintenu manuellement, à régénérer à chaque évolution majeure d'architecture.

---

## 1. Pitch produit

Voxa est un SaaS de **GEO Intelligence** : on mesure et on améliore la visibilité d'une marque dans les réponses des LLM grand public (ChatGPT, Claude, Perplexity, Gemini). Pure GEO, pas de SEO Google.

**Modèle économique** : retainer mensuel multi-tiers. Pilote payant en cours sur Betclic, prospects en démo (Le Havre AC, ASSE, Winamax, Unibet, Édouard Philippe).

**Différenciation produit (Phase 2 en cours)** : architecture multi-agents qui rebouclent jusqu'à un résultat satisfaisant — Gap Analyzer, Crawlability, Content Creator, Quality Controller, orchestrateur hybride.

---

## 2. Stack technique

- **Langage** : Python 3.10
- **Web** : Flask + Dash/Plotly avec DispatcherMiddleware multi-clients
- **Frontend dashboards** : Dash + Bootstrap 5 + `theme.py` (design system unifié)
- **DB** : SQLite, une base par client (`voxa.db`, `voxa_betclic.db`, etc.)
- **LLMs trackés** : Claude (Anthropic SDK), GPT-4o-mini (OpenAI), Perplexity Sonar — historiquement via API, **désormais via crawling UI Perplexity** (Patchright + Chrome)
- **Agents** : Anthropic SDK natif (pas LangChain, pas CrewAI)
- **Crawling Perplexity** : Patchright (anti-détection) + sessions persistantes
- **Hosting** : PythonAnywhere (plan Hacker), `lucsharper.pythonanywhere.com`
- **Local** : `/Users/lucmonteil/Voxa` (Mac)
- **Repo** : `lucmonteilpro/Voxa` (privé), branche par défaut `main`, URL `https://github.com/lucmonteilpro/Voxa.git`

---

## 3. Architecture v3 — principes clés

**DispatcherMiddleware multi-clients** : un seul process Flask sert N dashboards Dash via `wsgi.py`. Le routing par slug est fait au niveau WSGI, pas dans Flask.

**Factory pattern dashboards** : `dashboard_generic.py` expose `make_dashboard(slug)` qui lit `configs/{slug}.json` et instancie un dashboard Dash complet. Plus de `dashboard_psg.py` / `dashboard_betclic.py` séparés.

**Auto-discovery clients** : `wsgi.py` v3 scanne `configs/*.json` au démarrage et monte automatiquement chaque dashboard sur `/{slug}/`. Ajouter un client = ajouter un JSON dans `configs/`.

**Trackers — bascule API → UI** : le tracker actuel (`tracker_ui.py`) crawle Perplexity en simulant un utilisateur humain (Chrome + Patchright). C'est le tracker **actif aujourd'hui** (88 runs Sonar 2 produits le 04/05). L'ancien tracker `tracker.py` mode API HTTP (Claude Haiku + GPT-4o-mini + Sonar API) est **endormi** mais conservé pour la traçabilité scientifique des 8098 mesures historiques (utiles pour étude de corrélation Sonar 2 vs autres modèles).

**Storage agents** : table `agent_runs` ajoutée par `migrate_v3.py` à toutes les DBs. Stockage SQLite (pas JSON files) pour cohérence et requêtabilité.

**Design system unifié** : `theme.py` source de vérité. Exporte palette (C1, C2, NG, BG), CSS_FLASK, DASH_CSS (avec override Bootstrap 5 vars dans :root), helpers (score_color, card_style, make_topbar, make_btn_dark, make_btn_primary, badge_style).

---

## 4. Arborescence (résumé)

Voir `VOXA_TREE.md` pour l'arbre complet. Modules principaux :

- **Racine** : entrypoints (`wsgi.py`, `server.py`, `app_router.py`), trackers, dashboard factory, modules métier (`action_pack`, `geo_optimizer`, `score_simulator`, `site_scanner`, etc.), tests, migrations
- **`agents/`** : architecture multi-agents v3 (base + 4 agents : gap_analyzer, crawlability_agent, content_creator, quality_controller)
- **`configs/`** : config JSON par client (7 clients actifs)
- **`crawlers/`** : infra de scraping Perplexity (`base.py`, `perplexity.py`, `diagnose_response_dom.py`) + sessions persistantes Patchright + dump screenshots (gitignoré)
- **`scripts/`** : shell scripts ops (`install_cron.sh`, `setup_ssh_pa.sh`, `voxa_nightly.sh`)

---

## 5. Modules racine — rôle de chaque fichier

| Fichier | Rôle | Statut |
|---|---|---|
| `wsgi.py` | Entrypoint WSGI, DispatcherMiddleware, auto-discovery configs | ✅ Actif |
| `server.py` | Serveur Flask central (landing, login, settings, /demo, /api/v1/*) | ✅ Actif |
| `app_router.py` | Router landing + dict CLIENTS | ✅ Actif |
| `dashboard_generic.py` | Factory `make_dashboard(slug)` Dash | ✅ Actif |
| `tracker.py` | Tracker legacy mode API HTTP (Claude Haiku + GPT + Sonar API). 8098 mesures historiques. | 💤 Endormi (conservé pour traçabilité scientifique) |
| `tracker_betclic.py` | Tracker Betclic 4 marchés (FR/PT/CI/PL), 88 prompts | ✅ Actif |
| `tracker_generic.py` | Tracker générique JSON-config-driven | ✅ Actif |
| `tracker_ui.py` | Tracker actuel : crawl Perplexity via Chrome + Patchright (simule humain) | ✅ Actif (production) |
| `voxa_db.py` | Couche d'accès DB, dynamic config loading | ✅ Actif |
| `voxa_engine.py` | Engine de génération de recommandations | ✅ Actif |
| `theme.py` | Design system source de vérité | ✅ Actif |
| `geo_optimizer.py` | Génération JSON-LD, FAQPage, Organization Schema, suggestions articles | ✅ Actif |
| `action_pack.py` | Module V2 — pipeline "Pack Action Hebdo" | ✅ Actif |
| `score_simulator.py` | Module V2 — simulateur de score | ✅ Actif |
| `email_reporter.py` | Reporting mensuel par email (invoque `report_generator.py` en subprocess) | ⚠️ Voir §13 dette technique |
| `report_generator.py` | Moteur de génération de rapports clients (importé par `server.py`, invoqué par `email_reporter.py`) | ⚠️ Voir §13 dette technique |
| `site_scanner.py` | Crawlability scan (robots.txt, GPTBot/ClaudeBot/PerplexityBot) | ✅ Actif |
| `migrate_v2.py` / `migrate_v3.py` | Migrations DB | 🔧 Outils |
| `test_baseline.py` / `test_qc_rag.py` / `test_variance.py` | Tests | 🧪 |
| `analyze_variance.py` | Analyse de variance des runs | 🔧 Outil |

---

## 6. Architecture multi-agents (`agents/`)

**Classe abstraite** : `agents/base.py` — interface `Agent` avec input → output, log dans `agent_runs`, gestion success/failure/parent chaining/get_last_run.

**Agents implémentés** :

| Agent | Fichier | Rôle | État |
|---|---|---|---|
| Gap Analyzer | `gap_analyzer.py` | Analyse `sources` + `results` Perplexity, détecte les angles morts (seuil ≤ 60/100) | ✅ Stable (Phase 2B) |
| Crawlability | `crawlability_agent.py` | Vérifie l'accès des bots IA (GPTBot, PerplexityBot, ClaudeBot) | ✅ Stable (renommé depuis `seo_agent`) |
| Content Creator | `content_creator.py` | Pour chaque angle mort détecté : génère un paragraphe (150-200 mots) **+** schema JSON-LD FAQPage (2 paires Q&R) via API Claude. Output stocké en DB dans table `action_items`. Modes CLI : `--from-gap`, `--iterate`, `--n-items`, `--threshold`, `--target-score`, `--dry-run`, `--json`. Coût ~0.05$/item. | ✅ MVP (avec bug DB connu, voir §13) |
| Quality Controller v2 | `quality_controller.py` | Valide chaque item du Content Creator via protocole control/test : 1 crawl Perplexity sans injection (baseline), 3 crawls avec injection via template factuel neutre, médiane. Filtre Claude Haiku sur chaque crawl test (verdict pertinent/cosmetique/absent). Statut `validated` si delta > 10 ET ≥ 2/3 pertinents. CLI : `--slug`, `--pack-id`, `--limit`, `--dry-run`, `--json`. | ✅ Stable (Phase 2E livrée 04/05) |
| Orchestrator | `orchestrator.py` | Boucle de convergence sur items en `needs_iteration` : régénération contextualisée par Content Creator + revalidation par QC v2 jusqu'à validated OU plateau quantitatif OU max 5 itérations. Skip les items déjà validated. Persiste history JSON complet pour audit. CLI : `--slug`, `--pack-id`, `--limit`, `--dry-run`, `--json`. | ✅ Stable (Phase 2F livrée 05/05) |

**Décisions actées** :
- Framework : Anthropic SDK natif
- Stockage outputs : table `agent_runs` SQLite (table dédiée `action_items` pour les outputs Content Creator)
- Boucle orchestrateur : hybride max 5 itérations OR plateau
- Génération recos : Option A (Python templates) → extensible vers Option C (Claude API)
- Seuil angle mort : ≤ 60/100

**À construire** : orchestrateur (Phase 2 finale) qui chaîne les agents jusqu'à un résultat satisfaisant.

---

## 7. Conventions de code (à respecter par toute modif)

1. **Couleurs** : utiliser `theme.py` (C1, C2, NG, BG, helpers). **Aucune couleur hardcoded** dans les composants Dash. Bootstrap 5 vars overridées dans `:root` via DASH_CSS.
2. **Multi-clients** : `dashboard_generic.py` factory + `configs/*.json`. Pas de `dashboard_*.py` par client.
3. **Agents** : hériter de `agents.base.Agent`, logger dans `agent_runs`, CLI standalone (`python3 -m agents.X --slug Y`).
4. **DB** : passer par `voxa_db.py`, pas de SQL inline dans les modules métier.
5. **API LLMs** : Anthropic SDK pour Claude, pas LangChain ni CrewAI.
6. **Configs** : tout ce qui change par client va dans `configs/{slug}.json`. Pas de paramètres durs dans le code.
7. **Tests** : ajouter ou étendre les tests `test_*.py` à chaque feature non triviale.
8. **Secrets** : variables d'environnement uniquement (`.env` non versionné). Ne jamais commit de clés API.
9. **Suppression / refacto cross-fichiers** : `grep -rn "nom_du_fichier"` AVANT toute suppression. Jamais de `git rm` à l'aveugle.

---

## 8. Workflow déploiement

**Local → Prod en 3 commandes** :

```bash
# Mac
cd /Users/lucmonteil/Voxa
git add -A && git commit -m "..." && git push

# PythonAnywhere (console SSH)
cd ~/Voxa && git pull
# Puis Reload via onglet Web
```

**Trackers automatisés** : crons PythonAnywhere (onglet Tasks) appellent les trackers chaque nuit avec le chemin complet du virtualenv :
```
/home/lucsharper/.virtualenvs/voxa/bin/python /home/lucsharper/Voxa/tracker_betclic.py
```

---

## 9. Variables d'environnement

Fichier `.env` à la racine (gitignoré). Clés actuelles :

| Variable | Usage | Statut |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API (Content Creator + tracker.py legacy) | ✅ Active |
| `OPENAI_API_KEY` | GPT-4o-mini (tracker.py legacy uniquement) | 💤 Plus utilisée en prod (mode API abandonné) |
| `PERPLEXITY_API_KEY` | Sonar API (tracker.py legacy uniquement) | 💤 Plus utilisée en prod (mode API abandonné) |

> Les deux clés legacy peuvent être conservées tant que `tracker.py` est gardé pour la traçabilité scientifique. Décision à prendre si on supprime un jour `tracker.py`.

---

## 10. `.gitignore` (confirmé propre)

```
voxa.db
*.db
__pycache__/
*.pyc
.env
.DS_Store
crawlers/sessions/
crawlers/screenshots/
```

Aucun risque de fuite (clés, DBs, sessions Chrome, screenshots Perplexity).

---

## 11. État d'avancement (mai 2026)

### Phase 0 — Sprint Betclic infra : 🟡 en cours

Objectif : que les runs UI tournent automatiquement chaque nuit et que les données soient visibles sur PA pour les 4 marchés Betclic.

- ✅ Scripts shell créés (`voxa_nightly.sh`, `setup_ssh_pa.sh`, `install_cron.sh`)
- ❌ SSH key Mac → PA configurée (bloqueur : mot de passe PA à régénérer)
- ❌ Test SCP manuel `voxa_betclic.db` → PA
- ❌ Run all-markets exécuté (FR + PT + FR-CI + PL = 88 prompts)
- ❌ Cron 02h00 installé sur Mac
- ❌ Vérification du run nocturne

**Critère de fin** : `lucsharper.pythonanywhere.com/betclic/` affiche les données UI sur les 4 marchés et les recommandations dans le tab Insights.

### Phase 1 — Démo Betclic : 🔄 reporté

Statut : reporté car Olivier Audibert a déjà été pitché. Trigger de redémarrage : son retour.

### Phase 2 — Architecture multi-agents : 🟡 priorité 1

- ✅ 2A : Migration DB v3 + classe abstraite Agent
- ✅ 2B : Gap Analyzer
- ✅ 2C : Crawlability Agent (renommage depuis seo_agent)
- 🟡 2D : Content Creator (MVP fonctionnel mais bug table `action_items` à corriger sur `voxa_betclic.db`)
- ✅ 2E : Quality Controller v2 (livré + validé sur Pack #2 Betclic le 04/05)
- ✅ 2F : Orchestrateur hybride (livré + validé sur Pack #2 Betclic le 05/05)

### Phase 3 — Crawlers UI multi-LLMs : 🟡 en cours

- ✅ Session 1 : Crawler Claude.ai Sonnet 4.6 Adaptatif (livré 13/05, commit 5a72956)
- ⏳ Session 2 : Gemini
- ⏳ Session 3 : Grok
- ⏳ Session 4 : UI dashboard breakdown par LLM
- ⏳ Session 5 : ChatGPT (compte Plus requis)

**Note Claude.ai Adaptatif** : Claude.ai mode Adaptatif déclenche le web search à sa discrétion (~50% sur les prompts Betclic testés). Voxa traite ce taux comme une donnée GEO à part entière. Deux types de visibilité distincts à terme :
- **GEO search-time** (sources citées via web search) — mesurable directement
- **GEO recall-time** (marque citée depuis les connaissances du modèle, sans sources) — à exploiter en Session 1bis quand on aura le scoring associé

Le champ `search_triggered` est persisté dans `crawl_metadata_json` de chaque run Claude pour mesurer le taux de déclenchement.

---

## 12. Clients & configs actifs

| Slug | Vertical | Statut commercial |
|---|---|---|
| `betclic` | Paris sportifs FR/PT/CI/PL | Pilote payant en cours |
| `psg` | Foot Ligue 1 | Cas d'étude interne |
| `ephilippe` | Politique | Démo prospect |
| `lehavre` | Foot Ligue 1 | Démo prospect |
| `saintetienne` | Foot Ligue 1/2 | Démo prospect |
| `unibet` | Paris sportifs | Démo prospect |
| `winamax` | Paris sportifs | Démo prospect |

---

## 13. Dette technique connue (à traiter quand bande passante)

### Ticket DT-1 : `report_generator.py` + `email_reporter.py` — module reporting client inutilisé

**Constat** : `report_generator.py` (moteur de génération de rapports) et `email_reporter.py` (envoi mensuel par email) sont actifs dans le code mais **plus utilisés** côté business — Voxa n'envoie plus de rapports mensuels automatiques aux clients.

**Références dans le code** (vérifié par grep le 04/05/2026) :
- `server.py:717` → `from report_generator import generate_report, CLIENTS`
- `email_reporter.py:159` → invoque `report_generator.py` en subprocess
- `report_generator.py` lui-même (header docstring CLI)

**Pourquoi on a gardé pour l'instant** : suppression non triviale — il faut couper coordonnement les 3 points (route admin dans `server.py`, le cron `email_reporter.py` sur PA s'il tourne, le fichier `report_generator.py`). Risque de casser le serveur si fait à moitié.

**Quand traiter** : quand on aura 1h calme pour faire la suppression coordonnée propre. Pas urgent.

**Action de suppression (pour mémoire, à exécuter le moment venu)** :
1. Supprimer la route `/admin/report/...` dans `server.py` (et l'import)
2. Désactiver le cron `email_reporter.py` sur PA (onglet Tasks)
3. `git rm report_generator.py email_reporter.py`
4. Nettoyer les éventuelles entrées dans `voxa_db.py` ou autres modules
5. Test smoke : reload PA + vérifier que toutes les routes répondent

### Ticket DT-2 : CLOSED — faux positif (vérifié 04/05/2026)

**Constat initial** : on pensait que la table `action_items` manquait dans `voxa_betclic.db` et que le Pack #2 du 01/05 avait planté.

**Diagnostic réel** : la table n'a jamais été censée exister dans les DBs par client. L'architecture est centralisée dans `voxa_accounts.db` (cf `action_pack.py:38` et toutes les fonctions Pack qui utilisent `vdb.conn_accounts()`). Le Pack #2 est bien en DB depuis le 02/05/2026 20h00 (3 items, statuts `validated` / `needs_iteration` / `validated`).

**Mécanisme d'init** : `_init_pack_tables()` (`action_pack.py:75`) est appelée au top-level du module ligne 85, donc déclenchée par effet de bord à chaque import de `action_pack`. SQLite crée le fichier `voxa_accounts.db` s'il n'existe pas. Sur tout environnement neuf, l'import de `action_pack` (ou de `agents.content_creator` qui en dépend) crée la DB et les tables.

**Point d'attention** : ce mécanisme par effet de bord est fonctionnel mais fragile. Un refacto futur de `action_pack.py` qui déplacerait `_init_pack_tables()` en lazy-init perdrait silencieusement la création des tables. Smoke test ajouté (cf `test_action_pack_smoke.py`) pour attraper cette régression.

### Ticket DT-3 : CLOSED ✅ 04/05/2026

QC v2 livré. Multi-crawl + filtre Haiku + protocole control/test. Validé sur Pack #2 Betclic (cf. `VOXA_PLAN.md` journal du 04/05).

### Ticket DT-4 : Clés API legacy `OPENAI_API_KEY` / `PERPLEXITY_API_KEY`

**Constat** : ces deux clés ne servent plus en prod (mode API abandonné), mais sont gardées pour `tracker.py` legacy.

**Décision en suspens** : si un jour on supprime `tracker.py`, on supprime aussi ces clés du `.env`. Pas urgent.

### Ticket DT-5 : Migrer Betclic et PSG vers le dynamic loader configs JSON

**Constat** : `voxa_db.py` définit Betclic et PSG en STATIQUE (l.42-50) alors que les autres clients passent par `_load_dynamic_configs` à partir de `configs/*.json`. C'est une double source de vérité.

**Découvert le** : 04/05/2026 lors de la Phase 2E (besoin de propager le champ `domain` pour le QC v2).

**Action** : migrer Betclic et PSG en config JSON dynamic, supprimer la dict statique. Vérifier que `dashboard_url` reste cohérent (`/{slug}/` est construit identiquement en static et dynamic).

**Quand** : non urgent. À traiter quand on aura à ajouter un 3e champ qui nécessite la même duplication.

---

## 14. Préférences de collaboration (rappel synthétique)

Style de réponse attendu de Claude (web et Code) :

- Explications claires et concises avant toute modif
- Format **ancien code / nouveau code séparé**, avec chemin exact du fichier
- Modifs <20 lignes / 1 fichier → bloc à coller dans la conversation
- Au-delà → brief de session pour Claude Code, pas du copier-coller massif
- Jamais de réécriture complète d'un fichier si quelques lignes changent
- **Grep des références AVANT toute suppression** (leçon DT-1)
- Pas de yes-man : challenge si meilleure option visible, propose 2-3 options avec trade-offs sur les décisions d'archi
- Emails rédigés directement sans demander permission

---

## 15. Méthodologie de session Claude Code CLI

Convention d'utilisation de Claude Code (CLI ou panel VSCode) sur ce repo, à respecter à chaque session pour éviter les frictions de sync.

### Avant la session (30 sec)

```bash
cd ~/Voxa
git status          → working tree doit être clean
git pull --ff-only  → synchronise depuis GitHub
```

### Démarrer la session

- Soit `claude` dans le terminal VSCode (mode CLI)
- Soit ouvrir l'extension Claude Code dans la panel VSCode (mode UI)
- L'agent lit ce `CLAUDE.md` automatiquement et dispose du contexte projet
- Coller le brief généré depuis le chat claude.ai (Projet Voxa)

### Pendant la session

- L'agent modifie, teste, propose des commits — visibilité fichier par fichier
- Garder l'option "Ask before edits" activée pour valider chaque modif
- Interrompre / corriger à tout moment si besoin

### Après la session

```bash
git log --oneline -3   # pour vérifier le commit final
git push               # pour pousser sur GitHub
# Si branche feature : merger dans main
git merge feat/xxx --ff-only && git push
```

### Discipline branches

- **Petites évolutions / fixs / docs** : direct sur `main`
- **Refactos cross-fichiers, migrations DB, gros changements** : créer une branche feature avant la session : `git checkout -b feat/phase-XX`

### Outils à NE PAS utiliser pour ce repo

- **L'onglet `</>` Code de claude.ai** : crée des worktrees fantômes locaux qui désynchronisent `main` avec les modifs WIP. Bug vécu sur Phase 2G le 05/05.

---

## 16. Protocole de validation — leçons du 08/05/2026

Règles de validation à appliquer pour toute phase, migration, ou déploiement, tirées des erreurs de synchro Mac → PA observées le 08/05/2026.

### Règle 1 — Validation = vérification dans l'environnement cible

Une phase n'est jamais déclarée fermée sur la base d'un test à blanc qui "ne plante pas". Elle est fermée uniquement quand le résultat attendu est vu dans l'environnement final (PA pour la prod, localhost acceptable seulement pour les phases internes).

### Règle 2 — Symétrie dev → prod explicite

Toute migration DB ou modif de schéma appliquée en local doit être accompagnée d'une procédure documentée pour la prod, dans le brief Code de la phase. Ne jamais supposer qu'un SCP nightly transporte les changements de schéma — il transporte du contenu, pas de la structure.

### Règle 3 — Tester / Vérifier / Itérer

Aucune phase n'est validée sans vérification visuelle dans l'environnement cible final. Le pitch commercial sera fait sur PA, donc toutes les démos sont validées sur PA, pas sur localhost. Si quelque chose s'affiche différemment entre les deux, l'environnement de référence est PA.

### Règle 4 — Ouvrir un ticket DT plutôt qu'oublier

Quand un mismatch est découvert (data manquante, colonne manquante, comportement inattendu), même hors scope de la session en cours : ouvrir un ticket DT-X dans VOXA_PLAN.md immédiatement. Ne jamais reporter à "plus tard sans trace".

---

*Dernière mise à jour : 08/05/2026 — DT-7 résolu, leçons protocolaires (§16) inscrites.*
*À régénérer après chaque évolution majeure d'architecture (migration DB, ajout d'un agent, refacto cross-fichiers).*
