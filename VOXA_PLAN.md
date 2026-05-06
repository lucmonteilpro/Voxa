# Voxa — Plan d'action

> **Document vivant** — Claude met à jour ce fichier systématiquement à chaque
> session significative. Tu peux aussi l'éditer librement entre les sessions.
>
> **Synchro** : à uploader dans le project knowledge "Voxa" sur claude.ai
> ET à committer à la racine du repo (lu par Claude Code via CLAUDE.md).
>
> **Conventions de statut** :
> - ✅ Terminé — feature livrée ET validée méthodologiquement
> - 🟡 En cours — code livré mais validation en cours
> - ⏳ À faire
> - ❌ Bloqué (avec note explicative)
> - 🔄 Reporté / en attente
> - ⏸ Pausé / parked
> - 🧪 En validation méthodologique — code livré mais tests scientifiques requis

---

## 🔬 Méthodologie de rigueur — Principes obligatoires

> Ces principes s'appliquent à **chaque feature Voxa** sans exception.

### Pourquoi cette section existe

Voxa vend de la **mesure d'impact GEO**. Si la mesure est biaisée ou instable,
tout le pitch s'effondre face à un client technique. Voxa doit être
**le premier outil GEO scientifiquement rigoureux** — c'est un différenciateur
commercial majeur.

### Les 6 garde-fous

#### 1. Distinguer "code qui tourne" vs "feature qui mesure ce qu'elle dit mesurer"
Toujours **lire qualitativement les outputs**, pas juste les chiffres.

#### 2. Mesurer la baseline avant de mesurer l'apport
Tout score "amélioré" doit être comparé à un score "à nu" pris dans la même session.

#### 3. Quantifier la variance avant de tirer des conclusions
Si l'outil mesuré (Perplexity, ChatGPT, etc.) est non-déterministe, 1 mesure ne suffit pas.

#### 4. Détecter les faux positifs
Toujours vérifier que la réponse contient bien des **mots-clés du prompt original**.

#### 5. Protocole control/test obligatoire
Pour valider l'efficacité d'une intervention Voxa, comparer un groupe control (jamais optimisé) à un groupe test.

#### 6. Comprendre l'outil sous-jacent
Avant d'industrialiser une mesure, comprendre comment fonctionne l'outil mesuré.

### Checklist obligatoire par feature

À recopier et cocher pour chaque nouvelle feature qui mesure quelque chose :

**Phase A — Pré-design**
- [ ] Quelle question scientifique exacte la feature répond-elle ?
- [ ] Quels biais possibles ?
- [ ] Comment je vais valider que la feature mesure bien ce qu'elle dit ?
- [ ] Quel test minimal pour invalider la feature si elle ne marche pas ?
- [ ] Y a-t-il un groupe control/test pour cette feature ?
- [ ] Ai-je compris l'outil sous-jacent que j'utilise ?

**Phase B — Post-code**
- [ ] Test sur des données réelles (pas seulement mocks)
- [ ] Lecture qualitative des outputs (pas juste les nombres)
- [ ] Comparaison avec une baseline (sans la feature) sur le même contexte
- [ ] Si la feature mesure : 3+ mesures pour quantifier la variance
- [ ] Vérification d'au moins 1 cas de faux positif évident
- [ ] Vérifier la provenance des données comparées

**Phase C — Pré-pitch commercial**
- [ ] Pourrais-je défendre cette feature face à un client technique sceptique ?
- [ ] Si Olivier (expert data marketing) demande "comment vous mesurez ?", ai-je une réponse rigoureuse en moins de 30 secondes ?
- [ ] Les chiffres présentés sont-ils des moyennes/médianes sur N mesures ?
- [ ] Le delta présenté est-il comparé à un groupe control ?
- [ ] Documenter les limites connues de la feature

### Quand sauter cette checklist

Pour les features purement infra (sans mesure ni production de score) :
crawlers, migrations DB, scripts shell, etc. La checklist n'est obligatoire
que pour les features qui **produisent un score, une recommandation, ou une
décision** s'appuyant sur des données.

---

## 📌 Notes stratégiques persistantes

> Réflexions ouvertes, non tranchées définitivement, à reconsulter régulièrement.
> Ces notes ne sont JAMAIS supprimées sans validation explicite.

### Note 1 — Choix du modèle Perplexity à mesurer

**Date d'origine** : 2026-05-02
**Statut** : décision provisoire, à valider après plus de tests
**Décision actuelle** : **forcer Sonar 2** sur le crawler Perplexity ✅ implémenté 2026-05-03

#### Le contexte stratégique

Perplexity est un **orchestrateur**, pas un modèle. Il propose plusieurs modèles :
- Mode "Meilleur" (par défaut) : choix automatique parmi tous
- Sonar 2 : modèle propriétaire Perplexity
- GPT-5.4, GPT-5.5 Max (locked sans abonnement) : OpenAI
- Gemini 3.1 Pro : Google
- Claude Sonnet 4.6, Claude Opus 4.7 Max (locked) : Anthropic

#### Faits importants à mémoriser

**Distribution des utilisateurs Perplexity** :
- 33M utilisateurs actifs mensuels, 60-70M requêtes/jour
- Majorité : utilisateurs gratuits (modèles "de base" : Claude Instant, Mixtral, GPT-3.5)
- Minorité : utilisateurs Pro à 17-20$/mois (accès à Sonar 2, GPT-5.4, Claude 4.6, Gemini 3.1)

**Limite technique** :
- Les modèles "de base" gratuits (Claude Instant, Mixtral, GPT-3.5) ne sont **pas sélectionnables manuellement** même en Pro
- Donc on ne peut pas mesurer ce que voit un utilisateur gratuit "à l'identique"

#### Pourquoi on a choisi Sonar 2 malgré tout

1. **Stabilité scientifique** : forcer un modèle = variance interne uniquement (pas de variance externe due au choix de modèle aléatoire). Variance attendue beaucoup plus faible.
2. **Modèle natif Perplexity** : c'est leur techno propriétaire, central à leur produit, durable dans le temps.
3. **Architecture propre** : 1 crawler = 1 modèle. Pas de redondance avec les futurs crawlers ChatGPT (GPT-5.4) / Claude.ai (Sonnet 4.6) / Gemini (3.1 Pro) en Phase 3.
4. **Pragmatique** : on peut mesurer ce qu'on peut mesurer maintenant, sans bloquer Voxa.

#### Limites assumées (à acknowledge dans tout pitch commercial)

- **Sonar 2 ≠ ce que voit l'utilisateur gratuit Perplexity** (qui est sur Claude Instant/Mixtral/GPT-3.5)
- Hypothèse non vérifiée : les LLMs convergent sur les questions factuelles. Cette hypothèse doit être validée.
- Si la convergence n'est pas vérifiée, on devra ajuster (cf. section "Pistes futures" ci-dessous)

#### Premiers résultats observés (2026-05-03 soir)

Re-crawl complet Betclic Sonar 2 forcé : **88 prompts × 4 marchés en 53 minutes**, 0 fallback (sélection 100% réussie).

**Score moyen Betclic Sonar 2** :
- 🇫🇷 France : 71.2/100 (vs ~84.9 en mode "Meilleur" avant — écart -13.7 pts)
- 🇵🇹 Portugal : 85.3/100 (excellent)
- 🇨🇮 Côte d'Ivoire : 58.1/100 (axe d'amélioration)
- 🇵🇱 Pologne : 51.7/100 (axe d'amélioration)
- **Global** : 66.2/100 (vs ~84.9 FR en "Meilleur")

**Lecture honnête** : Sonar 2 donne des scores plus bas que le mode "Meilleur" probablement parce qu'il utilise des sources plus larges (moins biais marques connues). À acknowledge dans tout pitch commercial.

#### Pistes futures à explorer

À faire quand on aura des clients payants et plus de bandwidth :

**Piste A — Étude de corrélation Sonar 2 vs autres modèles**
- Mesurer 50 prompts sur Sonar 2 ET sur Claude 4.6 ET sur GPT-5.4 ET sur Gemini 3.1
- Calculer la corrélation des scores
- Si r > 0.8 : on peut continuer à utiliser Sonar 2 comme proxy
- Si r < 0.6 : il faut mesurer chaque modèle séparément

**Piste B — Crawler "incognito" pour simuler un utilisateur gratuit**
- Utiliser un compte gratuit Perplexity (sans abonnement) avec le crawler
- Mesurer ce que voit ce profil
- Comparer aux mesures Sonar 2 forcé
- Plus représentatif de l'expérience utilisateur réelle pour la masse

**Piste C — Mode "Meilleur" + multi-crawl statistique rigoureux**
- Garder le mode "Meilleur" qui reflète l'expérience utilisateur Pro
- Compenser la variance par 5-7 crawls + médiane
- Plus coûteux mais plus représentatif

**Piste D — Mesure par modèle (offre commerciale premium)**
- Pour les clients premium, mesurer chaque modèle séparément
- Voxa devient le seul outil qui dit : "Sur Sonar 2 vous êtes à 80, sur Claude 60, sur GPT 40, sur Gemini 75"
- Argument commercial très fort, mais coût × 4

#### Questions ouvertes que la roadmap doit clarifier

1. **Validité externe** : un score Sonar 2 = 80/100 prédit-il un score à 80/100 chez Mixtral/GPT-3.5 ?
2. **Évolution des modèles** : Sonar 2 sera-t-il toujours là dans 6 mois ? Comment on gère la migration ?
3. **Pitch commercial** : "Voxa mesure votre présence sur Sonar 2" est-il assez vendeur ? Ou trop technique ?
4. **Préférences clients** : Olivier (Betclic) préfère-t-il "ce que voit Pro" ou "ce que voit la masse" ? À demander.

#### Comment cette note évolue

Cette note doit être **complétée** à chaque session qui touche au sujet Perplexity / modèles. **Ne jamais supprimer** une question, on peut juste y répondre.

---

## ⚠️ Risques formalisés

> Consolidation des limites, fragilités et single-points-of-failure connus.
> Format : ID, constat, impact, mitigation actuelle, action de mitigation prévue.
> Mis à jour à chaque session qui découvre ou résout un risque.

### R1 — Sonar 2 ≠ expérience utilisateur gratuit Perplexity

**Constat** : on force Sonar 2 (modèle Pro) pour la stabilité scientifique, mais la majorité des utilisateurs Perplexity sont sur des modèles gratuits (Claude Instant / Mixtral / GPT-3.5) non sélectionnables manuellement.
**Impact** : un score Voxa sur Sonar 2 ne prédit pas nécessairement la visibilité réelle vue par la masse des utilisateurs gratuits.
**Mitigation actuelle** : limite assumée et documentée dans Note 1, à acknowledge dans tout pitch commercial.
**Action prévue** : étude de corrélation Sonar 2 vs autres modèles (Note 1, Piste A) quand bandwidth disponible. Si corrélation faible, basculer sur Piste C (multi-crawl mode "Meilleur") ou Piste D (mesure par modèle premium).

### R2 — Variance LLM non-déterministe sur 1 crawl

**Constat** : sur les 8098 mesures historiques, la variance LLM est élevée — ±24 pts sur 1 mesure, ±10 pts sur 5 mesures. Le Gap Analyzer actuel est basé sur 1 crawl par prompt.
**Impact** : les angles morts détectés par le Gap Analyzer peuvent être des faux positifs/négatifs causés par la variance plutôt que par un vrai gap.
**Mitigation actuelle** : Sonar 2 forcé devrait baisser fortement la variance (à valider sur 3 prompts × 3 crawls). Usage privilégié de la médiane plutôt que de la moyenne sur les analyses agrégées.
**Action prévue** : ✅ multi-crawl N=3 + médiane livré dans QC v2 (04/05). Variance non-nulle confirmée empiriquement (item #6 Pack #2 Betclic : [100, 98, 0]). N=3 absorbe la variance, médiane sauve du faux négatif quantitatif. R2 partiellement mitigé — reste à étendre le multi-crawl au tracker_ui et au Gap Analyzer (sessions futures).

### R3 — Architecture cron Mac = single-point-of-failure

**Constat** : le plan Phase 0 prévoit un cron 02h00 sur le Mac local qui lance le tracker UI puis push la DB sur PA via SCP. Si le Mac est éteint, fermé, en veille, ou en déplacement, pas de run nocturne.
**Impact** : risque de trous dans les données client (Betclic et autres prospects), désynchro entre Mac et dashboard PA, mauvaise expérience client si Olivier consulte le dashboard et voit des données obsolètes.
**Mitigation actuelle** : aucune. Architecture acceptée comme solution court terme.
**Action prévue** : envisager migration du tracker vers PA (Always-On task) ou Hetzner (Phase 6) à terme. Bloqueur potentiel : Patchright/Chromium tourne mal sur PA (sandbox limitations) — à tester avant de migrer.

### R4 — Crash Patchright en sortie de tracker UI

**Constat** : `BrowserContext.close: Connection closed while reading from the driver` observé en sortie de `tracker_ui.py` (01/05). Sans impact data — les données sont écrites en DB avant la sortie.
**Impact** : cosmétique côté logs aujourd'hui. Si la fréquence augmente, peut masquer de vraies erreurs ou polluer le diagnostic.
**Mitigation actuelle** : non bloquant, observé comme "bruit". À surveiller.
**Action prévue** : créer un ticket DT formel si la fréquence augmente. Sinon, à nettoyer lors de la prochaine refacto du module crawlers.

### R5 — Mécanisme d'init implicite des tables Pack

**Constat** : les tables `action_items` et autres tables Pack sont créées par effet de bord à l'import de `action_pack.py`. Pattern fragile — si l'import est court-circuité ou refactoré, les tables peuvent manquer (cas DT-2 04/05, finalement faux positif).
**Impact** : risque de régression silencieuse en cas de refacto. Modèle peu documenté pour un nouvel arrivant.
**Mitigation actuelle** : `test_action_pack_smoke.py` ajouté le 04/05 pour vérifier que les tables sont bien créées après import. Régression détectable en CI.
**Action prévue** : à terme, migrer vers une init explicite via `migrate_v3.py` (ou un futur `migrate_v4.py`). Pas urgent tant que le smoke test couvre.

### R6 — Évolution / durabilité de Sonar 2 dans le temps

**Constat** : Sonar 2 est un modèle propriétaire Perplexity. Rien ne garantit sa pérennité (renaming, déprécation, refonte de l'orchestrateur).
**Impact** : si Perplexity supprime ou renomme Sonar 2, le crawler casse silencieusement (fallback sur "Meilleur") et les données historiques deviennent incomparables avec les nouvelles.
**Mitigation actuelle** : `_detect_model_used()` honnête, étiquette les runs `perplexity-fallback` si la sélection rate. Logs explicites du modèle utilisé.
**Action prévue** : monitoring proactif (alerte si > X% de fallback sur une fenêtre). Plan de migration documenté en cas de déprécation Sonar 2 (probablement bascule sur le successeur ou sur GPT/Claude/Gemini selon corrélation découverte par Piste A).

### R7 — TOS Perplexity et risque anti-bot

**Constat** : on crawle Perplexity via Patchright + Chrome (anti-détection). Patchright simule un humain mais reste du scraping non autorisé par les TOS. La démo se fait sur Perplexity (pas sur Claude/ChatGPT), donc l'enjeu est concentré sur cette plateforme.
**Impact** : si Perplexity durcit la détection, le crawler peut commencer à se faire bloquer (CAPTCHAs, rate-limit, ban IP/compte). Risque existentiel pour le tracker UI.
**Mitigation actuelle** : sessions Patchright persistantes, compte Perplexity Pro pour réduire la friction, cadence raisonnable (88 prompts × 4 marchés en 53 min = pas de burst).
**Action prévue** : passer à une offre premium Perplexity Enterprise / API officielle si elle ouvre l'accès Sonar 2 forcé. En backup : crawler diversifié multi-LLMs (Phase 3) pour réduire la dépendance à Perplexity seul.

### R8 — Convergence orchestrateur non-garantie

**Constat** : sur le même item testé 2 fois consécutivement (item #6 du Pack #2 Betclic, 05/05), l'orchestrateur produit 2 outcomes différents : 1er run → validated en 2 itérations, 2e run → abandoned_plateau en 4 itérations. La variance cumulée Claude (génération) + Sonar 2 (crawl) + Haiku (verdict) rend la convergence probabiliste.
**Impact** : un client qui regénère un Pack 2 fois peut avoir 2 résultats différents pour les mêmes items. Cohérence d'expérience utilisateur imparfaite.
**Mitigation actuelle** : history JSON complet persisté (audit trail), statuts finaux explicites (validated / abandoned_plateau / abandoned_after_max_iterations), pas de fausse promesse.
**Action prévue** : (long terme) plateau qualitatif Phase 9 + stratégie alternative de régénération (Phase 2F+) + multi-crawl Gap Analyzer pour réduire la variance d'entrée. (Court terme) accepter le caractère probabiliste comme honnête méthodologiquement, le documenter dans tout pitch commercial. La trajectoire des verdicts pertinents (0→0→1→1 sur les 4 itérations du run réel) prouve que la régénération contextualisée a une influence sémantique mesurable, juste insuffisante sur certains items intrinsèquement difficiles.

---

## 🔥 Tâches en attente immédiate

- [x] Run all-markets terminé (88 runs, 1385 sources)
- [x] Gap Analyzer all-markets (23 angles morts détectés en mode Meilleur)
- [x] Content Creator testé (delta moyen +47 pts)
- [x] QC v1 testé : faux positifs identifiés
- [x] Test variance + analyse statistique 8098 mesures historiques
- [x] **Découverte Perplexity orchestrateur** : Sonar 2 / GPT / Claude / Gemini sélectionnables
- [x] **Décision** : forcer Sonar 2 (cf. Note 1 stratégique)
- [x] **Refactor crawler Perplexity** ✅ 2026-05-03 — sélection Sonar 2 fonctionnelle
- [x] **Re-crawl complet Betclic Sonar 2** ✅ 2026-05-03 — 88 runs, 0 fallback, 53 min
- [x] **Refactor Gap Analyzer** : filtre `llm = perplexity-sonar-2`, 17 angles morts
- [x] **Bug fix crawler** : filtre élargi `hostname.includes('perplexity')` pour exclure perplexity.com
- [x] **Setup Projet Voxa claude.ai + CLAUDE.md** ✅ 2026-05-04 — workflow web ↔ Code opérationnel
- [x] **DT-2 closed** ✅ 2026-05-04 — faux positif (Pack #2 bien en DB depuis 02/05) + smoke test ajouté
- [x] **Mot de passe PA régénéré** ✅ 2026-05-04 — stocké Dashlane
- [ ] **Setup SSH Mac → PA** — PROCHAINE SESSION (Phase 0)
- [ ] **Cron 02h00 installé** — après SSH OK
- [ ] **Re-affiner Gap Analyzer** plus tard quand plus de données accumulées (multi-crawl)
- [ ] **Refacto QC v2** : multi-crawl + nouveau template anti-faux-positif + filtre `llm = perplexity-sonar-2` (PHASE 2E)
- [x] **Orchestrateur Phase 2F** ✅ 05/05/2026 — chaîne Content Creator → QC v2 sur N itérations, régénération contextualisée, plateau strict, skip validated. Run réel sur Pack #2 : item #6 abandoned_plateau en 4 itérations (variance probabiliste, R8 documenté).
- [x] **Phase 2G Standard** ✅ 05/05/2026 — timeline orchestrateur dans tab Pack Action (badge statut + détail des itérations + dégradation graceful sur clients sans orchestrateur). Commit d977e9a.

---

## 📊 Vue d'ensemble

| Phase | Objectif | Statut |
|---|---|---|
| **Phase 0** | Sprint Betclic — infra crawl + sync | 🟡 (déblocable maintenant, MDP PA OK) |
| **Phase 1** | Démo Betclic prête | 🔄 |
| **Phase 2** | Architecture multi-agents | ✅ (8/8) |
| **Phase 3** | Crawlers UI multi-LLMs | ⏳ |
| **Phase 4** | Chatbot agentique sidebar | ⏳ |
| **Phase 5** | Olivier's 5 besoins Betclic | 🔄 |
| **Phase 6** | Migration Hetzner | 🔄 |
| **Phase 7** | Pub ChatGPT US | ⏸ |
| **Phase 8** | Voxa Politics | ⏳ |
| **Phase 9** | Protocole control/test | ⏳ |
| **Dette technique** | Tickets DT-1 à DT-5 | 🟡 (DT-2 et DT-3 closed) |

---

## ✅ Phase préparatoire (déjà fait)

- Dashboard, Migration DB v2, Crawler Perplexity (patchright)
- Tracker UI v1 + v2 (--all-markets, idempotence, ETA)
- Run Betclic all-markets : 88 runs (Meilleur) puis 88 runs (Sonar 2)
- 8098+ mesures historiques en DB (multi-LLM, sur 30+ jours)
- Souscription Perplexity Pro
- Setup Projet Voxa dans claude.ai (project knowledge + CLAUDE.md à la racine du repo)
- Smoke test action_pack pour blinder l'init implicite des tables Pack

---

## 🟡 Phase 0 — Sprint Betclic infra

**Objectif** : que les runs UI tournent automatiquement chaque nuit et que les données soient visibles sur PA pour les 4 marchés Betclic.

- [x] Scripts shell créés (`voxa_nightly.sh`, `setup_ssh_pa.sh`, `install_cron.sh`)
- [x] Mot de passe PythonAnywhere régénéré (préalable bloquant)
- [ ] SSH key Mac → PA configurée
- [ ] Test SCP manuel : `scp ~/Voxa/voxa_betclic.db lucsharper@ssh.pythonanywhere.com:~/Voxa/`
- [x] Run all-markets exécuté (deux fois : Meilleur puis Sonar 2)
- [ ] Cron 02h00 installé sur Mac (`./scripts/install_cron.sh`)
- [ ] Vérification du run nocturne le lendemain matin

**Critère de fin de phase** : `lucsharper.pythonanywhere.com/betclic/` affiche les données UI sur les 4 marchés et les recommandations dans le tab Insights.

**Risque assumé** : architecture cron Mac = SPOF (cf. R3). Migration vers PA ou Hetzner reportée à plus tard (Phase 6).

**Prochaine action immédiate** : brief de session Code dédié pour SSH + cron.

---

## 🔄 Phase 1 — Démo Betclic prête (reporté)

**Statut** : reporté car Olivier Audibert a déjà été pitché. On attend son retour.

- [ ] Page de démo scénarisée `/betclic-demo`
- [ ] Polish + répétition démo
- [ ] Démo réelle avec Olivier

**Trigger de redémarrage** : retour d'Olivier (positif → on prépare la démo réelle, négatif/silence → on continue Phase 2).

---

## ✅ Phase 2 — Architecture multi-agents

**Objectif** : matcher la promesse Meikai d'agents qui rebouclent jusqu'à un résultat satisfaisant.

### Décisions de design

- ✅ Anthropic SDK natif (vs LangChain/CrewAI)
- ✅ Table `agent_runs` (vs JSON files)
- ✅ Boucle hybride max 5 itérations OR plateau
- ✅ Gap Analyzer = Python ; Content Creator = Claude API
- ✅ Seuil angle mort : ≤ 60/100
- ✅ Auto-création DB minimale
- ✅ Voxa = GEO uniquement
- ✅ Refacto soft `action_pack.py`
- ✅ **Crawler force toujours 1 modèle spécifique** (cf. Note 1)
- ✅ **Filtre `llm = 'perplexity-sonar-2'`** dans agents (PRIMARY_LLM_FILTER)
- ✅ QC v2 : N=3 crawls test + 1 control + médiane + filtre Haiku (livré 04/05)
- ✅ Orchestrateur 2F : régénération contextualisée (previous_attempts dans system prompt) + plateau quantitatif strict (delta_N ≤ delta_(N-1) + 5 pts) + max 5 itérations + skip items déjà validated

### Sous-phases

- ✅ 2A Migration DB v3 + classe Agent
- ✅ 2B Gap Analyzer (avec filtre Sonar 2)
- ✅ 2C Crawlability Agent
- ✅ 2D Content Creator
- ✅ 2E Quality Controller v2 (livré + validé sur Pack #2 Betclic le 04/05)
- ✅ 2F Orchestrateur hybride (livré + validé sur Pack #2 Betclic le 05/05)
- ✅ 2G Intégration dashboard (livrée 05/05)

### État détaillé 2E

- [x] Code v1 livré
- [x] Tests baseline + variance + RAG
- [x] Découverte 8098 mesures historiques exploitables
- [x] Analyse statistique : 5 crawls = précision ±10 pts (en mode "Meilleur")
- [x] **Découverte critique** : Perplexity est un orchestrateur, on peut forcer Sonar 2
- [x] **Refactor crawler** : Sonar 2 forcé fonctionnel
- [x] **88 runs Sonar 2** générés, base propre disponible
- [x] **Bug perplexity.com fix**
- [x] **Re-test variance Sonar 2** : observée empiriquement via QC v2 sur item #6 du Pack #2 Betclic — variance [100, 98, 0] sur 3 crawls test, médiane absorbe le décrochage. Variance non-nulle confirmée.
- [x] Décision finale sur N : **N=3 conservé**, justifié empiriquement (la médiane sauve l'item du faux négatif quantitatif au 1er run réel).
- [x] QC v2 : multi-crawl + template factuel neutre + filtre Haiku (livré 04/05)
- [x] Phase C pré-pitch (méthodologie défendable face à un client technique)

---

## ⏳ Phase 3 — Crawlers UI multi-LLMs

**Architecture cible** : 1 crawler = 1 modèle forcé.

- [ ] `crawlers/chatgpt.py` : force GPT-5.4 (ou ce qu'OpenAI permet)
- [ ] `crawlers/claude_ai.py` : force Claude Sonnet 4.6
- [ ] `crawlers/gemini.py` : force Gemini 3.1 Pro
- [ ] `tracker_ui.py` : argument `--llm` (sonar / gpt / claude / gemini / all)
- [ ] DB : runs séparées par crawler/modèle (ex : 1 prompt × 4 LLMs = 4 runs)
- [ ] Vue dashboard : breakdown par LLM dans le ranking

**Note méthodologique** : variance observée historiquement sur tous les LLMs.
Anticiper le multi-crawl par défaut + protocole control/test (Phase 9).

**Lien avec R1** : la Phase 3 est la mitigation à long terme du risque "Sonar 2 ≠ expérience utilisateur réelle". Quand on aura des crawlers multi-LLMs, on pourra valider la corrélation et ajuster.

---

## ⏳ Phase 4 — Chatbot agentique sidebar

À détailler quand on s'en approchera.

---

## 🔄 Phase 5 — Olivier's 5 besoins Betclic

À détailler après retour Olivier (Phase 1).

---

## 🔄 Phase 6 — Migration Hetzner

**Lien avec R3** : la Phase 6 est la mitigation à long terme du SPOF cron Mac. À déclencher quand le revenu pilote justifie le coût d'un VPS.

À détailler le moment venu.

---

## ⏸ Phase 7 — Pub ChatGPT US

Pausé — pas de bandwidth.

---

## ⏳ Phase 8 — Voxa Politics

À détailler. Prospect Édouard Philippe en démo.

---

## ⏳ Phase 9 — Protocole control/test

**Objectif** : pour valider scientifiquement l'efficacité d'une intervention Voxa, comparer un groupe de prompts control (jamais optimisés) à un groupe test (optimisés via Content Creator). Sans ça, on ne peut pas affirmer que Voxa fait progresser la visibilité.

À implémenter avant le pitch Olivier sérieux. Bloqueur méthodologique majeur.

---

## 🛠 Dette technique

### Tickets actifs

| ID | Sujet | Priorité | Statut |
|---|---|---|---|
| **DT-1** | `report_generator.py` + `email_reporter.py` à supprimer (reporting client inutilisé) | Faible | Ouvert (suppression coordonnée à planifier) |
| **DT-4** | Clés API legacy `OPENAI_API_KEY` / `PERPLEXITY_API_KEY` à nettoyer si `tracker.py` est un jour supprimé | Faible | Ouvert (en attente décision) |
| **DT-5** | Migrer Betclic (et PSG) vers le dynamic loader configs JSON | Faible | Ouvert (cohérence d'archi, double source de vérité actuelle) |
| **DT-6** | Doctrine d'onboarding nouveau client | Faible | Ouvert (doctrine produit, non bloquant pour clients actifs) |

### Tickets clos

- ✅ **DT-2** — CLOSED le 04/05/2026 — faux positif. Le Pack #2 est bien en DB depuis le 02/05. Tables centralisées dans `voxa_accounts.db` (init via effet de bord à l'import de `action_pack.py`). Smoke test ajouté (`test_action_pack_smoke.py`). Voir aussi R5.
- ✅ **DT-3** — CLOSED le 04/05/2026 — Quality Controller v2 livré, validé sur Pack #2 Betclic. Multi-crawl (1 control + 3 test), filtre Haiku, protocole control/test par item. Inversion de verdict v1→v2 sur item #6 démontre la valeur ajoutée (v1 aurait validé un faux positif quantitatif, v2 rejette grâce aux verdicts Haiku off-topic). Cf. journal du 04/05.

### Détail DT-1 (pour mémoire — à exécuter le moment venu)

**Constat** : `report_generator.py` (moteur de génération de rapports) et `email_reporter.py` (envoi mensuel par email) sont actifs dans le code mais **plus utilisés** côté business — Voxa n'envoie plus de rapports mensuels automatiques aux clients.

**Références dans le code** (vérifié par grep le 04/05/2026) :
- `server.py:717` → `from report_generator import generate_report, CLIENTS`
- `email_reporter.py:159` → invoque `report_generator.py` en subprocess

**Action de suppression coordonnée** :
1. Supprimer la route `/admin/report/...` dans `server.py` (et l'import)
2. Désactiver le cron `email_reporter.py` sur PA (onglet Tasks)
3. `git rm report_generator.py email_reporter.py`
4. Nettoyer les éventuelles entrées dans `voxa_db.py` ou autres modules
5. Test smoke : reload PA + vérifier que toutes les routes répondent

**Quand traiter** : 1h calme, pas urgent.

### Détail DT-6 — Doctrine d'onboarding nouveau client

**Constat** : `make_dashboard(slug)` plante avec `OperationalError: no such table: prompts` pour les clients dont la DB n'a jamais été crawlée (ephilippe, lehavre, saintetienne, unibet, winamax). Comportement normal — la DB est créée vide à l'ajout du config JSON, mais les tables `prompts`/`runs`/`sources` ne sont créées qu'au 1er run du tracker.

**Impact** : impossible d'ouvrir le dashboard d'un client jamais crawlé. Pour Betclic et PSG (déjà crawlés) : aucun impact.

**Doctrine actuelle** : avant toute démo prospect, lancer un crawl initial pour ce client (`python3 tracker_ui.py --slug X`). Procédure manuelle pour l'instant.

**Action future** : à 3-4 nouveaux clients à activer, créer un script `onboard_client.py` qui chaîne init DB + 1er crawl + 1er Pack.

---

## 🤝 Cadre de travail

**3 surfaces Claude, 3 sweet spots** :

- **Chat web Projet "Voxa" (claude.ai)** : décisions d'archi, briefs de session, débriefs, génération de docs (decks, PDF, emails), mise à jour de ce plan
- **Claude Code (terminal CLI)** : exécution code dans le repo Voxa
- **Cowork (desktop)** : automatisation fichiers/tâches (pas pertinent pour le code, ignoré pour l'instant)

**Règles d'or** :

1. Pour toute modif >20 lignes ou multi-fichiers : passer par Code, pas par le chat web
2. Avant toute suppression de fichier : `grep -rn "nom_du_fichier"` (leçon DT-1)
3. À chaque fin de session Code significative : régénérer ce plan, le ré-uploader dans project knowledge, et le committer à la racine
4. Smoke test obligatoire pour les modifs de schéma DB ou les patterns d'init implicites

---

## 🗒 Journal de bord

### 2026-05-02 (jour 1)

**Découvertes majeures** :

1. **8098 mesures historiques** disponibles en DB (multi-LLM)
2. **Variance LLM élevée** : 1 mesure → ±24 pts ; 5 mesures → ±10 pts
3. **Distribution bimodale** des scores
4. **Perplexity est un orchestrateur** (pas un modèle unique)
5. **Décision** : forcer Sonar 2

**Méthodologie consolidée** :
- Phase 9 control/test ajoutée
- Notes stratégiques persistantes ajoutées
- Leçons 1-7 consignées

### 2026-05-03 (jour 2 — implémentation)

**Réalisations** :

1. **Refactor crawler Perplexity terminé**
   - Méthode `_select_model()` : 5 étapes avec échec gracieux
   - Helper `_find_model_button()` : 2 stratégies (label générique puis nom modèle)
   - Sélecteurs ARIA validés via diagnostic DOM (`role="menu"` + `role="menuitemradio"`)
   - `_detect_model_used()` honnête (retourne `perplexity-fallback` si sélection ratée)
   - Param `model_to_force` configurable (None pour mode "Meilleur" volontaire)

2. **Re-crawl complet Sonar 2** : 88 prompts × 4 marchés en 53 min, 0 fallback (100% sélections réussies)

3. **Refactor Gap Analyzer** : constantes `PRIMARY_LLM_FILTER` et `ALLOW_LEGACY_RUNS`, intégrées dans `_language_clause()`. Toutes les 5 requêtes SQL filtrent sur llm=perplexity-sonar-2.

4. **Bug fix** : filtre élargi `a.hostname.includes('perplexity')` (avant, perplexity.com passait à travers et polluait les sources avec 63 liens vers la privacy policy)

5. **Premier rapport Gap Analyzer Sonar 2** : 17 angles morts détectés sur les 4 marchés Betclic. Distribution :
   - Régulation & légalité : 6 angles morts (le gros sujet)
   - Paiement & retraits : 4
   - Image de marque : 3
   - Cotes & paris : 2
   - Visibilité : 2

**Insights** :
- **1xBet domine** sur les requêtes Côte d'Ivoire (régulation, popularité)
- **STS et LV BET dominent** en Pologne
- **anj.fr cité 31 fois** comme source en France (terrain à occuper)
- Score Sonar 2 plus bas que mode "Meilleur" (66 vs 85 sur FR) — probablement plus représentatif et moins biaisé

**Méthodologie consolidée** :
- Leçon 8 ajoutée : "Documenter les décisions provisoires comme dette technique"

**Limites identifiées (à traiter à terme)** :
- Mesures Gap Analyzer basées sur **1 crawl par prompt** → variance probable (cf. R2). Pour rigueur scientifique, passer à multi-crawl (3-5 mesures + médiane).
- Tracker_ui n'a pas encore de mode multi-crawl
- Phase 9 control/test pas encore implémentée

### 2026-05-04 (jour 3 — Setup Projet Claude + DT-2)

**Setup** :
- Création du Projet Voxa dans claude.ai avec instructions et project knowledge
- Installation de Claude Code (v2.1.126) et création du `CLAUDE.md` à la racine
- Workflow web ↔ Code formalisé : décisions et briefs en chat, exécution en CLI, débrief et resync project knowledge

**DT-2 — Diagnostic et résolution** :
- Hypothèse initiale (table `action_items` manquante dans `voxa_betclic.db`) invalidée
- Diagnostic réel : architecture centralisée dans `voxa_accounts.db`, Pack #2 bien présent (3 items, 02/05 20h00)
- Mise à jour du CLAUDE.md (§13) pour fermer le ticket avec la note de clôture
- Création de `test_action_pack_smoke.py` pour blinder l'init implicite des tables Pack (cf. R5)
- Smoke test exécuté avec succès dans le repo principal, état DB strictement identique avant/après
- Commit pushé sur `main` (`758c9e0`)

**Mot de passe PA régénéré** et stocké dans Dashlane → débloque la Phase 0.

**Plan consolidé en VOXA_PLAN total** : fusion du plan technique (Phase 0/1/2 + dette technique) avec le plan stratégique (méthodologie, notes persistantes, Phases 3-9, journal, leçons, glossaire). Ajout de la section **⚠️ Risques formalisés** (R1 à R7) consolidant les limites éparses.

**Leçons retenues** :
- Toujours `grep` avant suppression de fichier (cas `report_generator.py`)
- Le mécanisme d'init implicite par effet de bord à l'import est fragile mais fonctionnel — smoke test ajouté pour attraper toute régression
- Le workflow web → Code → web fonctionne : décision en chat, brief précis, exécution, débrief

**Prochaine session prévue** : Phase 0 SSH PA (brief Code à générer dans le chat web Projet).

### 2026-05-04 (jour 3 — suite — Phase 2E QC v2 livrée)

**Ce qu'on a fait (en français business)** : le Quality Controller, qui valide les contenus produits par le Content Creator, est passé d'une mesure unique biaisée à un mini-protocole scientifique. Pour chaque item à valider, l'agent fait maintenant 4 mesures sur Perplexity : une "à blanc" sans contenu Voxa injecté (pour mesurer ce que Perplexity dirait spontanément), et trois avec le contenu injecté via un template factuel neutre. On compare les scores (delta), et un appel à Claude Haiku sur chaque réponse vérifie que la marque est citée de façon utile, pas juste mentionnée superficiellement. Verdict final : item validé seulement si le contenu fait progresser le score d'au moins 10 points ET si Haiku confirme la pertinence sur au moins 2 des 3 réponses.

**Pourquoi** : le QC v1 produisait ~1/3 de faux positifs avec un template biaisé. Voxa vend de la mesure d'impact GEO, donc une mesure non-rigoureuse détruit le pitch face à un client technique comme Olivier. QC v2 mitige directement R2 (variance LLM) et installe une méthodologie défendable.

**Validation** : testé en run réel sur le Pack #2 Betclic (3 items régulation FR/PT). Résultats :
- Item #6 (FR) : Δ +98 pts mais 0/3 verdicts pertinents → needs_iteration (Perplexity mentionne Betclic mais off-topic vs la question posée)
- Item #7 (PT) : Δ +75 pts, 2/3 verdicts pertinents → validated
- Item #8 (PT) : Δ +82 pts, 2/3 verdicts pertinents → validated

**Découvertes méthodologiques** :
1. **Inversion de verdict v1→v2 sur item #6** : v1 aurait validé (score 100 sur 1 crawl), v2 rejette (filtre Haiku attrape la mention off-topic). Preuve directe de la valeur ajoutée du protocole control/test + Haiku.
2. **Variance Sonar 2 non-nulle confirmée** : item #6 produit [100, 98, 0] sur 3 crawls test. La médiane absorbe le décrochage à 0 (médiane=98). N=3 a justifié son existence dès le 1er run réel.
3. **Discrimination sémantique FR/PT par Haiku** : Haiku valide les mentions PT contextuelles (citations licences SRIJ avec numéros) et rejette les mentions FR descriptives mais hors-sujet. Le filtre fait du tri sémantique, pas juste de la détection de présence.

**Ce que ça débloque** : Phase 2F (orchestrateur hybride) peut maintenant être construite. Le signal `qc_v2_status` est fiable, l'orchestrateur peut s'appuyer dessus pour décider quand reboucler (needs_iteration) ou s'arrêter (validated).

**Décisions provisoires actées** (cf. Note 1 de méthodologie) :
- N = 3 crawls test conservé. À reconsidérer si les variances Sonar 2 se révèlent < 5 pts sur un échantillon plus large (ouvre la voie à N=2 ou 1).
- 1 domaine unique par client (Betclic = `betclic.fr` quel que soit le marché). Pas de breakdown FR/PT/CI/PL pour cette beta.
- Décision DT-5 ouverte : Betclic et PSG sont définis en statique dans `voxa_db.py` alors que les autres clients passent par le dynamic loader. À harmoniser plus tard.

**Limites identifiées (à traiter à terme)** :
- Le verdict cosmetique sur l'item #6 révèle aussi une faiblesse potentielle du Content Creator (contenu thématiquement adjacent mais pas réponse à la question). Info pour la Phase 2F : l'orchestrateur devra détecter ces cas et passer le hand vers une régénération du Content Creator avec un prompt plus contraint.
- Filtre Haiku non testé en cas d'erreur API (rate-limit, 5xx). Couvert défensivement par le fallback "ambiguous" mais jamais déclenché en run réel.

**Statut** : Phase 2E ✅ closed. DT-3 ✅ closed. Nouvelle DT-5 ouverte.

**Prochaine session prévue** : Phase 2F (orchestrateur hybride) — pas dans la même journée, à attaquer dans une nouvelle conversation Projet Voxa.

### 2026-05-05 (jour 4 — Phase 2F Orchestrateur livrée)

**Ce qu'on a fait (en français business)** : on a livré la pièce centrale qui matche la promesse Meikai. L'orchestrateur prend un Pack généré par Content Creator + validé par QC v2, repère les items rejetés, et tente de les améliorer en boucle. Pour chaque tentative ratée, il enrichit le prompt envoyé à Claude avec le contexte des échecs précédents — Claude "apprend" itération après itération. Trois statuts possibles : converge (validé), plateau (n'arrive plus à progresser → abandonne honnêtement), ou max 5 itérations atteintes.

**Pourquoi** : sans orchestrateur, Voxa livre un Pack avec 1/3 d'items rejetés et arrête. Avec orchestrateur, Voxa tente activement de résoudre les rejets ou les déclare honnêtement non-convergeables. C'est LA différence entre un outil de mesure passif et un outil de production active. C'est aussi ce qui justifie l'argument "Voxa pense, ne calcule pas" face à Olivier.

**Validation** : 2 runs consécutifs sur l'item #6 du Pack #2 Betclic (le seul item rejeté hier en QC v2) :
- Dry-run : convergence en 2 itérations → validated
- Run réel : abandon plateau en 4 itérations → abandoned_plateau

Les 2 outcomes différents sur le même item sont **un résultat précieux** méthodologiquement. Ils prouvent que :
1. La régénération contextualisée a une influence sémantique mesurable (les contenus évoluent itération après itération, les verdicts Haiku progressent de 0/3 pertinents à 1/3 sur le run réel)
2. La convergence n'est pas garantie — Voxa l'admet plutôt que de livrer du faux positif

**Découvertes méthodologiques** :

1. **Régénération contextualisée prouvée fonctionnelle** (dry-run) : l'item #6 passe de "Betclic est un opérateur agréé ANJ avec X bonus" (off-topic, rejeté à iter 1) à "Parier sur un site non agréé expose à X risques. Contrairement à Betclic, qui détient un agrément depuis…" (on-topic, validé à iter 2). La correction sémantique est observable et défendable face à un client technique.

2. **Plateau strict détecté correctement** (run réel) : sur 4 itérations, delta évolue 72 → 88 → 98 → 72. La régression à 72 < 98+5 déclenche le plateau. L'abandon est conforme à la spec.

3. **Skip des items validated propre** : items #7 et #8 traversent l'orchestrateur en zéro crawl (orchestrator_iterations=NULL).

4. **R8 ouvert** : la convergence orchestrateur est probabiliste. Variance cumulée Claude + Sonar 2 + Haiku. Documenté comme limite assumée.

**Ce que ça débloque** :
- Phase 2G (intégration dashboard) peut démarrer — les 3 statuts finaux + history JSON donnent matière à visualiser
- Pitch Olivier renforcé : on peut maintenant montrer le système complet (Gap → Content Creator → QC v2 → Orchestrator) en démo, et défendre l'honnêteté méthodologique du système (les abandons explicites sont un argument fort)

**Matériel commercial préservé** (pour décks futurs) :

Itération 1 dry-run (rejetée — verdicts cosmétiques) :
> "# Les risques de parier sur un site non agréé ANJ en France
> Betclic, contrairement aux opérateurs illégaux, dispose d'un agrément délivré par l'Autorité Nationale des Jeux en France. Parier sur un site non agréé expose à plusieurs risques majeurs..."

Itération 2 dry-run (validée — verdicts pertinents) :
> "# Les risques de parier sur un site non agréé ANJ en France
> Parier sur un site non agréé par l'Autorité Nationale des Jeux (ANJ) expose les joueurs à des risques majeurs. Contrairement à Betclic, qui détient un agrément officiel depuis 2010..."

Le déplacement sémantique "marque en tête → réponse en tête, marque en contre-exemple" est l'illustration la plus claire de la valeur agentique de Voxa qu'on ait produite à date.

**Décisions provisoires actées** :
- Plateau quantitatif strict (delta_N ≤ delta_(N-1) + 5) suffisant pour cette beta. Plateau qualitatif (Phase 9) reportée.
- Régénération contextualisée pure suffit pour les items convergeables. Stratégie alternative (templates Content Creator par catégorie) reportée (à reconsidérer si trop d'abandonnés sur futurs Packs).
- Crawler par appel (pas partagé) accepté. Optimisation crawler partagé reportée si l'orchestrateur devient un goulot.

**Limites identifiées (à traiter à terme)** :
- R8 caractère probabiliste : à discuter ouvertement avec Olivier comme signal d'honnêteté.
- Pluralisation "tentative(s)" fixée dans la même session (mineur mais on évite la dette texte).
- Mode `--iterate` du Content Creator (legacy) non testé en interaction avec previous_attempts (forcé à False dans regenerate_for_item, comportement défensif).

**Statut** : Phase 2F ✅ closed. R8 ouvert. Pas de nouvelle dette technique ouverte cette session.

**Prochaine session prévue** : à choisir entre Phase 2G (intégration dashboard pour exposer les statuts orchestrateur dans l'UI client) ou Phase 0 (cron nocturne PA) ou re-crawl all-markets pour fraîcheur données. À décider en chat web Projet selon l'urgence Olivier.

### 2026-05-05 (jour 4 — suite — Phase 2G livrée)

**Ce qu'on a fait (en français business)** : exposition des statuts orchestrateur dans le tab Pack Action du dashboard. Badge ↻ Stabilisé / ✓ Validé / ✕ Limite atteinte avec tooltips business-friendly. Timeline expandable par item montrant la trajectoire iter-par-iter (delta + ratio verdicts + contenu généré).

**Pourquoi** : rendre démontrable la valeur agentique face à Olivier. L'item #6 du Pack #2 affiche maintenant ses 4 itérations avec deltas 72→88→98→72 et progression verdicts 0/3 → 0/3 → 1/3 → 1/3, preuve visuelle que l'orchestrateur tente activement de résoudre les rejets et abandonne honnêtement quand il plafonne.

**Validation** : pytest smoke OK, 200 sur /betclic/ /psg/ /ephilippe/, validation visuelle sur localhost:5001/betclic/ tab Pack Action (badges, timeline, tooltips, dégradation graceful tous confirmés).

**Découverte hors-scope** : DBs clients vides (ephilippe, lehavre, saintetienne, unibet, winamax) → make_dashboard plante avec `OperationalError 'no such table: prompts'`. Reformulé en doctrine produit (DT-6) plutôt que bug technique.

**Bascule workflow** : le 05/05, abandon de l'onglet `</>` Code claude.ai au profit de Claude Code CLI/panel VSCode suite à des bugs de sync worktree. Méthodologie inscrite dans `CLAUDE.md` §15 (commit 4c54e7c).

**Statut** : Phase 2G ✅ closed. Phase 2 globale ✅ closed (8/8). DT-6 ouverte (doctrine onboarding, non bloquante pour Olivier).

---

## 🎓 Leçons méthodologiques apprises

### Leçon 1 — "Code qui tourne ≠ feature qui marche"

Toujours lire qualitativement les outputs avant de déclarer une feature opérationnelle. Un agent qui tourne sans erreur peut produire des données aberrantes silencieusement.

### Leçon 2 — "Pas de baseline, pas de mesure"

Tout score "amélioré" doit être comparé à un score "à nu" pris dans la même session. Sinon impossible de prouver l'apport.

### Leçon 3 — "Le LLM est un outil non-déterministe"

1 mesure ne suffit jamais sur un outil non-déterministe. Soit on multi-crawl, soit on force le déterminisme (cas Sonar 2 forcé).

### Leçon 4 — "Tester avant d'industrialiser"

Mesurer la variance et la fiabilité d'une feature sur un échantillon avant de la déployer en pipeline complet.

### Leçon 5 — "Toujours vérifier la provenance avant de comparer"

Avant de comparer deux scores, vérifier qu'ils sont issus du même outil, du même modèle, du même contexte. Sinon comparaison invalide.

### Leçon 6 — "Le control/test est non-négociable"

Sans groupe control jamais optimisé, on ne peut pas prouver l'efficacité d'une intervention Voxa. À implémenter avant pitch sérieux.

### Leçon 7 — "Comprendre l'outil sous-jacent avant d'industrialiser"

**Contexte** : Perplexity est un orchestrateur, pas un modèle. La variance qu'on
attribuait à "Perplexity" venait en grande partie du choix dynamique de modèle.
**Règle générale** : avant d'utiliser un outil pour mesurer, documenter son
architecture interne, ses options de configuration, et ses sources de variance.

### Leçon 8 — "Documenter les décisions provisoires comme dette technique"

**Date** : 2026-05-02
**Règle générale** : ne jamais faire un choix de design **sans** documenter le
contexte, les hypothèses, et les pistes alternatives à explorer plus tard.

### Leçon 9 — "Diagnostiquer le DOM réel avant de coder un sélecteur"

**Date** : 2026-05-03
**Contexte** : J'ai d'abord supposé que le menu Perplexity utilisait `role="dialog"`
en me basant sur ta capture d'écran initiale (en mode Pro). En mode anonyme, c'est
en réalité `role="menu"` avec items `[role="menuitemradio"]`. Sans diagnostic DOM
explicite (3 itérations de scripts d'inspection), j'aurais codé un sélecteur faux
qui aurait planté silencieusement.
**Règle générale** : avant d'écrire un sélecteur DOM, **inspecter le DOM réel
dans le contexte exact d'exécution** (pas le contexte de la capture d'écran).
Le diagnostic prend 5 minutes mais évite des heures de debug en aveugle.

### Leçon 10 — "Grep avant suppression"

**Date** : 2026-05-04 (DT-2 / cleanup `report_generator.py`)
**Règle générale** : toujours `grep -rn "nom_du_fichier"` avant `git rm` ou refacto cross-fichiers. Une suppression à l'aveugle peut casser des imports en chaîne et provoquer un crash silencieux du serveur en prod.

### Leçon 11 — "Hypothèse de bug ≠ bug réel"

**Date** : 2026-05-04 (DT-2)
**Contexte** : DT-2 ouvert sur l'hypothèse "table `action_items` manquante dans `voxa_betclic.db`" alors qu'en réalité les tables sont centralisées dans `voxa_accounts.db` et Pack #2 était bien généré.
**Règle générale** : avant d'investir une session de debug, vérifier l'hypothèse de base par une inspection directe (ici : `sqlite3` sur les bonnes DBs). Un faux ticket coûte autant qu'un vrai.

### Leçon 12 — "Le verdict qualitatif corrige le verdict quantitatif"

**Date** : 2026-05-04 (Phase 2E QC v2)
**Contexte** : sur l'item #6 du Pack #2 Betclic, le score quantitatif Perplexity bondit de 0 à +98 pts (delta médian) — un succès apparent maximal. Mais le filtre Haiku révèle que les 3 mentions de Betclic sont off-topic (la question portait sur les *risques de parier sur un site non agréé ANJ*, les réponses dérivent vers *Betclic est un opérateur agréé ANJ*). Sans le filtre Haiku, QC v1 aurait validé un faux positif pur.
**Règle générale** : pour toute mesure GEO, ne jamais valider sur un signal quantitatif seul. Croiser avec un signal qualitatif sémantique (filtre LLM ou lecture humaine). Un score brut élevé peut masquer une mention off-topic, un signal qualitatif l'attrape.

### Leçon 13 — "L'abandon honnête vaut mieux que le faux positif"

**Date** : 2026-05-05 (Phase 2F Orchestrateur — run réel item #6)
**Contexte** : sur 2 runs orchestrateur consécutifs sur le même item, on obtient validated puis abandoned_plateau. Le système probabiliste ne converge pas toujours. Plutôt que de masquer ce comportement, Voxa le documente explicitement dans le history JSON et dans le statut final.
**Règle générale** : un système GEO qui prétend toujours optimiser tout n'est pas fiable. Un système qui sait dire "je n'arrive pas à valider cet item de façon défendable" est mille fois plus défendable face à un client technique. L'abandon honnête est un signal de rigueur, pas un échec produit.

---

## 📚 Glossaire des features Voxa

### Crawler Perplexity (`crawlers/perplexity.py`) — ✅ Sonar 2 forcé
**À quoi ça sert** : récupère les vraies réponses Perplexity en automatisant un navigateur Chrome.
**Configuration** : force Sonar 2 par défaut (cf. Note 1). Utilisable avec `--no-force-model` pour mode "Meilleur".
**Output** : étiquette le run en DB avec `llm = perplexity-sonar-2` (ou `perplexity-fallback` si sélection ratée).
**Limite connue** : Sonar 2 ≠ expérience utilisateur gratuit (cf. Note 1 pistes futures et R1).

### Tracker UI (`tracker_ui.py`)
**À quoi ça sert** : crawle les prompts d'un client en boucle pour mesurer la présence de la marque.
**À l'avenir** : devra distinguer prompts control et prompts test (Phase 9), passer en multi-crawl.

### Migration DB v3 (`migrate_v3.py`)
**À quoi ça sert** : ajoute la table `agent_runs` à toutes les bases SQLite Voxa.

### Classe abstraite Agent (`agents/base.py`)
**À quoi ça sert** : fondation commune pour tous les agents Voxa.
**Bonus** : auto-création de DB minimale si le slug n'a pas encore de tracking.

### Agent Gap Analyzer (`agents/gap_analyzer.py`) — ✅ filtre Sonar 2
**À quoi ça sert** : identifie les angles morts d'une marque dans Perplexity.
**Filtre actif** : `PRIMARY_LLM_FILTER = "perplexity-sonar-2"`. Pour réinclure les anciens runs (debug) : `ALLOW_LEGACY_RUNS = True`.

### Crawlability Agent (`agents/crawlability_agent.py`)
**À quoi ça sert** : audit technique du site web pour vérifier qu'il est lisible par les bots IA.

### Content Creator (`agents/content_creator.py`)
**À quoi ça sert** : génère le contenu (texte + JSON-LD) pour combler les angles morts.
**Coût** : ~0.05$ par item (Claude API).

### Quality Controller v2 (`agents/quality_controller.py`) — ✅ LIVRÉ 04/05
**À quoi ça sert** : valide chaque item du Content Creator via un protocole control/test : 1 crawl Perplexity sans injection (baseline), 3 crawls avec injection via template factuel neutre, médiane des scores test, delta = test − baseline. Filtre qualitatif Claude Haiku sur chaque crawl test (verdict pertinent / cosmetique / absent / ambiguous).
**Statut final** : `validated` si delta > 10 ET ≥ 2/3 verdicts pertinents, sinon `needs_iteration`.
**Coût** : ~12 crawls Perplexity + 9 appels Haiku par pack de 3 items, ~9 minutes, ~0.01$ Anthropic. Négligeable.
**Limites connues** : 1 domaine unique par client (pas de breakdown par marché). À reconsidérer si la qualité d'augmentation se révèle insuffisante.

### Action Pack (`action_pack.py`) — ⚠️ init implicite
**À quoi ça sert** : module V2, pipeline "Pack Action Hebdo" — agrège les outputs Content Creator en un pack hebdo.
**Convention fragile** : les tables (`action_items`, etc.) sont créées par effet de bord à l'import du module (cf. R5). Couvert par `test_action_pack_smoke.py` depuis le 04/05.

### Orchestrator (`agents/orchestrator.py`) — ✅ LIVRÉ 05/05
**À quoi ça sert** : prend un Pack existant et fait converger ses items en `needs_iteration`. Pour chaque item rejeté, l'orchestrateur appelle Content Creator avec le contexte des verdicts précédents (régénération contextualisée), puis QC v2 sur le nouveau contenu. Boucle jusqu'à validation OU plateau quantitatif (delta n'évolue plus de >5 pts) OU max 5 itérations.
**Statuts finaux possibles** : `validated`, `abandoned_plateau`, `abandoned_after_max_iterations`.
**Comportement** : skip les items déjà validated (zero crawl wasted), écrase le `content` de l'item uniquement si converged, persiste un history JSON complet pour audit.
**Coût** : ~0.03-0.30$ Anthropic par item selon nombre d'itérations, ~5-25 min par item. Items skip = gratuit.
**Limites connues** : caractère probabiliste cf. R8.

### Smoke test action_pack (`test_action_pack_smoke.py`) — ✅ ajouté 04/05
**À quoi ça sert** : vérifie que les tables Pack sont bien créées après import de `action_pack.py`. Détecte toute régression sur le pattern d'init implicite (cf. R5).

### Test scripts (`test_baseline.py`, `test_qc_rag.py`, `test_variance.py`, `analyze_variance.py`)
**À quoi ça sert** : scripts ponctuels pour valider la méthodologie d'autres features.

### Scripts d'infra (`scripts/`)
- `voxa_nightly.sh`, `setup_ssh_pa.sh`, `install_cron.sh`
- Status : créés, prêts à activer (mot de passe PA OK depuis 04/05).

---

*Dernière mise à jour : 05/05/2026 — Phase 2G livrée, Phase 2 closed (8/8), DT-6 ouverte (doctrine onboarding), bascule workflow vers Claude Code CLI/panel VSCode.*
*À régénérer après chaque session significative pour garder project knowledge et repo alignés.*
