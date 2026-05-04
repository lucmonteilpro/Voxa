# Voxa — Plan d'action

> **Document vivant** — Claude met à jour ce fichier systématiquement à chaque
> session. Tu peux aussi l'éditer librement entre les sessions.
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
- [ ] Si Olivier (expert data marketing) demande "comment vous mesurez ?",
      ai-je une réponse rigoureuse en moins de 30 secondes ?
- [ ] Les chiffres présentés sont-ils des moyennes/médianes sur N mesures ?
- [ ] Le delta présenté est-il comparé à un groupe control ?
- [ ] Documenter les limites connues de la feature

---

## 📌 Notes stratégiques persistantes

> Réflexions ouvertes, non tranchées définitivement, à reconsulter régulièrement.
> Ces notes ne sont JAMAIS supprimées sans validation explicite.

### Note 1 — Choix du modèle Perplexity à mesurer

**Date d'origine** : 2026-05-02
**Statut** : décision provisoire, à valider après plus de tests
**Décision actuelle** : **forcer Sonar 2** sur le crawler Perplexity

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

#### Action immédiate (validée 2026-05-02)

- [x] Refactor crawler Perplexity pour forcer Sonar 2
- [ ] Test variance avec Sonar 2 forcé (3 prompts × 3 crawls)
- [ ] Selon variance, déterminer N pour le QC
- [ ] Mettre à jour le champ `llm` dans la DB : `perplexity-default` → `perplexity-sonar-2`

#### Comment cette note évolue

Cette note doit être **complétée** à chaque session qui touche au sujet Perplexity / modèles. **Ne jamais supprimer** une question, on peut juste y répondre. Si on découvre quelque chose qui invalide la décision, on l'écrit sans effacer la décision précédente.

---

## 🔥 Tâches en attente immédiate

- [x] Run all-markets terminé (88 runs, 1385 sources)
- [x] Gap Analyzer all-markets (23 angles morts)
- [x] Content Creator testé (delta moyen +47 pts)
- [x] QC v1 testé : faux positifs identifiés
- [x] Test variance + analyse statistique 8098 mesures historiques
- [x] **Découverte Perplexity orchestrateur** : Sonar 2 / GPT / Claude / Gemini sélectionnables
- [x] **Décision** : forcer Sonar 2 (cf. Note 1 stratégique)
- [ ] **Refactor crawler Perplexity** : ajout sélection modèle + force Sonar 2
- [ ] **Test variance avec Sonar 2 forcé** (3 prompts × 3 crawls)
- [ ] **QC v2** : N crawls (selon variance) + nouveau template anti-faux-positif
- [ ] Setup SSH Mac → PA — bloqueur PA password
- [ ] Cron 02h00

---

## 📊 Vue d'ensemble

| Phase | Objectif | Statut |
|---|---|---|
| **Phase 0** | Sprint Betclic — infra crawl + sync | 🟡 |
| **Phase 1** | Démo Betclic prête | 🔄 |
| **Phase 2** | Architecture multi-agents | 🟡 (4/8 ✅, 1 🧪) |
| **Phase 3** | Crawlers UI multi-LLMs | ⏳ |
| **Phase 4** | Chatbot agentique sidebar | ⏳ |
| **Phase 5** | Olivier's 5 besoins Betclic | 🔄 |
| **Phase 6** | Migration Hetzner | 🔄 |
| **Phase 7** | Pub ChatGPT US | ⏸ |
| **Phase 8** | Voxa Politics | ⏳ |
| **Phase 9** | Protocole control/test | ⏳ |

---

## ✅ Phase préparatoire (déjà fait)

- Dashboard, Migration DB v2, Crawler Perplexity (patchright)
- Tracker UI v1 + v2 (--all-markets, idempotence, ETA)
- Run Betclic all-markets : 88 runs, 1385 sources
- 8098 mesures historiques en DB (multi-LLM, 30+ jours)
- Souscription Perplexity Pro

---

## 🟡 Phase 0 — Sprint Betclic infra

- [x] Scripts shell créés
- [ ] SSH Mac → PA — bloqué sur mot de passe PA
- [ ] Test SCP manuel
- [x] Run all-markets exécuté
- [ ] Cron 02h00 installé

---

## 🔄 Phase 1 — Démo Betclic prête (reporté)

---

## 🟡 Phase 2 — Architecture multi-agents

### Décisions de design

- ✅ Anthropic SDK natif
- ✅ Table `agent_runs`
- ✅ Boucle hybride max 5 itérations OR plateau
- ✅ Gap Analyzer = Python ; Content Creator = Claude API
- ✅ Seuil angle mort : ≤ 60/100
- ✅ Auto-création DB minimale
- ✅ Voxa = GEO uniquement
- ✅ Refacto soft `action_pack.py`
- ✅ **Crawler force toujours 1 modèle spécifique** (cf. Note 1)
- 🟡 QC : N crawls + médiane — N à finaliser après test Sonar 2 forcé

### Sous-phases

- ✅ 2A Migration DB v3 + classe Agent
- ✅ 2B Gap Analyzer
- ✅ 2C Crawlability Agent
- ✅ 2D Content Creator
- 🧪 2E Quality Controller (en validation méthodologique)
- ⏳ 2F Orchestrateur multi-agents (bloqué jusqu'à 2E + 9)
- ⏳ 2G Intégration dashboard

### État détaillé 2E

- [x] Code v1 livré
- [x] Tests baseline + variance + RAG
- [x] Découverte 8098 mesures historiques exploitables
- [x] Analyse statistique : 5 crawls = précision ±10 pts (en mode "Meilleur")
- [x] **Découverte critique** : Perplexity est un orchestrateur, on peut forcer Sonar 2
- [ ] **Refactor crawler** : forcer Sonar 2
- [ ] **Re-test variance** avec Sonar 2 forcé (devrait être beaucoup plus stable)
- [ ] Décision finale sur N
- [ ] QC v2 : implémentation
- [ ] Phase C pré-pitch

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

---

## ⏳ Phase 4 — Chatbot agentique sidebar
## 🔄 Phase 5 — Olivier's 5 besoins Betclic
## 🔄 Phase 6 — Migration Hetzner
## ⏸ Phase 7 — Pub ChatGPT US
## ⏳ Phase 8 — Voxa Politics
## ⏳ Phase 9 — Protocole control/test

---

## 🗒 Journal de bord

### 2026-05-02

**Découvertes majeures** :

1. **8098 mesures historiques** disponibles en DB
2. **Variance LLM élevée** : 1 mesure → ±24 pts ; 5 mesures → ±10 pts
3. **Distribution bimodale** des scores (alterne 0 et 70+)
4. **Perplexity est un orchestrateur** (pas un modèle unique)
   - Mode actuel : "perplexity-default" = mode "Meilleur" qui choisit aléatoirement
   - Possibilité de forcer Sonar 2, GPT-5.4, Claude 4.6, Gemini 3.1 (via UI)
5. **Décision** : forcer Sonar 2 dans le crawler. Justifications dans Note 1 stratégique.

**Décisions de design pérennes** :
- Voxa force toujours 1 modèle par crawler (architecture cohérente)
- Phase 3 multi-LLMs aura 1 crawler par modèle (Sonar 2, GPT-5.4, Claude 4.6, Gemini 3.1)
- Pas de redondance entre crawlers

**Insight commercial Voxa** :
> Voxa peut se positionner comme **le seul outil GEO** qui :
> - Force un modèle stable par mesure (vs concurrents en mode "Meilleur" aléatoire)
> - Mesure plusieurs LLMs séparément
> - Maintient un groupe contrôle (Phase 9)
> - Documente les limites avec rigueur (cf. Note 1)

---

## 🎓 Leçons méthodologiques apprises

### Leçon 1 — "Code qui tourne ≠ feature qui marche"

### Leçon 2 — "Pas de baseline, pas de mesure"

### Leçon 3 — "Le LLM est un outil non-déterministe"

### Leçon 4 — "Tester avant d'industrialiser"

### Leçon 5 — "Toujours vérifier la provenance avant de comparer"

### Leçon 6 — "Le control/test est non-négociable"

### Leçon 7 — "Comprendre l'outil sous-jacent avant d'industrialiser"
**Contexte** : Perplexity est un orchestrateur, pas un modèle. La variance qu'on
attribuait à "Perplexity" venait en grande partie du choix dynamique de modèle.
**Règle générale** : avant d'utiliser un outil pour mesurer, documenter son
architecture interne, ses options de configuration, et ses sources de variance.

### Leçon 8 — "Documenter les décisions provisoires comme dette technique"
**Date** : 2026-05-02
**Contexte** : la décision de forcer Sonar 2 est prise dans un contexte d'incertitude
(on ne sait pas si Sonar 2 reflète l'expérience utilisateur gratuit). Plutôt que de
tout figer ou de tout reporter, on prend la décision **mais on consigne la
réflexion ouverte** dans une "Note stratégique persistante" (Note 1).
**Règle générale** : ne jamais faire un choix de design **sans** documenter le
contexte, les hypothèses, et les pistes alternatives à explorer plus tard. La
documentation de l'incertitude est aussi importante que la décision elle-même.

---

## 📚 Glossaire des features Voxa

### Crawler Perplexity (`crawlers/perplexity.py`)
**À quoi ça sert** : récupère les vraies réponses Perplexity en automatisant un navigateur Chrome.
**Configuration future** : forcer Sonar 2 (cf. Note 1).
**Limite connue** : Sonar 2 ≠ expérience utilisateur gratuit (cf. Note 1 pistes futures).

### Tracker UI (`tracker_ui.py`)
**À quoi ça sert** : crawle les prompts d'un client en boucle pour mesurer la présence de la marque.
**À l'avenir** : devra distinguer prompts control et prompts test (Phase 9).

### Migration DB v3 (`migrate_v3.py`)
**À quoi ça sert** : ajoute la table `agent_runs` à toutes les bases SQLite Voxa.

### Classe abstraite Agent (`agents/base.py`)
**À quoi ça sert** : fondation commune pour tous les agents Voxa.
**Bonus** : auto-création de DB minimale si le slug n'a pas encore de tracking.

### Agent Gap Analyzer (`agents/gap_analyzer.py`)
**À quoi ça sert** : identifie les angles morts d'une marque dans Perplexity.

### Crawlability Agent (`agents/crawlability_agent.py`)
**À quoi ça sert** : audit technique du site web pour vérifier qu'il est lisible par les bots IA.

### Content Creator (`agents/content_creator.py`)
**À quoi ça sert** : génère le contenu (texte + JSON-LD) pour combler les angles morts.
**Coût** : ~0.05$ par item (Claude API).

### Quality Controller (`agents/quality_controller.py`) — 🧪 EN VALIDATION
**Limites connues** :
- Faux positifs avec template "Imagine que..."
- 1 crawl insuffisant en mode "Meilleur"
- Refacto en cours : forcer Sonar 2 + N crawls + nouveau template

### Test scripts (`test_baseline.py`, `test_qc_rag.py`, `test_variance.py`, `analyze_variance.py`)
**À quoi ça sert** : scripts ponctuels pour valider la méthodologie.
**Status** : ont permis de découvrir les leçons 1-8.

### Scripts d'infra (`scripts/`)
- `voxa_nightly.sh`, `setup_ssh_pa.sh`, `install_cron.sh`
- Status : créés, pas encore activés (mot de passe PA).