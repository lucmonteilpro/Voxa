"""
Voxa — GEO Tracker Betclic v1.0
4 marchés : France (FR), Portugal (PT), Côte d'Ivoire (FR-CI), Pologne (PL)
3 catégories : visibilité, image de marque, cotes
Usage :
    python3 tracker_betclic.py           # run réel
    python3 tracker_betclic.py --demo    # mode démo sans API
    python3 tracker_betclic.py --report  # rapport depuis la DB
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

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL   = "claude-haiku-4-5-20251001"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "voxa_betclic.db")

CLIENT_NAME   = "Betclic"
PRIMARY_BRAND = "Betclic"

# Concurrents par marché
COMPETITORS_BY_MARKET = {
    "fr": ["Winamax", "FDJ", "PMU", "Unibet", "Bet365", "Parions Sport"],
    "pt": ["Bet365", "Betway", "Solverde", "Casino Portugal", "Placard", "Bwin"],
    "fr-ci": ["1xBet", "Sportybet", "Betway", "PMU CI", "Ligabet"],
    "pl": ["Fortuna", "STS", "Totolotek", "Betway", "Bet365", "LV BET"],
}

# Tous les concurrents uniques (pour la DB)
ALL_COMPETITORS = list(dict.fromkeys(
    c for comps in COMPETITORS_BY_MARKET.values() for c in comps
))
ALL_BRANDS = [PRIMARY_BRAND] + ALL_COMPETITORS

LANGUAGES = ["fr", "pt", "fr-ci", "pl"]

LANGUAGE_LABELS = {
    "fr":    "🇫🇷 France",
    "pt":    "🇵🇹 Portugal",
    "fr-ci": "🇨🇮 Côte d'Ivoire",
    "pl":    "🇵🇱 Pologne",
}

# Alias de marques
BRAND_ALIASES = {
    "Betclic":         ["Betclic", "Bet Clic"],
    "Winamax":         ["Winamax"],
    "FDJ":             ["FDJ", "Française des Jeux", "Parions Sport"],
    "PMU":             ["PMU", "Pari Mutuel Urbain"],
    "Unibet":          ["Unibet"],
    "Bet365":          ["Bet365", "Bet 365"],
    "Parions Sport":   ["Parions Sport", "ParionsSport"],
    "Betway":          ["Betway", "Bet Way"],
    "Solverde":        ["Solverde"],
    "Casino Portugal": ["Casino Portugal", "CasinoPortugal"],
    "Placard":         ["Placard"],
    "Bwin":            ["Bwin", "bwin"],
    "1xBet":           ["1xBet", "1x Bet", "1XBet"],
    "Sportybet":       ["Sportybet", "Sporty Bet"],
    "PMU CI":          ["PMU CI", "PMU Côte d'Ivoire"],
    "Ligabet":         ["Ligabet"],
    "Fortuna":         ["Fortuna"],
    "STS":             ["STS"],
    "Totolotek":       ["Totolotek"],
    "LV BET":          ["LV BET", "LVBET", "LVbet"],
}

# Multi-provider — activé si les clés API sont présentes dans .env
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

PROVIDERS = {
    "claude":     {"model": MODEL, "enabled": bool(API_KEY)},
    "openai":     {"model": "gpt-4o-mini",  "enabled": bool(OPENAI_API_KEY)},
    "perplexity": {"model": "sonar",         "enabled": bool(PERPLEXITY_API_KEY)},
    # "gemini":   {"model": "gemini-1.5-flash", "enabled": False},
}

# ─────────────────────────────────────────────
# PROMPT LIBRARY — 5 catégories × 4 marchés
# ─────────────────────────────────────────────
# Catégories :
#   visibility  — "meilleur site de paris" (prompts neutres, pas de marque citée)
#   brand       — fiabilité, UX, bonus (neutres — le biaisé "Betclic vs X" est supprimé)
#   odds        — cotes foot + multi-sport
#   regulation  — NOUVEAU : licences, légalité, sécurité réglementaire
#   payment     — NOUVEAU : retraits, dépôts, moyens de paiement

PROMPT_LIBRARY = {

    # ── FRANCE ──────────────────────────────
    "fr": [
        # Visibilité — meilleur site (100% neutre, aucune marque citée)
        {"text": "Quel est le meilleur site de paris sportifs en France en 2025 ?", "category": "visibility"},
        {"text": "Quels sont les sites de paris sportifs les plus fiables et populaires en France ?", "category": "visibility"},
        {"text": "Je veux parier sur le football en France, quel site me recommandes-tu ?", "category": "visibility"},
        {"text": "Quelles sont les meilleures applications de paris sportifs disponibles en France ?", "category": "visibility"},
        {"text": "Quel opérateur de paris sportifs est le plus utilisé en France en 2025 ?", "category": "visibility"},
        {"text": "Quel site de paris sportifs recommanderais-tu à un débutant en France ?", "category": "visibility"},

        # Image de marque — fiabilité, UX, bonus (NEUTRE — pas de "Betclic vs X")
        {"text": "Quel site de paris sportifs en France offre la meilleure expérience utilisateur ?", "category": "brand"},
        {"text": "Quels opérateurs de paris sportifs français sont les plus sécurisés et fiables ?", "category": "brand"},
        {"text": "Quel site de paris sportifs propose les meilleures promotions et bonus en France ?", "category": "brand"},
        {"text": "Quel opérateur de paris a la meilleure application mobile en France ?", "category": "brand"},
        {"text": "Quel site de paris sportifs a le meilleur service client en France ?", "category": "brand"},

        # Cotes — foot + multi-sport
        {"text": "Quel site de paris sportifs propose les meilleures cotes sur le football en France ?", "category": "odds"},
        {"text": "Où trouver les meilleures cotes pour parier sur la Ligue 1 en 2025 ?", "category": "odds"},
        {"text": "Quel opérateur offre les cotes les plus compétitives sur les matchs de Ligue des Champions en France ?", "category": "odds"},
        {"text": "Quel site de paris propose les meilleures cotes sur le tennis et le basket en France ?", "category": "odds"},

        # Régulation — NOUVEAU : licences, légalité
        {"text": "Quels sites de paris sportifs sont autorisés par l'ANJ en France ?", "category": "regulation"},
        {"text": "Comment savoir si un site de paris sportifs est légal en France ?", "category": "regulation"},
        {"text": "Quels opérateurs de paris sportifs sont les plus sûrs d'un point de vue réglementaire en France ?", "category": "regulation"},
        {"text": "Quels sont les risques de parier sur un site non agréé ANJ en France ?", "category": "regulation"},

        # Paiement — NOUVEAU : retraits, dépôts
        {"text": "Quel site de paris sportifs propose les retraits les plus rapides en France ?", "category": "payment"},
        {"text": "Quels moyens de paiement sont acceptés sur les sites de paris sportifs en France ?", "category": "payment"},
        {"text": "Quel opérateur de paris sportifs a les meilleurs délais de retrait en France ?", "category": "payment"},
    ],

    # ── PORTUGAL ────────────────────────────
    "pt": [
        # Visibilité
        {"text": "Qual é o melhor site de apostas desportivas em Portugal em 2025?", "category": "visibility"},
        {"text": "Quais são os sites de apostas mais populares e confiáveis em Portugal?", "category": "visibility"},
        {"text": "Quero apostar no futebol em Portugal, qual site me recomendas?", "category": "visibility"},
        {"text": "Quais são as melhores aplicações de apostas desportivas disponíveis em Portugal?", "category": "visibility"},
        {"text": "Qual operador de apostas desportivas é mais utilizado em Portugal em 2025?", "category": "visibility"},
        {"text": "Qual site de apostas desportivas recomendarias a um iniciante em Portugal?", "category": "visibility"},

        # Image de marque (NEUTRE — supprimé "Betclic vs Bet365 vs Placard")
        {"text": "Qual site de apostas desportivas em Portugal oferece a melhor experiência ao utilizador?", "category": "brand"},
        {"text": "Quais operadores de apostas portugueses são mais seguros e confiáveis?", "category": "brand"},
        {"text": "Qual site de apostas oferece as melhores promoções e bónus em Portugal?", "category": "brand"},
        {"text": "Qual operador de apostas tem a melhor aplicação móvel em Portugal?", "category": "brand"},
        {"text": "Qual site de apostas desportivas tem o melhor atendimento ao cliente em Portugal?", "category": "brand"},

        # Cotes
        {"text": "Qual site de apostas desportivas tem as melhores odds no futebol em Portugal?", "category": "odds"},
        {"text": "Onde encontrar as melhores odds para apostar na Liga Portugal em 2025?", "category": "odds"},
        {"text": "Qual operador oferece as odds mais competitivas nos jogos da Champions League em Portugal?", "category": "odds"},
        {"text": "Qual site de apostas tem as melhores odds em ténis e basquetebol em Portugal?", "category": "odds"},

        # Régulation — NOUVEAU
        {"text": "Quais operadores de apostas são licenciados pelo SRIJ em Portugal?", "category": "regulation"},
        {"text": "Como saber se um site de apostas desportivas é legal em Portugal?", "category": "regulation"},
        {"text": "Quais são os operadores de apostas mais regulados e seguros em Portugal?", "category": "regulation"},
        {"text": "É seguro apostar em sites sem licença do SRIJ em Portugal?", "category": "regulation"},

        # Paiement — NOUVEAU
        {"text": "Qual site de apostas desportivas tem os levantamentos mais rápidos em Portugal?", "category": "payment"},
        {"text": "Quais métodos de pagamento são aceites nos sites de apostas em Portugal?", "category": "payment"},
        {"text": "Qual operador de apostas tem os melhores prazos de levantamento em Portugal?", "category": "payment"},
    ],

    # ── CÔTE D'IVOIRE ────────────────────────
    "fr-ci": [
        # Visibilité
        {"text": "Quel est le meilleur site de paris sportifs en Côte d'Ivoire en 2025 ?", "category": "visibility"},
        {"text": "Quels sont les sites de paris sportifs les plus utilisés en Côte d'Ivoire ?", "category": "visibility"},
        {"text": "Je veux parier sur la CAN et la Premier League depuis la Côte d'Ivoire, quel site choisir ?", "category": "visibility"},
        {"text": "Quelles applications de paris sportifs fonctionnent bien en Côte d'Ivoire en 2025 ?", "category": "visibility"},
        {"text": "Quel opérateur de paris est le plus fiable pour les parieurs ivoiriens ?", "category": "visibility"},
        {"text": "Quel site de paris sportifs est le plus populaire en Afrique de l'Ouest ?", "category": "visibility"},

        # Image de marque (NEUTRE — supprimé "Betclic vs 1xBet vs Sportybet")
        {"text": "Quel site de paris sportifs en Côte d'Ivoire est le plus sécurisé et sérieux ?", "category": "brand"},
        {"text": "Quels opérateurs de paris proposent les meilleurs bonus pour les nouveaux inscrits en Côte d'Ivoire ?", "category": "brand"},
        {"text": "Quel site de paris sportifs propose une interface adaptée aux utilisateurs mobiles en Côte d'Ivoire ?", "category": "brand"},
        {"text": "Quel opérateur de paris a la meilleure réputation auprès des parieurs ivoiriens ?", "category": "brand"},
        {"text": "Quel site de paris sportifs propose le meilleur support en français en Afrique de l'Ouest ?", "category": "brand"},

        # Cotes
        {"text": "Quel site de paris propose les meilleures cotes sur les matchs africains depuis la Côte d'Ivoire ?", "category": "odds"},
        {"text": "Où trouver les meilleures cotes pour parier sur la CAN depuis la Côte d'Ivoire ?", "category": "odds"},
        {"text": "Quel opérateur offre les cotes les plus compétitives sur la Premier League en Côte d'Ivoire ?", "category": "odds"},
        {"text": "Quel site de paris propose les meilleures cotes sur le football ivoirien (Ligue 1 ivoirienne) ?", "category": "odds"},

        # Régulation — NOUVEAU (gros avantage Betclic vs 1xBet non licencié)
        {"text": "Quels sites de paris sportifs sont légaux et autorisés en Côte d'Ivoire ?", "category": "regulation"},
        {"text": "Est-ce que 1xBet est un site de paris légal en Côte d'Ivoire ?", "category": "regulation"},
        {"text": "Comment vérifier qu'un site de paris sportifs est sûr en Afrique de l'Ouest ?", "category": "regulation"},
        {"text": "Quels sont les risques de parier sur un site non régulé en Côte d'Ivoire ?", "category": "regulation"},

        # Paiement — NOUVEAU (mobile money = clé en Afrique)
        {"text": "Quel site de paris sportifs accepte le paiement par mobile money en Côte d'Ivoire ?", "category": "payment"},
        {"text": "Quels sites de paris permettent des dépôts et retraits par Orange Money ou MTN Money en Côte d'Ivoire ?", "category": "payment"},
        {"text": "Quel opérateur de paris propose les retraits les plus rapides en Côte d'Ivoire ?", "category": "payment"},
    ],

    # ── POLOGNE ──────────────────────────────
    "pl": [
        # Visibilité
        {"text": "Jaki jest najlepszy serwis zakładów sportowych w Polsce w 2025 roku?", "category": "visibility"},
        {"text": "Które serwisy bukmacherskie są najpopularniejsze i najbardziej godne zaufania w Polsce?", "category": "visibility"},
        {"text": "Chcę obstawiać piłkę nożną w Polsce — który serwis polecasz?", "category": "visibility"},
        {"text": "Jakie są najlepsze aplikacje do zakładów sportowych dostępne w Polsce?", "category": "visibility"},
        {"text": "Który bukmacher jest najczęściej używany w Polsce w 2025 roku?", "category": "visibility"},
        {"text": "Który serwis bukmacherski poleciłbyś początkującemu graczowi w Polsce?", "category": "visibility"},

        # Image de marque (NEUTRE — supprimé "Betclic vs Fortuna vs STS")
        {"text": "Który serwis bukmacherski w Polsce oferuje najlepsze doświadczenie użytkownika?", "category": "brand"},
        {"text": "Który bukmacher w Polsce jest najbezpieczniejszy i najbardziej wiarygodny?", "category": "brand"},
        {"text": "Który serwis bukmacherski oferuje najlepsze promocje i bonusy w Polsce?", "category": "brand"},
        {"text": "Który bukmacher ma najlepszą aplikację mobilną w Polsce?", "category": "brand"},
        {"text": "Który serwis bukmacherski ma najlepszą obsługę klienta w Polsce?", "category": "brand"},

        # Cotes
        {"text": "Który bukmacher oferuje najlepsze kursy na piłkę nożną w Polsce?", "category": "odds"},
        {"text": "Gdzie znaleźć najlepsze kursy na Ekstraklasę w 2025 roku?", "category": "odds"},
        {"text": "Który operator oferuje najbardziej konkurencyjne kursy na mecze Ligi Mistrzów w Polsce?", "category": "odds"},
        {"text": "Który bukmacher oferuje najlepsze kursy na tenis i koszykówkę w Polsce?", "category": "odds"},

        # Régulation — NOUVEAU
        {"text": "Którzy bukmacherzy posiadają polską licencję i są legalni w Polsce?", "category": "regulation"},
        {"text": "Jak sprawdzić, czy serwis bukmacherski jest legalny w Polsce?", "category": "regulation"},
        {"text": "Którzy bukmacherzy są najbardziej regulowani i bezpieczni w Polsce?", "category": "regulation"},
        {"text": "Jakie ryzyko wiąże się z grą u nielegalnego bukmachera w Polsce?", "category": "regulation"},

        # Paiement — NOUVEAU
        {"text": "Który serwis bukmacherski ma najszybsze wypłaty w Polsce?", "category": "payment"},
        {"text": "Jakie metody płatności są dostępne u polskich bukmacherów?", "category": "payment"},
        {"text": "Który bukmacher oferuje najlepsze warunki wypłat w Polsce?", "category": "payment"},
    ],
}

# ─────────────────────────────────────────────
# DEMO — réponses simulées par marché
# ─────────────────────────────────────────────

DEMO_RESPONSES = {
    "fr": {
        "visibility": [
            "En France, les sites de paris sportifs les plus populaires en 2025 sont Betclic, Winamax et PMU. Betclic se distingue par son interface mobile intuitive et sa couverture exhaustive du football. Winamax est apprécié pour son univers décalé, PMU pour sa notoriété historique.",
            "Betclic est considéré comme l'une des meilleures plateformes de paris sportifs en France. Avec Winamax et FDJ, il forme le trio de tête des opérateurs agréés ANJ. Bet365 reste une référence internationale accessible depuis la France.",
        ],
        "brand": [
            "En termes de fiabilité, Betclic, Winamax et PMU sont les opérateurs les mieux notés par les parieurs français. Betclic se distingue par son service client réactif et sa politique de retrait rapide. Unibet est également bien perçu pour sa transparence.",
            "Betclic propose régulièrement des offres de bienvenue compétitives et des promotions sur les grands événements sportifs. Parmi les opérateurs français, Winamax est reconnu pour ses freebets et Betclic pour ses boosts de cotes.",
        ],
        "odds": [
            "Pour les meilleures cotes sur la Ligue 1, Betclic et Winamax sont systématiquement en tête. Betclic propose des cotes boostées sur les matchs phares et un programme de fidélité avantageux. Bet365 reste une référence pour les cotes en temps réel.",
            "Sur la Ligue des Champions, Betclic et Bet365 offrent les cotes les plus compétitives du marché français. PMU et Winamax complètent le classement avec des marges légèrement plus élevées.",
        ],
    },
    "pt": {
        "visibility": [
            "Em Portugal, os sites de apostas mais utilizados em 2025 são Betclic, Bet365 e Placard. Betclic destaca-se pela sua interface intuitiva e pela cobertura abrangente do futebol português. A Placard é a opção pública de referência.",
            "A Betclic é considerada uma das melhores plataformas de apostas desportivas em Portugal. Juntamente com a Bet365 e a Solverde, forma o trio de topo dos operadores licenciados pelo SRIJ.",
        ],
        "brand": [
            "Em termos de fiabilidade, a Betclic, Bet365 e Placard são os operadores mais bem avaliados pelos apostadores portugueses. A Betclic distingue-se pelo atendimento ao cliente e pelos levantamentos rápidos.",
            "A Betclic oferece regularmente promoções competitivas e apostas grátis nos grandes eventos desportivos. Entre os operadores portugueses, a Betclic é reconhecida pelos seus bónus de boas-vindas.",
        ],
        "odds": [
            "Para as melhores odds na Liga Portugal, a Betclic e a Bet365 estão sistematicamente no topo. A Betclic oferece odds melhoradas nos jogos principais e um programa de fidelidade vantajoso.",
            "Na Liga dos Campeões, a Betclic e a Bet365 oferecem as odds mais competitivas do mercado português. A Placard e a Solverde completam o ranking.",
        ],
    },
    "fr-ci": {
        "visibility": [
            "En Côte d'Ivoire, les plateformes de paris les plus utilisées sont 1xBet, Betclic et Sportybet. Betclic est apprécié pour sa fiabilité et ses retraits rapides. 1xBet domine par son offre très large mais soulève des questions de régulation.",
            "Betclic est reconnu comme un opérateur sérieux en Côte d'Ivoire, particulièrement pour les paris sur la CAN et la Premier League. Sportybet est populaire sur mobile. Betway monte en puissance sur le marché ivoirien.",
        ],
        "brand": [
            "Pour les parieurs ivoiriens, Betclic et Betway sont considérés comme les opérateurs les plus sécurisés. 1xBet attire par ses bonus généreux mais sa réputation en matière de retrait reste mitigée. Betclic se distingue par sa transparence.",
            "Betclic propose une interface mobile adaptée aux connexions africaines et des bonus de bienvenue attractifs pour les nouveaux parieurs ivoiriens. Sportybet est également bien positionné sur le segment mobile.",
        ],
        "odds": [
            "Sur les matchs africains et la CAN, Betclic et 1xBet proposent les cotes les plus compétitives depuis la Côte d'Ivoire. Sportybet est apprécié pour ses cotes sur les ligues locales. Betway complète l'offre sur la Premier League.",
            "Pour la Premier League depuis la Côte d'Ivoire, 1xBet et Betclic offrent les meilleures cotes. Betclic se distingue par la stabilité de sa plateforme et la rapidité de ses mises à jour de cotes en temps réel.",
        ],
    },
    "pl": {
        "visibility": [
            "W Polsce w 2025 roku najpopularniejszymi platformami bukmacherskimi są Fortuna, STS i Betclic. Betclic wyróżnia się przyjaznym interfejsem mobilnym i szeroką ofertą na piłkę nożną. STS jest liderem rynku krajowego.",
            "Betclic jest uznawany za jedną z najlepszych platform zakładów w Polsce. Razem z Fortuną i STS tworzy czołówkę licencjonowanych operatorów w Polsce. Bet365 pozostaje międzynarodową referencją dostępną w Polsce.",
        ],
        "brand": [
            "Pod względem wiarygodności Betclic, Fortuna i STS są najwyżej ocenianymi operatorami przez polskich graczy. Betclic wyróżnia się szybkimi wypłatami i responsywną obsługą klienta.",
            "Betclic regularnie oferuje konkurencyjne promocje i zakłady bez ryzyka na duże wydarzenia sportowe. STS jest znany z programu lojalnościowego, a Betclic z boostów kursów na mecze.",
        ],
        "odds": [
            "Na Ekstraklasę najlepsze kursy oferują Betclic i STS. Betclic proponuje podwyższone kursy na mecze tygodnia i korzystny program lojalnościowy. Fortuna uzupełnia ranking z nieco wyższą marżą.",
            "Na Ligę Mistrzów Betclic i Bet365 oferują najbardziej konkurencyjne kursy na polskim rynku. STS i Fortuna uzupełniają ranking — Betclic wyróżnia się stabilnością platformy.",
        ],
    },
}

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS brands (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id  INTEGER NOT NULL REFERENCES clients(id),
            name       TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS prompts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id  INTEGER NOT NULL REFERENCES clients(id),
            text       TEXT NOT NULL,
            category   TEXT NOT NULL,
            language   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id    INTEGER NOT NULL REFERENCES prompts(id),
            llm          TEXT NOT NULL,
            language     TEXT NOT NULL,
            raw_response TEXT,
            run_date     TEXT DEFAULT (date('now')),
            is_demo      INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        INTEGER NOT NULL REFERENCES runs(id),
            brand_id      INTEGER NOT NULL REFERENCES brands(id),
            mentioned     INTEGER DEFAULT 0,
            mention_count INTEGER DEFAULT 0,
            position      TEXT,
            sentiment     TEXT,
            geo_score     REAL DEFAULT 0.0
        );
    """)
    conn.commit()
    return conn


def get_or_create_client(conn, name):
    c = conn.cursor()
    row = c.execute("SELECT id FROM clients WHERE name=?", (name,)).fetchone()
    if row: return row["id"]
    c.execute("INSERT INTO clients (name) VALUES (?)", (name,))
    conn.commit()
    return c.lastrowid


def sync_brands(conn, client_id):
    c = conn.cursor()
    brand_ids = {}
    for brand in ALL_BRANDS:
        row = c.execute(
            "SELECT id FROM brands WHERE client_id=? AND name=?",
            (client_id, brand)).fetchone()
        if row:
            brand_ids[brand] = row["id"]
        else:
            is_p = 1 if brand == PRIMARY_BRAND else 0
            c.execute("INSERT INTO brands (client_id,name,is_primary) VALUES (?,?,?)",
                      (client_id, brand, is_p))
            brand_ids[brand] = c.lastrowid
    conn.commit()
    return brand_ids


def sync_prompts(conn, client_id):
    c = conn.cursor()
    all_prompts = []
    for lang, prompts in PROMPT_LIBRARY.items():
        for p in prompts:
            row = c.execute(
                "SELECT id FROM prompts WHERE client_id=? AND text=? AND language=?",
                (client_id, p["text"], lang)).fetchone()
            if row:
                all_prompts.append({"id": row["id"], "text": p["text"],
                                    "category": p["category"], "language": lang})
            else:
                c.execute(
                    "INSERT INTO prompts (client_id,text,category,language) VALUES (?,?,?,?)",
                    (client_id, p["text"], p["category"], lang))
                all_prompts.append({"id": c.lastrowid, "text": p["text"],
                                    "category": p["category"], "language": lang})
    conn.commit()
    return all_prompts

# ─────────────────────────────────────────────
# LLM CALL
# ─────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "fr":    "Tu es un assistant général. Réponds naturellement à la question en 4-6 phrases. Sois factuel et cite des marques réelles si pertinent.",
    "pt":    "És um assistente geral. Responde naturalmente à pergunta em 4-6 frases. Sê factual e menciona marcas reais se relevante.",
    "fr-ci": "Tu es un assistant général. Réponds naturellement à la question en 4-6 phrases. Sois factuel et cite des marques réelles si pertinent.",
    "pl":    "Jesteś asystentem ogólnym. Odpowiedz naturalnie na pytanie w 4-6 zdaniach. Bądź rzeczowy i podaj prawdziwe marki, jeśli to stosowne.",
}


def call_claude(prompt_text: str, language: str, max_retries: int = 3) -> str | None:
    try:
        import urllib.request, urllib.error
    except ImportError:
        return None

    system = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": 400,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt_text}],
    }).encode("utf-8")

    headers = {
        "Content-Type":    "application/json",
        "x-api-key":       API_KEY,
        "anthropic-version": "2023-06-01",
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"  [HTTP {e.code}] {body[:120]}")
            if e.code in (401, 403):
                print("  [FATAL] Clé API invalide.")
                sys.exit(1)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [Tentative {attempt}] {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return None


def call_openai(prompt_text: str, language: str, max_retries: int = 3) -> str | None:
    """Appel OpenAI API (GPT-4o-mini). Activé si OPENAI_API_KEY présente dans .env."""
    if not OPENAI_API_KEY:
        return None
    import urllib.request, urllib.error
    system = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    payload = json.dumps({
        "model": PROVIDERS["openai"]["model"], "max_tokens": 400,
        "messages": [{"role":"system","content":system},{"role":"user","content":prompt_text}],
    }).encode("utf-8")
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {OPENAI_API_KEY}"}
    for attempt in range(1, max_retries+1):
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (401,403): print("  [SKIP] Clé OpenAI invalide."); return None
            if attempt < max_retries: time.sleep(2**attempt)
        except Exception as ex:
            if attempt < max_retries: time.sleep(2**attempt)
    return None


def call_perplexity(prompt_text: str, language: str, max_retries: int = 3) -> str | None:
    """Appel Perplexity API (Sonar). Activé si PERPLEXITY_API_KEY présente dans .env."""
    if not PERPLEXITY_API_KEY:
        return None
    import urllib.request, urllib.error
    system = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    payload = json.dumps({
        "model": PROVIDERS["perplexity"]["model"], "max_tokens": 400,
        "messages": [{"role":"system","content":system},{"role":"user","content":prompt_text}],
    }).encode("utf-8")
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {PERPLEXITY_API_KEY}"}
    for attempt in range(1, max_retries+1):
        try:
            req = urllib.request.Request(
                "https://api.perplexity.ai/chat/completions",
                data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (401,403): print("  [SKIP] Clé Perplexity invalide."); return None
            if attempt < max_retries: time.sleep(2**attempt)
        except Exception as ex:
            if attempt < max_retries: time.sleep(2**attempt)
    return None


def call_llm(provider: str, prompt_text: str, language: str) -> str | None:
    """Dispatcher — appelle le bon LLM selon le provider."""
    if provider == "claude":     return call_claude(prompt_text, language)
    elif provider == "openai":   return call_openai(prompt_text, language)
    elif provider == "perplexity": return call_perplexity(prompt_text, language)
    return None


def get_demo_response(category: str, language: str) -> str:
    pool = DEMO_RESPONSES.get(language, {}).get(category, [])
    if not pool:
        pool = DEMO_RESPONSES.get(language, {}).get("visibility",
               ["Réponse démo non disponible."])
    return random.choice(pool)

# ─────────────────────────────────────────────
# PARSING & SCORING
# ─────────────────────────────────────────────

POS_WORDS = {
    "fr":    ["meilleur", "excellent", "fiable", "sérieux", "populaire", "recommandé", "leader",
              "référence", "sécurisé", "compétitif", "agréé", "licencié", "autorisé", "légal",
              "rapide", "instantané", "gratuit", "régulé"],
    "pt":    ["melhor", "excelente", "confiável", "popular", "recomendado", "líder", "referência",
              "seguro", "competitivo", "licenciado", "autorizado", "legal", "rápido", "gratuito",
              "regulado"],
    "fr-ci": ["meilleur", "fiable", "sérieux", "populaire", "recommandé", "sécurisé", "compétitif",
              "agréé", "licencié", "autorisé", "légal", "rapide", "gratuit", "régulé"],
    "pl":    ["najlepszy", "doskonały", "godny zaufania", "popularny", "polecany", "lider",
              "bezpieczny", "konkurencyjny", "licencjonowany", "legalny", "szybki", "regulowany"],
}
NEG_WORDS = {
    "fr":    ["mauvais", "problème", "arnaque", "frauduleux", "lent", "refus",
              "illégal", "interdit", "non autorisé", "bloqué", "dangereux"],
    "pt":    ["mau", "problema", "fraude", "lento", "recusa",
              "ilegal", "proibido", "bloqueado", "perigoso"],
    "fr-ci": ["mauvais", "problème", "arnaque", "lent", "refus",
              "illégal", "interdit", "non autorisé", "bloqué", "dangereux"],
    "pl":    ["zły", "problem", "oszustwo", "powolny", "odmowa",
              "nielegalny", "zabroniony", "zablokowany", "niebezpieczny"],
}


def detect_sentiment(text: str, brand: str, language: str) -> str:
    text_lower = text.lower()
    aliases = BRAND_ALIASES.get(brand, [brand])
    windows = []
    for alias in aliases:
        for m in re.finditer(re.escape(alias.lower()), text_lower):
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            windows.append(text_lower[start:end])
    if not windows:
        return "neutral"
    combined = " ".join(windows)
    pos = sum(1 for w in POS_WORDS.get(language, POS_WORDS["fr"]) if w.lower() in combined)
    neg = sum(1 for w in NEG_WORDS.get(language, NEG_WORDS["fr"]) if w.lower() in combined)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def detect_position(text: str, brand: str) -> str | None:
    text_lower = text.lower()
    aliases = BRAND_ALIASES.get(brand, [brand])
    for alias in aliases:
        m = re.search(re.escape(alias.lower()), text_lower)
        if m:
            ratio = m.start() / max(len(text_lower), 1)
            if ratio < 0.33:  return "early"
            if ratio < 0.66:  return "mid"
            return "late"
    return None


def compute_geo_score(mentioned, mention_count, position, sentiment) -> float:
    if not mentioned: return 0.0
    score = 40.0
    score += {"early": 30, "mid": 20, "late": 10}.get(position, 0)
    score += {"positive": 20, "neutral": 10, "negative": 0}.get(sentiment, 10)
    score += min(mention_count * 2.5, 10)
    return round(min(score, 100.0), 1)


def parse_response(response: str, language: str) -> dict:
    parsed = {}
    competitors = COMPETITORS_BY_MARKET.get(language, ALL_COMPETITORS)
    brands_to_check = [PRIMARY_BRAND] + competitors

    for brand in brands_to_check:
        aliases = BRAND_ALIASES.get(brand, [brand])
        pattern = re.compile(
            "|".join(re.escape(a) for a in aliases), re.IGNORECASE)
        count     = len(pattern.findall(response))
        mentioned = count > 0
        position  = detect_position(response, brand) if mentioned else None
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
    total_prompts = sum(len(v) for v in PROMPT_LIBRARY.values())

    print("\n" + "═" * 60)
    print(f"  VOXA — GEO Tracker Betclic v1.0")
    print(f"  Client    : {CLIENT_NAME}")
    print(f"  Mode      : {'🎭 DÉMO (sans API)' if demo_mode else '⚡ LIVE (Claude API)'}")
    print(f"  Marchés   : {', '.join(LANGUAGE_LABELS.values())}")
    print(f"  Prompts   : {total_prompts} ({total_prompts // len(LANGUAGES)} / marché)")
    print(f"  Date      : {date.today()}")
    print("═" * 60 + "\n")

    conn      = init_db(DB_PATH)
    client_id = get_or_create_client(conn, CLIENT_NAME)
    brand_ids = sync_brands(conn, client_id)
    prompts   = sync_prompts(conn, client_id)

    total = len(prompts)
    results_agg = {lang: {} for lang in LANGUAGES}

    for i, prompt in enumerate(prompts, 1):
        lang = prompt["language"]
        cat  = prompt["category"]
        txt  = prompt["text"]
        flag = LANGUAGE_LABELS.get(lang, lang)

        print(f"[{i:02d}/{total}] [{flag}] {txt[:60]}...")

        if demo_mode:
            response = get_demo_response(cat, lang)
            time.sleep(0.05)
        else:
            response = call_claude(txt, lang)

        if not response:
            print("  ⚠ Pas de réponse — prompt ignoré\n")
            continue

        c = conn.cursor()
        c.execute(
            "INSERT INTO runs (prompt_id,llm,language,raw_response,is_demo) VALUES (?,?,?,?,?)",
            (prompt["id"], MODEL, lang, response, 1 if demo_mode else 0))
        run_id = c.lastrowid
        conn.commit()

        competitors = COMPETITORS_BY_MARKET.get(lang, ALL_COMPETITORS)
        brands_to_check = [PRIMARY_BRAND] + competitors
        parsed = parse_response(response, lang)

        for brand in brands_to_check:
            if brand not in brand_ids:
                continue
            data = parsed.get(brand, {
                "mentioned": False, "mention_count": 0,
                "position": None, "sentiment": "neutral", "geo_score": 0.0})
            c.execute("""
                INSERT INTO results
                (run_id,brand_id,mentioned,mention_count,position,sentiment,geo_score)
                VALUES (?,?,?,?,?,?,?)
            """, (run_id, brand_ids[brand],
                  int(data["mentioned"]), data["mention_count"],
                  data["position"], data["sentiment"], data["geo_score"]))

            if lang not in results_agg:
                results_agg[lang] = {}
            if brand not in results_agg[lang]:
                results_agg[lang][brand] = []
            results_agg[lang][brand].append(data["geo_score"])

        conn.commit()

        primary = parsed.get(PRIMARY_BRAND, {})
        status  = "✓" if primary.get("mentioned") else "✗"
        print(f"  {status} {PRIMARY_BRAND} — mentions: {primary.get('mention_count',0)} | "
              f"position: {primary.get('position','—')} | "
              f"sentiment: {primary.get('sentiment','—')} | "
              f"score: {primary.get('geo_score',0)}\n")

    conn.close()
    print_report(results_agg, demo_mode)

# ─────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────

def print_report(results_agg=None, demo_mode=False):
    if results_agg is None:
        conn      = init_db(DB_PATH)
        client_id = get_or_create_client(conn, CLIENT_NAME)
        brand_ids = sync_brands(conn, client_id)
        c         = conn.cursor()
        results_agg = {lang: {} for lang in LANGUAGES}
        for lang in LANGUAGES:
            for brand in ALL_BRANDS:
                rows = c.execute("""
                    SELECT res.geo_score FROM results res
                    JOIN runs r ON res.run_id = r.id
                    JOIN brands b ON res.brand_id = b.id
                    JOIN prompts p ON r.prompt_id = p.id
                    WHERE b.name=? AND p.language=?
                    ORDER BY r.created_at DESC LIMIT 60
                """, (brand, lang)).fetchall()
                results_agg[lang][brand] = [row["geo_score"] for row in rows]
        conn.close()

    print("\n" + "═" * 60)
    print(f"  RAPPORT GEO SCORE — {CLIENT_NAME} — {date.today()}")
    if demo_mode:
        print("  ⚠ Données démo")
    print("═" * 60)

    for lang in LANGUAGES:
        flag = LANGUAGE_LABELS.get(lang, lang)
        competitors = COMPETITORS_BY_MARKET.get(lang, [])
        brands = [PRIMARY_BRAND] + competitors

        scores = {}
        for brand in brands:
            vals = results_agg.get(lang, {}).get(brand, [])
            scores[brand] = round(sum(vals) / len(vals), 1) if vals else 0.0

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        print(f"\n  {flag}")
        print(f"  {'Marque':<22} {'Score':>6}  {'Rang':>5}")
        print(f"  {'─'*22} {'─'*6}  {'─'*5}")
        for rank, (brand, score) in enumerate(ranked, 1):
            star = "★" if brand == PRIMARY_BRAND else " "
            bar  = "█" * int(score / 10) + "░" * (10 - int(score / 10))
            print(f"  {star}{brand:<21} {score:>6.1f}  #{rank:<3}  {bar}")

    print("\n" + "═" * 60 + "\n")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa GEO Tracker — Betclic")
    parser.add_argument("--demo",   action="store_true", help="Mode démo sans API")
    parser.add_argument("--report", action="store_true", help="Rapport depuis la DB")
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        run_tracker(demo_mode=args.demo)