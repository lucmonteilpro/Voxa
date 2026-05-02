# Voxa — Plan d'action

> **Document vivant** — Claude met à jour ce fichier systématiquement à chaque
> session. Tu peux aussi l'éditer librement entre les sessions.
>
> **Conventions de statut** :
> - ✅ Terminé
> - 🟡 En cours
> - ⏳ À faire
> - ❌ Bloqué (avec note explicative)
> - 🔄 Reporté / en attente
> - ⏸ Pausé / parked

---

## 🔥 Tâches en attente immédiate

> Tâches concrètes à exécuter dès que possible (pas des phases entières).

- [x] **Lancer `tracker_ui.py --slug betclic --all-markets`** (run terminé : 88 runs, 1385 sources)
- [x] **Lancer Gap Analyzer all-markets** : 23 angles morts détectés
- [x] **Tester Content Creator en mode --from-gap** : OK, 2 items générés (delta +90)
- [ ] **Bug fix Content Creator** : appliquer la version corrigée pour le KeyError 'delta'
- [ ] **Setup SSH Mac → PA** : retrouver mot de passe PA puis relancer `./scripts/setup_ssh_pa.sh`
- [ ] **Installer cron 02h00** : `./scripts/install_cron.sh` après que SSH fonctionne

---

## 📊 Vue d'ensemble

| Phase | Objectif | Statut | Sessions estimées | Échéance |
|---|---|---|---|---|
| **Phase 0** | Sprint Betclic — finir l'infra crawl + sync | 🟡 | 1 (en cours) | Cette semaine |
| **Phase 1** | Démo Betclic prête | 🔄 | 2-3 | Reporté (Olivier déjà pitché) |
| **Phase 2** | Architecture multi-agents | 🟡 | 8-10 (4/8 faits) | 3-4 semaines |
| **Phase 3** | Crawlers UI multi-LLMs | ⏳ | 4-5 | 2 semaines |
| **Phase 4** | Chatbot agentique sidebar | ⏳ | 4-5 | 2 semaines |
| **Phase 5** | Olivier's 5 besoins Betclic | 🔄 | 3-4 | Selon retour Olivier |
| **Phase 6** | Migration Hetzner | 🔄 | 2-3 | Quand product mature |
| **Phase 7** | Pub ChatGPT US | ⏸ | — | Pas de calendrier |
| **Phase 8** | Voxa Politics — adaptation produit | ⏳ | 2-3 | Quand Phase 2 quasi terminée |

---

## ✅ Phase préparatoire (déjà fait — historique)

- [x] Dashboard light mode + sidebar 3 sections (MONITOR / IMPROVE / DISCOVER)
- [x] 4 KPI cards avec icônes
- [x] Filter bar sticky compact
- [x] Migration DB v2 : ajout `crawl_method`, `screenshot_path`, `crawl_duration_ms`, table `sources`
- [x] Backup automatique des DBs avant migration
- [x] Crawler `crawlers/perplexity.py` (patchright + Chrome stable)
- [x] Login Perplexity persistant (cookies dans `crawlers/sessions/perplexity_patchright/`)
- [x] Tracker UI v1 : crawl + persistence DB
- [x] Tracker UI v2 : `--all-markets`, idempotence, ETA, gestion erreurs
- [x] Run Betclic FR validé : 22 prompts, 298 sources, score 84.9/100
- [x] Run Betclic all-markets : 88 runs, 1385 sources, 23 angles morts
- [x] Top 10 domaines Perplexity FR identifiés
- [x] Recommandations dashboard filtrées sur runs >= 2026-05-01
- [x] Souscription Perplexity Pro

---

## 🟡 Phase 0 — Sprint Betclic infra (en cours)

**Objectif** : que les runs UI tournent automatiquement chaque nuit et que les données soient visibles sur PA.

- [x] Scripts shell créés (`voxa_nightly.sh`, `setup_ssh_pa.sh`, `install_cron.sh`)
- [ ] SSH key Mac → PA configurée — Bloqueur : retrouver mot de passe PA
- [ ] Test SCP manuel : `scp ~/Voxa/voxa_betclic.db lucsharper@ssh.pythonanywhere.com:~/Voxa/`
- [x] Run all-markets exécuté (FR + PT + FR-CI + PL = 88 prompts, 1385 sources)
- [ ] Cron 02h00 installé sur Mac (`./scripts/install_cron.sh`)
- [ ] Vérification du run nocturne le lendemain matin

**Critère de fin de phase** : `lucsharper.pythonanywhere.com/betclic/` affiche les données UI sur les 4 marchés et les recommandations dans le tab Insights.

---

## 🔄 Phase 1 — Démo Betclic prête (reporté)

Reporté car Olivier déjà pitché. On attend son retour avant de retravailler la démo.

- [ ] Page de démo scénarisée `/betclic-demo`
- [ ] Polish + répétition démo
- [ ] Démo réelle avec Olivier

**Trigger de redémarrage** : retour d'Olivier.

---

## 🟡 Phase 2 — Architecture multi-agents (priorité 1)

**Objectif** : matcher la promesse Meikai d'agents qui rebouclent jusqu'à un résultat satisfaisant.

### Décisions de design (validées)

- ✅ **Framework** : Anthropic SDK natif (vs LangChain/CrewAI)
- ✅ **Stockage outputs** : table SQLite `agent_runs`
- ✅ **Premier agent** : Gap Analyzer
- ✅ **Boucle orchestrateur** : hybride max 5 itérations OR plateau
- ✅ **Génération recos** : Gap Analyzer = Python templates (gratuit) ; Content Creator = Claude API (qualité)
- ✅ **Seuil angle mort** : ≤ 60/100
- ✅ **Auto-création DB minimale** si slug sans tracking préalable
- ✅ **Voxa = GEO uniquement** : `seo_agent` renommé `crawlability_agent`
- ✅ **Refacto soft `action_pack.py`** : Content Creator hérite de `Agent`, réutilise `action_pack.py` privé

### Sous-phases

#### ✅ 2A — Migration DB v3 + classe abstraite Agent

#### ✅ 2B — Agent Gap Analyzer
- 23 angles morts détectés sur Betclic all-markets

#### ✅ 2C — Crawlability Agent
- Wrapper de `site_scanner.py`, audit GEO du site

#### ✅ 2D — Content Creator
- Hérite de `Agent`, réutilise `action_pack.py` privé
- Modes : `--from-gap`, `--iterate`, `--n-items`, `--threshold`
- Tri intelligent : score croissant + priorité catégorie (régulation, paiement)

#### ⏳ 2E — Quality Controller (suivant)
- [ ] Re-crawle Perplexity avec contenu proposé via prompt augmentation
- [ ] Mesure l'impact réel sur le score
- [ ] Feedback structuré au Content Creator si insuffisant

#### ⏳ 2F — Orchestrateur multi-agents
- [ ] Boucle Gap → Crawlability → Content → QC
- [ ] Critère d'arrêt : max 5 itérations OR plateau

#### ⏳ 2G — Intégration dashboard
- [ ] Tab "Optimisations" dans la sidebar (section IMPROVE)
- [ ] Affichage historique `agent_runs`
- [ ] Bouton "Lancer optimisation" qui déclenche l'orchestrateur

---

## ⏳ Phase 3 — Crawlers UI multi-LLMs

- [ ] `crawlers/chatgpt.py` : ChatGPT Search (login Google persistant)
- [ ] `crawlers/claude_ai.py` : Claude.ai
- [ ] `crawlers/gemini.py` : Gemini
- [ ] `tracker_ui.py` : argument `--llm`
- [ ] DB : runs séparées par LLM
- [ ] Vue dashboard : breakdown par LLM

---

## ⏳ Phase 4 — Chatbot agentique sidebar

- [ ] Backend Flask `/api/chat` (Claude API + tools)
- [ ] Tools : `query_db`, `generate_jsonld`, `simulate_score`, `run_agent`
- [ ] Frontend Dash : composant chat dans la sidebar gauche
- [ ] Historique persisté
- [ ] Affichage des outils invoqués

---

## 🔄 Phase 5 — Olivier's 5 besoins Betclic

1. ⏳ Landing pages GEO-only (`geo.betclic.fr`)
2. ⏳ Tracker clics par origine
3. ⏳ Estimation volumes prompts par marché
4. ✅ Score prédit + évolution (`score_simulator.py` + `action_pack.py`)
5. ⏳ Documentation "1 CNAME suffit"

---

## 🔄 Phase 6 — Migration infra Hetzner

**Trigger** : product mature ET 3-4 clients en discussion sérieuse.

- [ ] Inscription Hetzner Cloud + création VPS CX22 (4€/mois)
- [ ] Setup Ubuntu 24.04 + Python 3.12 + patchright + Chromium
- [ ] xvfb pour Chromium "headless visible"
- [ ] Login Perplexity Pro persistant via VNC
- [ ] systemd timer cron quotidien
- [ ] Sync auto Hetzner → PA via rsync nightly

---

## ⏸ Phase 7 — Pub ChatGPT US (parked)

À ressortir quand cash récurrent suffisant.

---

## ⏳ Phase 8 — Voxa Politics

### 8A — Alias slugs et tolérance
- [ ] `SLUG_ALIASES` : `edouardphilippe` → `ephilippe`, etc.

### 8B — Adaptation Gap Analyzer pour vertical politique
- [ ] Catégories : `discovery`, `program`, `comparison`, `position`, `reputation`

### 8C — Crawlability Agent pour sites politiques
- [ ] Audit horizons-le-parti.fr (score 17/100, pas de sitemap, 0 JSON-LD)
- [ ] Schema spécifique : `Person`, `Organization`, `PoliticalParty`

### 8D — Pitch Voxa Politics actualisé

### 8E — EU AI Act Politics
- [ ] Conformité Digital Omnibus (adopté 26 mars 2026)

---

## 🗒 Journal de bord

### 2026-05-01

**Phase 2D — Content Creator (terminé)**
- Refacto soft : `agents/content_creator.py` hérite de `Agent`, réutilise `action_pack.py` privé
- Tests OK : 2 items générés, delta +90 pts
- Bug fix : KeyError 'delta' quand pack existant lu en DB → utilisation de `.get()`
- Bug fix : tri intelligent des angles morts (score croissant + priorité catégorie)

**Insight commercial Betclic** : score Perplexity 84/100 atteint malgré crawlabilité 25/100 → potentiel énorme avec balisage GEO

**Insight Voxa Politics** : horizons-le-parti.fr à 17/100 → pas de sitemap, 0 JSON-LD → opportunité de pitcher rapidement

**Top concurrents Betclic toutes langues** : Unibet (19), STS (19), Parions Sport (18), Fortuna (18), FDJ (18), 1xBet (18), Winamax (17), Solverde (16), Bwin (15), Placard (12)

**Décisions clés**
- Hetzner reporté après amélioration produit complète
- Voxa = GEO uniquement (pas SEO)
- Content Creator = Claude API (qualité éditoriale critique)
- Plan d'action mis à jour systématiquement par Claude à chaque session
- À chaque feature ajoutée, une explication simple est ajoutée en bas du plan

---

## 📝 Comment utiliser ce document

1. **Mise à jour automatique** : Claude met à jour ce fichier à chaque session
2. **Édition manuelle** : tu peux modifier librement entre les sessions
3. **Tâches en attente immédiate** : section en haut pour les actions concrètes du jour
4. **Statuts** : modifie l'emoji en début de section/phase quand le statut change
5. **Décisions clés** : ajoute une entrée dans le **Journal de bord** avec la date
6. **Versionning** : ce fichier est dans `~/Voxa/VOXA_PLAN.md` et pushé sur GitHub

---

## 📚 Glossaire des features Voxa

> Pour chaque module/agent ajouté, une explication simple en français : à quoi
> ça sert, comment l'utiliser, ce que ça produit. Mise à jour systématique.

### Crawler Perplexity (`crawlers/perplexity.py`)

**À quoi ça sert** : récupère les vraies réponses que les utilisateurs voient
quand ils questionnent Perplexity, avec les sources web utilisées.

**Comment ça marche** : ouvre une fenêtre Chrome contrôlée, navigue sur
perplexity.ai, tape le prompt, attend la réponse, capture la réponse + les
sources URL.

**Ce que ça produit** : la réponse texte + une liste d'URLs sources +
screenshot de la page.

---

### Tracker UI (`tracker_ui.py`)

**À quoi ça sert** : lance le crawler Perplexity sur une liste de prompts pour
un client donné (ex: les 22 prompts Betclic FR), pour mesurer la présence de
la marque dans les réponses.

**Comment l'utiliser** :
- 1 marché : `python3 tracker_ui.py --slug betclic --language fr`
- Tous marchés : `python3 tracker_ui.py --slug betclic --all-markets`
- Test rapide : `python3 tracker_ui.py --slug betclic --language fr --limit 3`

**Ce que ça produit** : pour chaque prompt, un score GEO (0-100) basé sur la
présence/sentiment/position de la marque + sources Perplexity capturées.

**Idempotence** : si tu relances le même jour, les prompts déjà crawlés sont
skip. Pratique pour reprendre après une coupure.

---

### Migration DB v3 (`migrate_v3.py`)

**À quoi ça sert** : a ajouté la table `agent_runs` à toutes les bases SQLite
Voxa pour permettre l'architecture multi-agents.

**Comment l'utiliser** : `python3 migrate_v3.py` (déjà fait, idempotent).

**Ce que ça produit** : table SQLite qui logge chaque exécution d'agent
(qui ? quand ? combien de temps ? succès ou échec ? quel input/output ?).

---

### Classe abstraite Agent (`agents/base.py`)

**À quoi ça sert** : fondation commune pour tous les agents Voxa. Évite la
duplication du code de logging.

**Comment l'utiliser** : tu hérites de `Agent` et tu implémentes juste la
méthode `execute()`. Le reste (logging DB, gestion erreurs, durée) est géré
automatiquement.

**Ce que ça produit** : à chaque appel `agent.run(input)`, une ligne dans
`agent_runs` avec status (success/failed) + l'output complet.

---

### Agent Gap Analyzer (`agents/gap_analyzer.py`)

**À quoi ça sert** : identifie les **angles morts** d'une marque dans les
réponses Perplexity. Réponds à la question : "sur quels prompts on est
absent ou faible, et qui nous remplace ?".

**Comment l'utiliser** :
- 1 marché : `python3 -m agents.gap_analyzer --slug betclic --language fr`
- Tous marchés : `python3 -m agents.gap_analyzer --slug betclic`
- Output JSON : ajouter `--json`

**Ce que ça produit** : la liste des prompts faibles, pour chacun les
concurrents qui dominent + les sources Perplexity à viser, plus une reco
actionnable. Sur Betclic toutes langues : 23 angles morts détectés (8 sur
régulation, 6 sur paiement, etc.).

---

### Crawlability Agent (`agents/crawlability_agent.py`)

**À quoi ça sert** : audit technique du site web cible pour vérifier qu'il
est lisible par les bots IA (GPTBot, PerplexityBot, ClaudeBot, etc.).

**Comment l'utiliser** :
- Audit pur : `python3 -m agents.crawlability_agent --slug betclic`
- Croisé avec Gap : ajouter `--with-gap`
- URL custom : `--url https://example.com`

**Ce que ça produit** : un score de crawlabilité IA (0-100), la liste des
bots qui peuvent (ou ne peuvent pas) accéder, et des recommandations
techniques (ajouter un schema FAQPage, sitemap.xml, etc.).

**Tests réels** : Betclic 25/100, PSG 50/100, horizons-le-parti.fr 17/100.

---

### Content Creator (`agents/content_creator.py`)

**À quoi ça sert** : génère le contenu (texte HTML + JSON-LD FAQPage) à
publier sur le site pour combler les angles morts détectés par le Gap
Analyzer.

**Comment l'utiliser** :
- Mode auto (utilise le Gap) : `python3 -m agents.content_creator --slug betclic --from-gap`
- Avec self-eval : ajouter `--iterate` (plus lent mais meilleurs scores)
- Limiter le nombre : `--n-items 3`
- Test sans écriture : `--dry-run`

**Ce que ça produit** : pour chaque angle mort, un paragraphe optimisé
(150-200 mots) qui mentionne la marque + un schema JSON-LD FAQPage prêt à
copier-coller dans le code source de la page. Le tout stocké dans la table
`action_items` (visible dans le dashboard via le tab Insights).

**Coût** : utilise Claude API (~0.05$ par item généré). Pour Betclic
(2 items) : ~0.10$ par run.

**Tri intelligent** : les angles morts sont traités par priorité décroissante
(score le plus bas en premier, puis catégories régulation/paiement avant les
autres).

---

### Scripts d'infra (`scripts/`)

**À quoi ça sert** : automatiser le run nocturne du tracker UI sur Mac avec
sync automatique vers PythonAnywhere.

**Fichiers** :
- `voxa_nightly.sh` : lance le tracker + sync DB → PA
- `setup_ssh_pa.sh` : configure une SSH key Mac→PA (one-shot)
- `install_cron.sh` : installe le cron 02h00 sur Mac

**Status** : créés mais pas encore activés (bloqué sur le mot de passe PA).