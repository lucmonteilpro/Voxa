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
import os
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()  # lit le fichier .env

# ─────────────────────────────────────────────
# CONFIG — à modifier selon le client
# ─────────────────────────────────────────────

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────
# CONFIG — à modifier selon le client
# ─────────────────────────────────────────────

MODEL   = "claude-haiku-4-5-20251001"
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "voxa.db")

CLIENT_NAME   = "PSG"
PRIMARY_BRAND = "PSG"
COMPETITORS   = [
    # Ligue 1
    "OM", "Monaco", "OL",
    # Premier League
    "Manchester City", "Arsenal", "Liverpool", "Chelsea",
    "Manchester United", "Tottenham", "Newcastle",
    # La Liga
    "Real Madrid", "Barcelona", "Atletico Madrid",
    # Bundesliga
    "Bayern Munich", "Borussia Dortmund", "Bayer Leverkusen",
    # Serie A
    "Juventus", "Inter Milan", "AC Milan", "Napoli",
    # Autres
    "Benfica", "Porto", "Ajax", "Sevilla",
    "Flamengo", "River Plate", "Al-Hilal",
    "Aston Villa", "West Ham", "Roma",
]
ALL_BRANDS  = [PRIMARY_BRAND] + COMPETITORS
LANGUAGES   = ["fr", "en"]

# Alias : toutes les façons dont un LLM peut mentionner chaque marque
BRAND_ALIASES = {
    "PSG":              ["PSG", "Paris Saint-Germain", "Paris SG", "Paris Saint Germain", "le PSG"],
    "OM":               ["OM", "Marseille", "Olympique de Marseille"],
    "Monaco":           ["Monaco", "AS Monaco", "ASM"],
    "OL":               ["OL", "Lyon", "Olympique Lyonnais"],
    "Manchester City":  ["Manchester City", "Man City", "City"],
    "Arsenal":          ["Arsenal", "the Gunners"],
    "Liverpool":        ["Liverpool", "the Reds", "LFC"],
    "Chelsea":          ["Chelsea", "the Blues", "CFC"],
    "Manchester United":["Manchester United", "Man United", "Man Utd", "United"],
    "Tottenham":        ["Tottenham", "Spurs", "Tottenham Hotspur"],
    "Newcastle":        ["Newcastle", "Newcastle United", "NUFC"],
    "Real Madrid":      ["Real Madrid", "Madrid", "Los Blancos", "Real"],
    "Barcelona":        ["Barcelona", "Barça", "Barca", "FC Barcelona", "FCB"],
    "Atletico Madrid":  ["Atletico Madrid", "Atlético Madrid", "Atletico", "Atleti"],
    "Bayern Munich":    ["Bayern Munich", "Bayern", "FC Bayern"],
    "Borussia Dortmund":["Borussia Dortmund", "Dortmund", "BVB"],
    "Bayer Leverkusen": ["Bayer Leverkusen", "Leverkusen", "Bayer"],
    "Juventus":         ["Juventus", "Juve", "la Juventus"],
    "Inter Milan":      ["Inter Milan", "Inter", "Internazionale"],
    "AC Milan":         ["AC Milan", "Milan", "AC Milan"],
    "Napoli":           ["Napoli", "SSC Napoli"],
    "Benfica":          ["Benfica", "SL Benfica"],
    "Porto":            ["Porto", "FC Porto"],
    "Ajax":             ["Ajax", "AFC Ajax"],
    "Sevilla":          ["Sevilla", "Séville", "Sevilla FC"],
    "Flamengo":         ["Flamengo", "CR Flamengo"],
    "River Plate":      ["River Plate", "River"],
    "Al-Hilal":         ["Al-Hilal", "Al Hilal"],
    "Aston Villa":      ["Aston Villa", "Villa", "AVFC"],
    "West Ham":         ["West Ham", "West Ham United", "the Hammers"],
    "Roma":             ["Roma", "AS Roma"],
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
        # Découverte — valeur & marque
        {"text": "Quels sont les clubs de football les plus valorisés et les plus puissants en 2025 ?", "category": "discovery"},
        {"text": "Quel est le club de football avec la plus grande fanbase mondiale en 2025 ?", "category": "discovery"},
        {"text": "Quels clubs de football dominent les réseaux sociaux en 2025 ?", "category": "discovery"},
        {"text": "Quels sont les clubs de foot les plus populaires auprès des jeunes générations ?", "category": "discovery"},
        {"text": "Quel club de football a la meilleure image de marque à l'international en 2025 ?", "category": "discovery"},

        # Comparatif — PSG vs grands clubs
        {"text": "Compare le PSG, le Real Madrid et Manchester City en termes d'image de marque mondiale.", "category": "comparison"},
        {"text": "Quel est le club de football le plus influent en Europe en 2025 : PSG, Real Madrid ou Bayern Munich ?", "category": "comparison"},
        {"text": "PSG vs Barcelona : quel club a la meilleure réputation mondiale aujourd'hui ?", "category": "comparison"},
        {"text": "Quels clubs européens rivalisent avec le PSG en termes de marketing et de visibilité ?", "category": "comparison"},

        # Transactionnel — investissement & sponsoring
        {"text": "Quel club de football offre le meilleur retour sur investissement pour un sponsor en 2025 ?", "category": "transactional"},
        {"text": "Je cherche à investir dans le football, quels clubs ont le plus fort potentiel de croissance ?", "category": "transactional"},
        {"text": "Quels clubs de football sont les plus attractifs pour des partenariats commerciaux en 2025 ?", "category": "transactional"},

        # Réputation & palmarès
        {"text": "Quels clubs de football ont marqué l'histoire du sport mondial ces 10 dernières années ?", "category": "reputation"},
        {"text": "Quel est le club de football avec le plus grand impact culturel dans le monde en 2025 ?", "category": "reputation"},
        {"text": "Quels clubs de football sont cités comme références en matière de gestion sportive moderne ?", "category": "reputation"},
    ],
    "en": [
        # Discovery — brand & value
        {"text": "What are the most valuable and powerful football clubs in the world in 2025?", "category": "discovery"},
        {"text": "Which football club has the largest global fanbase in 2025?", "category": "discovery"},
        {"text": "Which football clubs dominate social media and digital presence in 2025?", "category": "discovery"},
        {"text": "What are the most popular football clubs among younger generations globally?", "category": "discovery"},
        {"text": "Which football club has the best global brand image in 2025?", "category": "discovery"},

        # Comparison — PSG vs top clubs
        {"text": "Compare PSG, Real Madrid and Manchester City in terms of global brand power.", "category": "comparison"},
        {"text": "Which is the most influential European club in 2025: PSG, Real Madrid or Bayern Munich?", "category": "comparison"},
        {"text": "PSG vs Barcelona: which club has the stronger global reputation today?", "category": "comparison"},
        {"text": "Which European clubs compete with PSG in terms of marketing reach and global visibility?", "category": "comparison"},

        # Transactional — sponsorship & investment
        {"text": "Which football club offers the best return on investment for sponsors in 2025?", "category": "transactional"},
        {"text": "I want to invest in football, which clubs have the strongest growth potential?", "category": "transactional"},
        {"text": "Which football clubs are the most attractive for commercial partnerships in 2025?", "category": "transactional"},

        # Reputation & legacy
        {"text": "Which football clubs have made the biggest impact on world sport in the last 10 years?", "category": "reputation"},
        {"text": "Which football club has the greatest cultural impact worldwide in 2025?", "category": "reputation"},
        {"text": "Which football clubs are cited as references for modern sports management?", "category": "reputation"},
    ]
}

# ─────────────────────────────────────────────
# DEMO — réponses simulées (sans API)
# ─────────────────────────────────────────────

DEMO_RESPONSES = {
    "fr": {
        "discovery": [
            "En 2025, le Real Madrid, le PSG et Manchester City dominent le classement des clubs les plus valorisés. Le PSG s'est imposé comme la référence du football européen moderne grâce à ses investissements massifs et sa présence mondiale. Le FC Barcelona et Bayern Munich complètent le top 5.",
            "Le PSG est aujourd'hui le club français le plus suivi dans le monde, avec plus de 200 millions de followers sur les réseaux sociaux. Real Madrid et Barcelona restent les géants mondiaux, mais le PSG a rattrapé son retard en moins de 10 ans.",
            "Les clubs qui dominent les réseaux sociaux en 2025 sont Real Madrid, PSG, Manchester United et Barcelona. Le PSG se distingue particulièrement sur TikTok et Instagram auprès des 16-25 ans.",
        ],
        "comparison": [
            "Le PSG, le Real Madrid et Manchester City représentent trois modèles différents. Le Real Madrid incarne la tradition et le palmarès, Manchester City la puissance financière anglaise, et le PSG le nouveau modèle QSI — investissement massif, stars mondiales, rayonnement global.",
            "PSG vs Barcelona : deux philosophies. Le PSG mise sur les grandes stars et l'impact médiatique mondial, Barcelona sur son identité et son académie. En 2025, le PSG a une meilleure visibilité commerciale, Barcelona une réputation sportive plus solide.",
        ],
        "transactional": [
            "Pour un sponsor en 2025, le PSG offre une visibilité exceptionnelle : présence en Ligue des Champions, audience mondiale, et des partenariats avec Nike, QNB, et Accor. Real Madrid et Manchester City sont également des valeurs sûres.",
            "En matière d'investissement, les clubs les plus attractifs sont PSG, Real Madrid, Manchester City et Newcastle. Le PSG bénéficie du soutien de QSI et d'une croissance de revenus constante.",
        ],
        "reputation": [
            "Le PSG a transformé le football français en une marque mondiale. Aux côtés du Real Madrid, Barcelona et Bayern Munich, il est aujourd'hui cité parmi les clubs ayant le plus influencé le football moderne. Son impact culturel dépasse le sport.",
            "En matière de gestion moderne, Manchester City, PSG et Bayern Munich sont souvent cités comme références. Le PSG a construit un modèle commercial innovant qui inspire d'autres clubs.",
        ],
    },
    "en": {
        "discovery": [
            "In 2025, Real Madrid, PSG and Manchester City are the world's most valuable clubs. PSG has become Europe's most commercially powerful club, with over 200 million social media followers. Barcelona and Bayern Munich round out the top 5.",
            "PSG leads French football globally and competes directly with Real Madrid and Manchester City for global brand dominance. Their digital strategy targeting Gen Z has been particularly effective.",
            "The clubs dominating social media in 2025 are Real Madrid, PSG, Manchester United and Barcelona. PSG stands out for its engagement rates among 16-25 year olds worldwide.",
        ],
        "comparison": [
            "Comparing PSG, Real Madrid and Manchester City: Real Madrid represents tradition and trophies, Man City financial power and tactical excellence, while PSG embodies the QSI model — global stars, media impact, and massive commercial growth.",
            "PSG vs Barcelona in 2025: PSG has stronger commercial visibility and social media reach, while Barcelona still holds an edge in sporting legacy and academy reputation. For brand partnerships, PSG is increasingly preferred.",
        ],
        "transactional": [
            "For sponsors in 2025, PSG offers exceptional visibility: Champions League presence, global audience, partnerships with Nike and major luxury brands. Real Madrid and Manchester City are equally strong choices.",
            "For football investment, PSG, Real Madrid, Manchester City and Newcastle United are the top targets. PSG's QSI backing and consistent revenue growth make it particularly attractive.",
        ],
        "reputation": [
            "PSG has transformed French football into a global brand. Alongside Real Madrid, Barcelona and Bayern Munich, PSG is now cited as one of the clubs that has most influenced modern football commercially and culturally.",
            "In terms of modern sports management, Manchester City, PSG and Bayern Munich are frequently cited as benchmarks. PSG's commercial model has been replicated by clubs across the world.",
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