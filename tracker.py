"""
Voxa — GEO Tracker v1.0
Mesure la présence d'une marque dans les réponses des LLMs.
Usage :
    python tracker.py            # run réel (Claude API)
    python tracker.py --demo     # mode démo sans API
    python tracker.py --report   # affiche le dernier rapport
"""

import sqlite3
import json
import re
import sys
import time
import random
import argparse
from datetime import datetime, date

# ─────────────────────────────────────────────
# CONFIG — à modifier selon le client
# ─────────────────────────────────────────────

import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MODEL       = "claude-haiku-4-5-20251001"
DB_PATH     = "voxa.db"

CLIENT_NAME   = "OM"
PRIMARY_BRAND = "OM"
COMPETITORS   = ["PSG", "OL", "Monaco"]
ALL_BRANDS    = [PRIMARY_BRAND] + COMPETITORS
LANGUAGES     = ["fr", "en"]

# Alias : toutes les façons dont un LLM peut mentionner chaque marque
BRAND_ALIASES = {
    "OM":     ["OM", "Marseille", "Olympique de Marseille", "Olympique Marseille"],
    "PSG":    ["PSG", "Paris Saint-Germain", "Paris SG", "Paris Saint Germain"],
    "OL":     ["OL", "Lyon", "Olympique Lyonnais"],
    "Monaco": ["Monaco", "AS Monaco", "ASM"],
}

# Multi-provider — structure préparée, providers alternatifs hashés pour V2
PROVIDERS = {
    "claude": {"model": MODEL, "enabled": True},
    # "openai":     {"model": "gpt-4o-mini",                          "enabled": False},  # TODO V2
    # "gemini":     {"model": "gemini-1.5-flash",                     "enabled": False},  # TODO V2
    # "perplexity": {"model": "llama-3.1-sonar-small-128k-online",    "enabled": False},  # TODO V2
}

# ─────────────────────────────────────────────
# PROMPT LIBRARY
# ─────────────────────────────────────────────

PROMPT_LIBRARY = {
    "fr": [
        # Découverte
        {"text": "Quel est le club de foot avec la meilleure ambiance en France en 2025 ?", "category": "discovery"},
        {"text": "Quel club de Ligue 1 est le plus populaire auprès des supporters en 2025 ?", "category": "discovery"},
        {"text": "Quels sont les clubs de football français les plus suivis sur les réseaux sociaux ?", "category": "discovery"},
        {"text": "Quel est le club de foot français avec le plus grand nombre de supporters à l'étranger ?", "category": "discovery"},
        # Comparatif
        {"text": "Compare l'ambiance au Vélodrome de Marseille versus le Parc des Princes à Paris.", "category": "comparison"},
        {"text": "Quel est le meilleur club de Ligue 1 en termes d'expérience supporter en 2025 ?", "category": "comparison"},
        {"text": "PSG ou OM : quel club a la plus grande base de fans passionnés en France ?", "category": "comparison"},
        # Transactionnel
        {"text": "Je veux regarder du football français de qualité, quel club dois-je suivre ?", "category": "transactional"},
        {"text": "Quel club de foot français mérite le plus d'être soutenu par un nouveau fan ?", "category": "transactional"},
        # Sentiment / réputation
        {"text": "Quels clubs de Ligue 1 ont la meilleure réputation en Europe en 2025 ?", "category": "reputation"},
        {"text": "Quel club de football français est le plus respecté à l'international ?", "category": "reputation"},
    ],
    "en": [
        # Découverte
        {"text": "Which French football club has the best atmosphere and fans in 2025?", "category": "discovery"},
        {"text": "What is the most popular Ligue 1 club internationally in 2025?", "category": "discovery"},
        {"text": "Which French football team has the biggest global fanbase?", "category": "discovery"},
        {"text": "What are the top French football clubs to follow in 2025?", "category": "discovery"},
        # Comparatif
        {"text": "Compare Olympique de Marseille and Paris Saint-Germain fan culture.", "category": "comparison"},
        {"text": "Which Ligue 1 club offers the best match day experience for fans?", "category": "comparison"},
        {"text": "PSG vs OM vs Lyon: which French club has the most passionate supporters?", "category": "comparison"},
        # Transactionnel
        {"text": "I want to start following French football, which club should I support?", "category": "transactional"},
        {"text": "Which French football club is worth watching for a new international fan?", "category": "transactional"},
        # Reputation
        {"text": "Which French football clubs are most respected in Europe in 2025?", "category": "reputation"},
        {"text": "What is the best French club in terms of history and global recognition?", "category": "reputation"},
    ]
}

# ─────────────────────────────────────────────
# DEMO — réponses simulées (sans API)
# ─────────────────────────────────────────────

DEMO_RESPONSES = {
    "fr": {
        "discovery": [
            "L'OM reste le club avec la meilleure ambiance en France. Le Vélodrome est électrique. Le PSG a la puissance financière, l'OL une belle histoire, Monaco les résultats récents, mais l'atmosphère à Marseille est incomparable.",
            "En 2025, l'OM domine le classement ambiance. Marseille vibre pour ses joueurs comme aucune autre ville. Le PSG attire les stars, mais l'OL et Monaco peinent à rivaliser côté supporters.",
            "Le PSG est le club le plus médiatisé, mais l'OM reste le plus ancré dans la culture populaire française. OL et Monaco sont des clubs solides mais moins passionnants.",
        ],
        "comparison": [
            "Le Vélodrome de l'OM est l'un des stades les plus impressionnants d'Europe. Le Parc des Princes du PSG est moderne mais l'ambiance y est plus froide. L'OL au Groupama Stadium monte, Monaco reste confidentiel.",
            "OM vs PSG : deux cultures opposées. L'OM c'est la passion populaire, le PSG c'est le glamour. En termes d'ambiance pure, l'OM gagne haut la main.",
        ],
        "transactional": [
            "Si vous cherchez un club français avec de l'émotion, choisissez l'OM. La ville de Marseille vit pour son club. Le PSG est une option pour les amateurs de stars, l'OL pour ceux qui aiment la régularité.",
        ],
        "reputation": [
            "L'OM est le seul club français à avoir remporté la Ligue des Champions. Sa réputation en Europe reste solide. Le PSG est reconnu pour ses investissements, Monaco pour sa formation. L'OL a une belle histoire européenne.",
        ],
    },
    "en": {
        "discovery": [
            "Olympique de Marseille (OM) stands out as the most passionate French club in 2025. The Vélodrome is legendary. PSG has the global fame, Lyon the history, Monaco the recent trophies, but OM fans are in a league of their own.",
            "PSG dominates globally due to their spending, but OM has the most authentic supporter culture in France. Monaco and Lyon are solid clubs but lack that raw passion.",
        ],
        "comparison": [
            "OM vs PSG is the classic French rivalry. OM brings working-class passion and a legendary stadium. PSG brings star power. In terms of atmosphere, OM wins every time.",
        ],
        "transactional": [
            "For a new international fan, PSG is the easy choice for star power. But if you want real passion and history, support OM — the only French club to win the Champions League.",
        ],
        "reputation": [
            "OM remains France's most iconic club internationally, known for their 1993 Champions League title. PSG has risen thanks to investment, Monaco is respected for developing talent, Lyon for consistency.",
        ],
    }
}

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    """Crée la base SQLite et les tables si elles n'existent pas."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS brands (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id   INTEGER NOT NULL REFERENCES clients(id),
            name        TEXT NOT NULL,
            is_primary  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS prompts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id   INTEGER NOT NULL REFERENCES clients(id),
            text        TEXT NOT NULL,
            category    TEXT NOT NULL,
            language    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id     INTEGER NOT NULL REFERENCES prompts(id),
            llm           TEXT NOT NULL,
            language      TEXT NOT NULL,
            raw_response  TEXT,
            run_date      TEXT DEFAULT (date('now')),
            is_demo       INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES runs(id),
            brand_id        INTEGER NOT NULL REFERENCES brands(id),
            mentioned       INTEGER DEFAULT 0,
            mention_count   INTEGER DEFAULT 0,
            position        TEXT,
            sentiment       TEXT,
            geo_score       REAL DEFAULT 0.0
        );
    """)

    conn.commit()
    return conn


def get_or_create_client(conn: sqlite3.Connection, name: str) -> int:
    """Retourne l'id du client, le crée si inexistant."""
    c = conn.cursor()
    row = c.execute("SELECT id FROM clients WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    c.execute("INSERT INTO clients (name) VALUES (?)", (name,))
    conn.commit()
    return c.lastrowid


def sync_brands(conn: sqlite3.Connection, client_id: int) -> dict:
    """Synchronise les marques en base, retourne {name: id}."""
    c = conn.cursor()
    brand_ids = {}
    for brand in ALL_BRANDS:
        row = c.execute(
            "SELECT id FROM brands WHERE client_id = ? AND name = ?",
            (client_id, brand)
        ).fetchone()
        if row:
            brand_ids[brand] = row["id"]
        else:
            is_primary = 1 if brand == PRIMARY_BRAND else 0
            c.execute(
                "INSERT INTO brands (client_id, name, is_primary) VALUES (?, ?, ?)",
                (client_id, brand, is_primary)
            )
            brand_ids[brand] = c.lastrowid
    conn.commit()
    return brand_ids


def sync_prompts(conn: sqlite3.Connection, client_id: int) -> list:
    """Synchronise la prompt library en base, retourne la liste complète."""
    c = conn.cursor()
    all_prompts = []
    for lang, prompts in PROMPT_LIBRARY.items():
        for p in prompts:
            row = c.execute(
                "SELECT id FROM prompts WHERE client_id = ? AND text = ? AND language = ?",
                (client_id, p["text"], lang)
            ).fetchone()
            if row:
                all_prompts.append({"id": row["id"], "text": p["text"], "category": p["category"], "language": lang})
            else:
                c.execute(
                    "INSERT INTO prompts (client_id, text, category, language) VALUES (?, ?, ?, ?)",
                    (client_id, p["text"], p["category"], lang)
                )
                all_prompts.append({"id": c.lastrowid, "text": p["text"], "category": p["category"], "language": lang})
    conn.commit()
    return all_prompts

# ─────────────────────────────────────────────
# LLM CALL
# ─────────────────────────────────────────────

def call_claude(prompt_text: str, language: str, max_retries: int = 3) -> str | None:
    """Appelle Claude Haiku et retourne la réponse brute. Retry sur erreur réseau."""
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print("  [ERREUR] urllib non disponible")
        return None

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 400,
        "system": (
            "Tu es un assistant général. Réponds naturellement à la question posée en 4-6 phrases. "
            "Sois factuel et cite des marques ou clubs réels si pertinent."
        ) if language == "fr" else (
            "You are a general assistant. Answer the question naturally in 4-6 sentences. "
            "Be factual and mention real brands or clubs if relevant."
        ),
        "messages": [{"role": "user", "content": prompt_text}]
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"  [HTTP {e.code}] {body[:120]}")
            if e.code in (401, 403):
                print("  [FATAL] Clé API invalide. Arrêt.")
                sys.exit(1)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [Tentative {attempt}] Erreur : {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    return None


def get_demo_response(category: str, language: str) -> str:
    """Retourne une réponse simulée pour le mode démo."""
    pool = DEMO_RESPONSES.get(language, {}).get(category, [])
    if not pool:
        pool = DEMO_RESPONSES[language].get("discovery", ["Réponse démo non disponible."])
    return random.choice(pool)

# ─────────────────────────────────────────────
# PARSING & SCORING
# ─────────────────────────────────────────────

POSITIVE_WORDS_FR = ["meilleur", "excellent", "incroyable", "légendaire", "passionné", "électrique", "incomparable", "solide", "respecté", "populaire"]
NEGATIVE_WORDS_FR = ["décevant", "faible", "mauvais", "pauvre", "insuffisant", "médiocre"]
POSITIVE_WORDS_EN = ["best", "great", "legendary", "passionate", "iconic", "excellent", "outstanding", "respected", "popular", "dominant"]
NEGATIVE_WORDS_EN = ["disappointing", "weak", "poor", "bad", "mediocre", "insufficient"]


def detect_sentiment(text: str, brand: str, language: str) -> str:
    """Détecte le sentiment autour d'une marque dans le texte."""
    # Fenêtre de 80 chars autour de chaque mention
    text_lower = text.lower()
    brand_lower = brand.lower()
    windows = []

    for m in re.finditer(re.escape(brand_lower), text_lower):
        start = max(0, m.start() - 80)
        end = min(len(text_lower), m.end() + 80)
        windows.append(text_lower[start:end])

    if not windows:
        return "neutral"

    combined = " ".join(windows)
    pos_words = POSITIVE_WORDS_FR if language == "fr" else POSITIVE_WORDS_EN
    neg_words = NEGATIVE_WORDS_FR if language == "fr" else NEGATIVE_WORDS_EN

    pos = sum(1 for w in pos_words if w in combined)
    neg = sum(1 for w in neg_words if w in combined)

    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def detect_position(text: str, brand: str) -> str:
    """Détecte si la marque est citée en début, milieu ou fin de réponse."""
    text_lower = text.lower()
    brand_lower = brand.lower()
    match = re.search(re.escape(brand_lower), text_lower)
    if not match:
        return None
    ratio = match.start() / max(len(text_lower), 1)
    if ratio < 0.33:
        return "early"
    if ratio < 0.66:
        return "mid"
    return "late"


def compute_geo_score(mentioned: bool, mention_count: int, position: str, sentiment: str) -> float:
    """
    Calcul du GEO Score sur 100 :
    - Mention         : 40 pts
    - Position        : 30 pts (early > mid > late)
    - Sentiment       : 20 pts
    - Fréquence       : 10 pts
    """
    if not mentioned:
        return 0.0

    # Mention (40 pts)
    score = 40.0

    # Position (30 pts)
    position_scores = {"early": 30, "mid": 20, "late": 10}
    score += position_scores.get(position, 0)

    # Sentiment (20 pts)
    sentiment_scores = {"positive": 20, "neutral": 10, "negative": 0}
    score += sentiment_scores.get(sentiment, 10)

    # Fréquence (10 pts) — capé à 10
    score += min(mention_count * 2.5, 10)

    return round(min(score, 100.0), 1)


def parse_response(response: str, language: str) -> dict:
    """Parse la réponse LLM pour toutes les marques via leurs alias. Retourne un dict brand → résultats."""
    parsed = {}
    for brand in ALL_BRANDS:
        # Construit un pattern qui matche le nom principal + tous ses alias
        aliases = BRAND_ALIASES.get(brand, [brand])
        pattern = re.compile(
            "|".join(re.escape(a) for a in aliases),
            re.IGNORECASE
        )
        matches = pattern.findall(response)
        count   = len(matches)
        mentioned = count > 0
        position  = detect_position(response, aliases[0]) if mentioned else None
        sentiment = detect_sentiment(response, brand, language) if mentioned else "neutral"
        geo_score = compute_geo_score(mentioned, count, position, sentiment)

        parsed[brand] = {
            "mentioned":     mentioned,
            "mention_count": count,
            "position":      position,
            "sentiment":     sentiment,
            "geo_score":     geo_score,
        }
    return parsed

# ─────────────────────────────────────────────
# TRACKER PRINCIPAL
# ─────────────────────────────────────────────

def run_tracker(demo_mode: bool = False):
    """Boucle principale : pour chaque prompt, appelle le LLM, parse, stocke."""

    print("\n" + "═" * 55)
    print(f"  VOXA — GEO Tracker v1.0")
    print(f"  Client    : {CLIENT_NAME}")
    print(f"  Mode      : {'🎭 DÉMO (sans API)' if demo_mode else '⚡ LIVE (Claude API)'}")
    print(f"  Langues   : {', '.join(LANGUAGES)}")
    print(f"  Prompts   : {sum(len(v) for v in PROMPT_LIBRARY.values())}")
    print(f"  LLM       : {MODEL}")
    print(f"  Date      : {date.today()}")
    print("═" * 55 + "\n")

    # Init DB
    conn = init_db(DB_PATH)
    client_id = get_or_create_client(conn, CLIENT_NAME)
    brand_ids = sync_brands(conn, client_id)
    prompts = sync_prompts(conn, client_id)

    total = len(prompts)
    results_agg = {lang: {b: [] for b in ALL_BRANDS} for lang in LANGUAGES}

    for i, prompt in enumerate(prompts, 1):
        lang = prompt["language"]
        cat = prompt["category"]
        txt = prompt["text"]

        print(f"[{i:02d}/{total}] [{lang.upper()}] {txt[:65]}...")

        # Appel LLM ou démo
        if demo_mode:
            response = get_demo_response(cat, lang)
            time.sleep(0.1)  # simule la latence
        else:
            response = call_claude(txt, lang)

        if not response:
            print("  ⚠ Pas de réponse — prompt ignoré\n")
            continue

        # Stockage du run
        c = conn.cursor()
        c.execute(
            "INSERT INTO runs (prompt_id, llm, language, raw_response, is_demo) VALUES (?, ?, ?, ?, ?)",
            (prompt["id"], MODEL, lang, response, 1 if demo_mode else 0)
        )
        run_id = c.lastrowid
        conn.commit()

        # Parse + stockage des résultats
        parsed = parse_response(response, lang)
        for brand, data in parsed.items():
            c.execute("""
                INSERT INTO results (run_id, brand_id, mentioned, mention_count, position, sentiment, geo_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, brand_ids[brand],
                int(data["mentioned"]), data["mention_count"],
                data["position"], data["sentiment"], data["geo_score"]
            ))
            results_agg[lang][brand].append(data["geo_score"])

        conn.commit()

        # Log mention principale
        primary = parsed[PRIMARY_BRAND]
        status = "✓" if primary["mentioned"] else "✗"
        print(f"  {status} {PRIMARY_BRAND} — mentions: {primary['mention_count']} | position: {primary['position']} | sentiment: {primary['sentiment']} | score: {primary['geo_score']}\n")

    conn.close()

    # Rapport final
    print_report(results_agg, demo_mode)


# ─────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────

def print_report(results_agg: dict = None, demo_mode: bool = False):
    """Affiche le rapport GEO Score consolidé."""

    if results_agg is None:
        # Lecture depuis la DB
        conn = init_db(DB_PATH)
        client_id = get_or_create_client(conn, CLIENT_NAME)
        brand_ids = sync_brands(conn, client_id)
        c = conn.cursor()
        results_agg = {lang: {b: [] for b in ALL_BRANDS} for lang in LANGUAGES}
        for lang in LANGUAGES:
            for brand in ALL_BRANDS:
                rows = c.execute("""
                    SELECT res.geo_score
                    FROM results res
                    JOIN runs r ON res.run_id = r.id
                    JOIN brands b ON res.brand_id = b.id
                    JOIN prompts p ON r.prompt_id = p.id
                    WHERE b.name = ? AND p.language = ?
                    ORDER BY r.created_at DESC
                    LIMIT 50
                """, (brand, lang)).fetchall()
                results_agg[lang][brand] = [row["geo_score"] for row in rows]
        conn.close()

    print("\n" + "═" * 55)
    print(f"  RAPPORT GEO SCORE — {CLIENT_NAME} — {date.today()}")
    if demo_mode:
        print("  ⚠ Données démo (non réelles)")
    print("═" * 55)

    for lang in LANGUAGES:
        print(f"\n  Langue : {lang.upper()}")
        print(f"  {'Marque':<12} {'Score':>6}  {'Rang':>5}  {'#Prompts':>8}")
        print(f"  {'─'*12} {'─'*6}  {'─'*5}  {'─'*8}")

        scores_lang = {}
        for brand in ALL_BRANDS:
            vals = results_agg[lang][brand]
            scores_lang[brand] = round(sum(vals) / len(vals), 1) if vals else 0.0

        ranked = sorted(scores_lang.items(), key=lambda x: x[1], reverse=True)
        for rank, (brand, score) in enumerate(ranked, 1):
            is_primary = "★" if brand == PRIMARY_BRAND else " "
            bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
            n = len(results_agg[lang][brand])
            print(f"  {is_primary}{brand:<11} {score:>6.1f}  #{rank:<4}  {n:>6} prompts  {bar}")

    print("\n" + "═" * 55 + "\n")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa GEO Tracker")
    parser.add_argument("--demo",   action="store_true", help="Mode démo sans appel API")
    parser.add_argument("--report", action="store_true", help="Affiche le rapport depuis la DB")
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        run_tracker(demo_mode=args.demo)