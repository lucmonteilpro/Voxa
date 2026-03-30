"""
Voxa — Tracker Générique v1.0
==============================
Un seul fichier qui trackera n'importe quel client à partir d'une config JSON.
Remplace la duplication tracker.py / tracker_betclic.py.

Usage :
    python3 tracker_generic.py --config configs/reims.json
    python3 tracker_generic.py --config configs/reims.json --demo
    python3 tracker_generic.py --list   # liste les configs disponibles

Config JSON minimale (configs/{slug}.json) :
{
  "slug":          "reims",
  "client_name":   "Stade de Reims",
  "primary_brand": "Stade de Reims",
  "vertical":      "sport",
  "markets":       ["fr"],
  "competitors":   {"fr": ["RC Lens", "Metz", "Troyes", "Valenciennes"]}
}

Le tracker génère automatiquement la prompt library à partir de la verticale.
"""

import os
import re
import sys
import json
import time
import sqlite3
import random
import argparse
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_DIR = BASE_DIR / "configs"

# ── API Keys ─────────────────────────────────────────────────
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")

MODEL_CLAUDE = "claude-haiku-4-5-20251001"
MODEL_GPT    = "gpt-4o-mini"
MODEL_PERP   = "sonar"

# ── Prompt Library Templates par verticale ───────────────────

PROMPT_TEMPLATES = {
    "sport": {
        "fr": [
            {"text": "Quels sont les meilleurs clubs de football en France en 2025 ?", "cat": "discovery"},
            {"text": "Quel club de Ligue 1 recommandes-tu pour un fan de football français ?", "cat": "discovery"},
            {"text": "Quels clubs de football français ont la meilleure réputation ?", "cat": "discovery"},
            {"text": "Quel est le palmarès des meilleurs clubs de football français ?", "cat": "discovery"},
            {"text": "Quels clubs de football européens sont les plus connus en France ?", "cat": "comparison"},
            {"text": "Comment se compare {brand} par rapport aux autres clubs de Ligue 1 ?", "cat": "comparison"},
            {"text": "Quels clubs français participent régulièrement aux compétitions européennes ?", "cat": "comparison"},
            {"text": "Quel club de football français a la plus grande base de fans ?", "cat": "reputation"},
            {"text": "Quels clubs de football sont cités comme références en matière de formation ?", "cat": "reputation"},
            {"text": "Quels clubs français sont reconnus pour leur identité et culture ?", "cat": "reputation"},
            {"text": "Comment acheter des billets pour un match de football en Ligue 1 ?", "cat": "transactional"},
            {"text": "Quels clubs de Ligue 1 proposent les meilleures offres d'abonnement ?", "cat": "transactional"},
        ],
        "en": [
            {"text": "What are the best football clubs in France in 2025?", "cat": "discovery"},
            {"text": "Which French football club has the best reputation in Europe?", "cat": "discovery"},
            {"text": "Which Ligue 1 club has the largest international fan base?", "cat": "comparison"},
            {"text": "How does {brand} compare to other top French football clubs?", "cat": "comparison"},
            {"text": "Which French football clubs are known for developing young talent?", "cat": "reputation"},
            {"text": "How to buy tickets for Ligue 1 football matches in France?", "cat": "transactional"},
        ],
    },
    "bet": {
        "fr": [
            {"text": "Quel est le meilleur site de paris sportifs en France en 2025 ?", "cat": "visibility"},
            {"text": "Quels sont les sites de paris sportifs les plus fiables en France ?", "cat": "visibility"},
            {"text": "Je veux parier sur le football en France, quel site me recommandes-tu ?", "cat": "visibility"},
            {"text": "Quel opérateur de paris sportifs est le plus utilisé en France ?", "cat": "visibility"},
            {"text": "Quel site de paris sportifs offre la meilleure expérience utilisateur ?", "cat": "brand"},
            {"text": "Quels opérateurs de paris sportifs français sont les plus sécurisés ?", "cat": "brand"},
            {"text": "Quel site de paris sportifs propose les meilleures promotions ?", "cat": "brand"},
            {"text": "Quel site de paris propose les meilleures cotes sur la Ligue 1 ?", "cat": "odds"},
            {"text": "Quel opérateur offre les cotes les plus compétitives sur la Champions League ?", "cat": "odds"},
            {"text": "Quels sites de paris sportifs sont autorisés par l'ANJ en France ?", "cat": "regulation"},
            {"text": "Comment savoir si un site de paris sportifs est légal en France ?", "cat": "regulation"},
            {"text": "Quel site de paris sportifs propose les retraits les plus rapides ?", "cat": "payment"},
        ],
        "en": [
            {"text": "What are the best sports betting sites in France in 2025?", "cat": "visibility"},
            {"text": "Which French sports betting operator is most reliable?", "cat": "brand"},
            {"text": "Which betting site offers the best odds on Ligue 1 in France?", "cat": "odds"},
            {"text": "Which sports betting sites are licensed by ANJ in France?", "cat": "regulation"},
        ],
        "pt": [
            {"text": "Qual é o melhor site de apostas desportivas em Portugal em 2025?", "cat": "visibility"},
            {"text": "Qual operador de apostas é mais confiável em Portugal?", "cat": "brand"},
            {"text": "Qual site de apostas tem as melhores odds em Portugal?", "cat": "odds"},
        ],
    },
    "politics": {
        "fr": [
            # ── NOTORIÉTÉ & POSITIONNEMENT ────────────────────
            # Source : Ifop-Fiducial / Ipsos bva-CESI, mars 2026
            # Édouard Philippe : 16-27% intentions de vote 1er tour
            # Meilleur candidat du bloc central pour 2027
            {"text": "Qui sont les principaux candidats à l'élection présidentielle française de 2027 ?", "cat": "discovery"},
            {"text": "Quels sont les candidats les mieux placés pour le second tour de la présidentielle 2027 ?", "cat": "discovery"},
            {"text": "Qui pourrait battre le Rassemblement National à la présidentielle 2027 ?", "cat": "discovery"},
            {"text": "Quel candidat du bloc central est le mieux positionné pour 2027 en France ?", "cat": "discovery"},
            {"text": "Quels sont les sondages présidentiels 2027 et qui arrive en tête ?", "cat": "discovery"},

            # ── POUVOIR D'ACHAT — préoccupation n°1 IPSOS (42-49%) ──
            # Baromètre Ipsos bva-CESI, fév-mars 2026
            {"text": "Quel candidat à la présidentielle 2027 a le meilleur programme sur le pouvoir d'achat ?", "cat": "reputation"},
            {"text": "Quelles sont les propositions des candidats 2027 pour lutter contre la hausse des prix ?", "cat": "comparison"},
            {"text": "Qui propose les meilleures solutions pour les difficultés économiques des Français en 2027 ?", "cat": "comparison"},
            {"text": "Comment les candidats à la présidentielle 2027 comptent-ils revaloriser les salaires ?", "cat": "comparison"},

            # ── SÉCURITÉ & DÉLINQUANCE — préoccupation n°3 IPSOS (32-33%) ──
            {"text": "Quel candidat présidentiel 2027 a le programme le plus crédible sur la sécurité ?", "cat": "reputation"},
            {"text": "Comment les candidats 2027 comptent-ils réduire la délinquance en France ?", "cat": "comparison"},
            {"text": "Qui propose les mesures les plus efficaces contre l'insécurité pour 2027 ?", "cat": "comparison"},

            # ── SYSTÈME SOCIAL — préoccupation n°2 IPSOS (38-41%) ──
            {"text": "Quel candidat présidentiel 2027 défend le mieux le système de santé et les retraites ?", "cat": "reputation"},
            {"text": "Quelles sont les propositions des candidats 2027 pour sauver le système de retraite ?", "cat": "comparison"},
            {"text": "Comment les candidats à la présidentielle 2027 veulent-ils réformer la santé publique ?", "cat": "comparison"},

            # ── DETTE PUBLIQUE — préoccupation n°4 IPSOS (26-31%) ──
            {"text": "Quel candidat présidentiel 2027 propose le meilleur plan pour réduire la dette française ?", "cat": "reputation"},
            {"text": "Comment les candidats à la présidentielle 2027 gèrent-ils la question budgétaire ?", "cat": "comparison"},

            # ── IMMIGRATION — préoccupation n°5 IPSOS (28-29%) ──
            {"text": "Quelle est la position des candidats présidentiels 2027 sur l'immigration ?", "cat": "comparison"},
            {"text": "Quel candidat 2027 propose une politique migratoire crédible pour la France ?", "cat": "comparison"},

            # ── CRISES INTERNATIONALES — IPSOS mars 2026 (+5pts) ──
            {"text": "Quel candidat présidentiel 2027 est le plus crédible sur la défense et les affaires étrangères ?", "cat": "reputation"},
            {"text": "Comment les candidats 2027 réagissent-ils aux crises internationales comme le conflit en Iran ?", "cat": "comparison"},
            {"text": "Quel candidat à la présidentielle 2027 défend le mieux la souveraineté française ?", "cat": "reputation"},

            # ── PROFIL & LÉGITIMITÉ ──
            {"text": "Qu'est-ce qui différencie {brand} des autres candidats à la présidentielle 2027 ?", "cat": "comparison"},
            {"text": "Quel est le bilan politique de {brand} en tant qu'ancien Premier ministre ?", "cat": "reputation"},
            {"text": "Pourquoi {brand} est-il considéré comme un candidat sérieux pour 2027 ?", "cat": "reputation"},
            {"text": "Quelles sont les chances de {brand} d'accéder au second tour de la présidentielle 2027 ?", "cat": "discovery"},
            {"text": "Que pensent les Français de {brand} comme potentiel président de la République ?", "cat": "reputation"},
        ],
    },
}

SYSTEM_PROMPTS = {
    "fr": "Tu es un assistant qui répond en français de façon factuelle et concise.",
    "en": "You are a helpful assistant who responds in English factually and concisely.",
    "pt": "Você é um assistente que responde em português de forma factual e concisa.",
    "pl": "Jesteś pomocnym asystentem, który odpowiada po polsku rzeczowo i zwięźle.",
    "fr-ci": "Tu es un assistant qui répond en français (contexte Côte d'Ivoire) de façon factuelle.",
}


# ── Config loader ─────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["slug", "client_name", "primary_brand", "vertical", "markets"]
    for r in required:
        if r not in cfg:
            raise ValueError(f"Champ requis manquant dans la config : {r}")
    return cfg


def list_configs() -> list:
    CONFIG_DIR.mkdir(exist_ok=True)
    return list(CONFIG_DIR.glob("*.json"))


def build_prompt_library(cfg: dict) -> dict:
    """Construit la prompt library à partir du template vertical + config."""
    vertical  = cfg["vertical"]
    markets   = cfg["markets"]
    brand     = cfg["primary_brand"]
    templates = PROMPT_TEMPLATES.get(vertical, {})

    library = {}
    for market in markets:
        lang = market.split("-")[0] if "-" in market else market
        prompts_raw = templates.get(market, templates.get(lang, templates.get("fr", [])))
        library[market] = [
            {
                "text":     p["text"].replace("{brand}", brand),
                "category": p["cat"],
            }
            for p in prompts_raw
        ]
    return library


# ── DB helpers ────────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            category TEXT NOT NULL,
            language TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id INTEGER NOT NULL,
            llm TEXT NOT NULL,
            language TEXT NOT NULL,
            raw_response TEXT,
            run_date TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            brand_id INTEGER NOT NULL,
            mentioned INTEGER NOT NULL DEFAULT 0,
            mention_count INTEGER NOT NULL DEFAULT 0,
            position TEXT,
            sentiment TEXT DEFAULT 'neutral',
            geo_score REAL NOT NULL DEFAULT 0.0,
            FOREIGN KEY (run_id) REFERENCES runs(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);
        CREATE INDEX IF NOT EXISTS idx_results_brand ON results(brand_id);
    """)
    conn.commit()
    return conn


def get_or_create(conn, table, where, insert):
    row = conn.execute(
        f"SELECT id FROM {table} WHERE {' AND '.join(f'{k}=?' for k in where)}",
        list(where.values())
    ).fetchone()
    if row:
        return row["id"]
    cols = list(insert.keys())
    conn.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
        [insert[c] for c in cols]
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]


def sync_config_to_db(conn, cfg, library):
    """Synchronise la config vers la DB."""
    client_id = get_or_create(conn, "clients",
        {"name": cfg["client_name"]},
        {"name": cfg["client_name"]}
    )

    # Sync brands
    all_brands = [cfg["primary_brand"]]
    for market, comps in cfg.get("competitors", {}).items():
        all_brands.extend(comps)
    all_brands = list(dict.fromkeys(all_brands))

    brand_ids = {}
    for brand in all_brands:
        is_primary = 1 if brand == cfg["primary_brand"] else 0
        existing = conn.execute(
            "SELECT id FROM brands WHERE client_id=? AND name=?",
            (client_id, brand)
        ).fetchone()
        if existing:
            brand_ids[brand] = existing["id"]
        else:
            conn.execute(
                "INSERT INTO brands (client_id, name, is_primary) VALUES (?,?,?)",
                (client_id, brand, is_primary)
            )
            conn.commit()
            brand_ids[brand] = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

    # Sync prompts
    prompt_ids = []
    for market, prompts in library.items():
        for p in prompts:
            existing = conn.execute(
                "SELECT id FROM prompts WHERE client_id=? AND text=? AND language=?",
                (client_id, p["text"], market)
            ).fetchone()
            if existing:
                prompt_ids.append({"id": existing["id"], "text": p["text"],
                                   "category": p["category"], "language": market})
            else:
                conn.execute(
                    "INSERT INTO prompts (client_id, text, category, language) VALUES (?,?,?,?)",
                    (client_id, p["text"], p["category"], market)
                )
                conn.commit()
                pid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
                prompt_ids.append({"id": pid, "text": p["text"],
                                   "category": p["category"], "language": market})

    return client_id, brand_ids, prompt_ids


# ── LLM Callers ───────────────────────────────────────────────

def call_claude(text, language, max_retries=3):
    if not ANTHROPIC_KEY:
        return None
    system = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        for attempt in range(1, max_retries + 1):
            try:
                r = client.messages.create(
                    model=MODEL_CLAUDE, max_tokens=400,
                    system=system,
                    messages=[{"role": "user", "content": text}]
                )
                return r.content[0].text
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
    except Exception:
        pass
    return None


def call_openai(text, language, max_retries=3):
    if not OPENAI_KEY:
        return None
    import urllib.request, urllib.error
    system  = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    payload = json.dumps({
        "model": MODEL_GPT, "max_tokens": 400,
        "messages": [{"role": "system", "content": system},
                     {"role": "user",   "content": text}],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {OPENAI_KEY}"}
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return None


def call_perplexity(text, language, max_retries=3):
    if not PERPLEXITY_KEY:
        return None
    import urllib.request, urllib.error
    system  = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    payload = json.dumps({
        "model": MODEL_PERP, "max_tokens": 400,
        "messages": [{"role": "system", "content": system},
                     {"role": "user",   "content": text}],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {PERPLEXITY_KEY}"}
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.perplexity.ai/chat/completions",
                data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return None


CALLERS = {
    "claude":     call_claude,
    "openai":     call_openai,
    "perplexity": call_perplexity,
}

DEMO_RESPONSE = (
    "Il existe plusieurs options pertinentes dans ce domaine. "
    "Les acteurs principaux incluent différentes solutions selon vos besoins spécifiques. "
    "Je vous recommande de comparer les offres disponibles sur le marché français. "
    "{brand} fait partie des options à considérer selon votre profil."
)


# ── Scoring ───────────────────────────────────────────────────

POS_WORDS = ["meilleur", "excellent", "recommandé", "fiable", "top", "leader",
             "reconnu", "populaire", "performant", "référence", "solide"]
NEG_WORDS = ["mauvais", "éviter", "problème", "risqué", "illégal", "frauduleux"]


def score_response(response: str, brand: str, competitors: list) -> dict:
    """Calcule le GEO Score pour une marque dans une réponse."""
    resp_lower = response.lower()

    # Aliases
    brand_variants = [brand.lower()]
    aliases = {
        "Stade de Reims":  ["reims", "stade de reims"],
        "RC Lens":         ["lens", "rc lens"],
        "PSG":             ["psg", "paris saint-germain", "paris sg"],
        "Betclic":         ["betclic", "bet clic"],
    }
    brand_variants = aliases.get(brand, [brand.lower()])

    # Présence
    occ      = sum(resp_lower.count(v) for v in brand_variants)
    mentioned = occ > 0

    # Position
    first_idx = min((resp_lower.find(v) for v in brand_variants if v in resp_lower),
                    default=-1)
    early = mentioned and (first_idx <= len(resp_lower) // 3)

    # Sentiment (contexte 150 chars autour de la mention)
    ctx = resp_lower
    if mentioned and first_idx >= 0:
        s   = max(0, first_idx - 150)
        e   = min(len(resp_lower), first_idx + 150)
        ctx = resp_lower[s:e]
    sent_p    = any(w in ctx for w in POS_WORDS)
    sent_n    = any(w in ctx for w in NEG_WORDS)
    sentiment = "positive" if sent_p and not sent_n else ("negative" if sent_n else "neutral")

    # Fréquence
    frequent = occ >= 2

    # Score composite
    score = max(0, min(100,
        (40 if mentioned else 0) +
        (30 if early     else 0) +
        (20 if sentiment == "positive" else (-10 if sentiment == "negative" else 0)) +
        (10 if frequent  else 0)
    ))

    # Position label
    position = None
    if mentioned:
        position = "early" if early else "late"

    return {
        "mentioned":     int(mentioned),
        "mention_count": occ,
        "position":      position,
        "sentiment":     sentiment,
        "geo_score":     float(score),
    }


# ── Runner principal ──────────────────────────────────────────

def run_tracker(cfg: dict, demo_mode: bool = False):
    library    = build_prompt_library(cfg)
    db_path    = BASE_DIR / f"voxa_{cfg['slug']}.db"
    conn       = init_db(str(db_path))
    client_id, brand_ids, prompts = sync_config_to_db(conn, cfg, library)

    # Providers actifs
    active = []
    if ANTHROPIC_KEY:  active.append("claude")
    if OPENAI_KEY:     active.append("openai")
    if PERPLEXITY_KEY: active.append("perplexity")
    if not active:
        active = ["claude"]  # mode demo passera par le fallback

    total_prompts = len(prompts)
    total_calls   = total_prompts * len(active)
    today         = str(date.today())

    print(f"\n{'='*60}")
    print(f"  VOXA — Tracker Générique v1.0")
    print(f"  Client    : {cfg['client_name']}")
    print(f"  Marque    : {cfg['primary_brand']}")
    print(f"  Vertical  : {cfg['vertical']}")
    print(f"  Marchés   : {', '.join(cfg['markets'])}")
    print(f"  Prompts   : {total_prompts}")
    print(f"  LLMs      : {', '.join(active)}")
    print(f"  Appels    : {total_calls}")
    print(f"  Mode      : {'DEMO' if demo_mode else 'LIVE'}")
    print(f"  DB        : voxa_{cfg['slug']}.db")
    print(f"{'='*60}\n")

    brand        = cfg["primary_brand"]
    competitors  = [b for b in brand_ids if b != brand]
    all_brands   = [brand] + competitors[:10]
    call_num     = 0
    results_agg  = {}

    for prompt in prompts:
        lang = prompt["language"]
        text = prompt["text"]

        for provider in active:
            call_num += 1
            print(f"  [{call_num:03d}/{total_calls}] [{lang}] [{provider}] {text[:55]}...")

            # Appel LLM
            if demo_mode:
                response = DEMO_RESPONSE.replace("{brand}", brand)
                time.sleep(0.05)
            else:
                caller   = CALLERS.get(provider, call_claude)
                response = caller(text, lang)
                if not response:
                    print(f"    ⚠ Pas de réponse — ignoré")
                    continue

            # Insérer le run
            conn.execute(
                "INSERT INTO runs (prompt_id, llm, language, raw_response, run_date, is_demo) "
                "VALUES (?,?,?,?,?,?)",
                (prompt["id"], provider, lang, response[:2000], today, int(demo_mode))
            )
            conn.commit()
            run_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

            # Scorer toutes les marques
            for b in all_brands:
                if b not in brand_ids:
                    continue
                sc = score_response(response, b, [x for x in all_brands if x != b])
                conn.execute(
                    "INSERT INTO results (run_id, brand_id, mentioned, mention_count, "
                    "position, sentiment, geo_score) VALUES (?,?,?,?,?,?,?)",
                    (run_id, brand_ids[b], sc["mentioned"], sc["mention_count"],
                     sc["position"], sc["sentiment"], sc["geo_score"])
                )

                if b == brand:
                    key = (lang, provider)
                    if key not in results_agg:
                        results_agg[key] = []
                    results_agg[key].append(sc["geo_score"])

            conn.commit()

    # Résumé
    print(f"\n{'='*60}")
    print(f"  RÉSULTATS — {brand}")
    for (lang, provider), scores in sorted(results_agg.items()):
        avg = round(sum(scores) / len(scores)) if scores else 0
        print(f"  [{lang}] [{provider}] GEO Score moyen : {avg}/100 ({len(scores)} prompts)")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa Tracker Générique")
    parser.add_argument("--config", help="Chemin vers le fichier config JSON")
    parser.add_argument("--demo",   action="store_true", help="Mode démo sans API")
    parser.add_argument("--list",   action="store_true", help="Lister les configs disponibles")
    parser.add_argument("--create", help="Créer une config minimale pour un slug")
    args = parser.parse_args()

    if args.list:
        configs = list_configs()
        if not configs:
            print("Aucune config trouvée dans configs/")
        else:
            print("Configs disponibles :")
            for c in configs:
                cfg = load_config(c)
                print(f"  {c.name} → {cfg['client_name']} ({cfg['vertical']})")
        sys.exit(0)

    if args.create:
        CONFIG_DIR.mkdir(exist_ok=True)
        slug = args.create
        template = {
            "slug":          slug,
            "client_name":   slug.title(),
            "primary_brand": slug.title(),
            "vertical":      "sport",
            "markets":       ["fr"],
            "competitors":   {
                "fr": ["Concurrent 1", "Concurrent 2", "Concurrent 3"]
            }
        }
        path = CONFIG_DIR / f"{slug}.json"
        with open(path, "w") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        print(f"✓ Config créée : {path}")
        print(f"  Éditez le fichier puis lancez : python3 tracker_generic.py --config {path}")
        sys.exit(0)

    if not args.config:
        parser.print_help()
        sys.exit(1)

    cfg = load_config(args.config)
    run_tracker(cfg, demo_mode=args.demo)