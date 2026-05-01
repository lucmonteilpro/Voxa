"""
Voxa — Tracker UI (Perplexity headed)
======================================
Tracker en mode UI qui interroge Perplexity via le navigateur (vs API).
Réutilise toute la logique de scoring de tracker.py pour garantir la
cohérence des données avec l'historique.

Différences vs tracker.py :
- Pas d'API key requise (login Perplexity manuel persistant)
- Réponses = celles vues réellement par les utilisateurs (pas API stub)
- Sources web réelles capturées + screenshot pour audit
- Stocke dans les nouvelles colonnes (screenshot_path, crawl_duration_ms, crawl_method='ui')
- Insère les sources dans la table `sources` (jointe à `runs`)

Compatibilité :
- Réutilise sync_brands, sync_prompts, init_db de tracker.py
- Réutilise parse_response (donc compute_geo_score, detect_sentiment, detect_position)
- Les runs UI apparaissent dans le dashboard à côté des runs API existants
- Distinction via `runs.crawl_method` ('api' pour anciens, 'ui' pour nouveaux)

Usage :
    # Run sur 5 prompts FR pour tester
    python3 tracker_ui.py --slug betclic --language fr --limit 5

    # Run complet sur un marché
    python3 tracker_ui.py --slug betclic --language fr

    # Run complet sur tous les marchés (long, ~25min/marché)
    python3 tracker_ui.py --slug betclic

    # Mode dry-run : crawl sans écrire en DB (pour debug)
    python3 tracker_ui.py --slug betclic --language fr --limit 3 --dry-run

Workflow recommandé :
1. D'abord --limit 3 --dry-run pour vérifier que ça crawl correctement
2. Puis --limit 5 sans dry-run pour vérifier que ça écrit en DB
3. Puis --language fr (un marché complet, ~25min)
4. Puis sans --language (tous les marchés, plusieurs heures)
"""

import argparse
import random
import sys
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Réutilisation de la logique métier existante
from tracker import (
    init_db, get_or_create_client, sync_brands, sync_prompts,
    parse_response,
    PRIMARY_BRAND, COMPETITORS_BY_MARKET, ALL_COMPETITORS,
    LANGUAGE_LABELS, MODEL,
)

# Crawler UI
from crawlers.perplexity import PerplexityCrawler
from crawlers.base import CrawlerResult

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# Délais entre prompts (anti-rate-limit + détection bot)
DELAY_MIN_S = 8       # minimum entre 2 prompts
DELAY_MAX_S = 15      # maximum entre 2 prompts
LONG_PAUSE_EVERY = 20 # toutes les N prompts → pause longue
LONG_PAUSE_S = 60     # durée pause longue


# ─────────────────────────────────────────────
# DB persistence (étendue par rapport à tracker.py)
# ─────────────────────────────────────────────
def insert_run_with_ui_metadata(conn: sqlite3.Connection,
                                  prompt_id: int,
                                  language: str,
                                  result: CrawlerResult) -> int:
    """Insert un run en DB avec les nouvelles colonnes UI (migration v2).

    Retourne le run_id créé.
    """
    c = conn.cursor()
    c.execute("""
        INSERT INTO runs (
            prompt_id, llm, language, raw_response,
            is_demo, created_at,
            screenshot_path, crawl_duration_ms, crawl_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        prompt_id,
        result.model_used or "perplexity-default",
        language,
        result.response_text,
        0,  # not demo
        datetime.now().isoformat(),
        result.screenshot_path,
        result.crawl_duration_ms,
        "ui",  # crawl_method = UI (vs 'api' pour les anciens)
    ))
    run_id = c.lastrowid
    conn.commit()
    return run_id


def insert_results_for_brands(conn: sqlite3.Connection,
                               run_id: int,
                               brand_ids: dict,
                               parsed: dict,
                               brands_to_check: list) -> None:
    """Insert les résultats par marque (mention, sentiment, geo_score)."""
    c = conn.cursor()
    for brand in brands_to_check:
        if brand not in brand_ids:
            continue
        data = parsed.get(brand, {
            "mentioned": False, "mention_count": 0,
            "position": None, "sentiment": "neutral", "geo_score": 0.0
        })
        c.execute("""
            INSERT INTO results
            (run_id, brand_id, mentioned, mention_count, position, sentiment, geo_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, brand_ids[brand],
            int(data["mentioned"]), data["mention_count"],
            data["position"], data["sentiment"], data["geo_score"]
        ))
    conn.commit()


def insert_sources(conn: sqlite3.Connection,
                    run_id: int,
                    sources: list) -> int:
    """Insert les sources URL citées dans la nouvelle table `sources`.

    Retourne le nombre de sources insérées.
    """
    if not sources:
        return 0
    c = conn.cursor()
    n = 0
    for src in sources:
        # src est un CrawlerSource dataclass
        c.execute("""
            INSERT INTO sources
            (run_id, url, title, domain, position, snippet)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            src.url,
            src.title,
            src.domain,
            src.position,
            src.snippet,
        ))
        n += 1
    conn.commit()
    return n


# ─────────────────────────────────────────────
# Affichage console
# ─────────────────────────────────────────────
def print_header(slug: str, language: Optional[str], n_prompts: int, dry_run: bool):
    print("\n" + "═" * 70)
    print(f"  VOXA — UI Tracker (Perplexity headed)")
    print(f"  Client    : {slug}")
    print(f"  Marchés   : {language.upper() if language else 'TOUS'}")
    print(f"  Prompts   : {n_prompts}")
    print(f"  Mode      : {'🔍 DRY-RUN (pas d écriture DB)' if dry_run else '💾 LIVE (DB)'}")
    print(f"  Date      : {date.today()}")
    print("═" * 70 + "\n")


def print_progress(idx: int, total: int, lang: str, prompt_text: str,
                    result: CrawlerResult, parsed: dict, n_sources: int):
    """Affiche le résultat d'une query en console."""
    flag = LANGUAGE_LABELS.get(lang, lang)
    primary = parsed.get(PRIMARY_BRAND, {})
    status = "✓" if primary.get("mentioned") else "✗"

    print(f"\n[{idx:02d}/{total}] [{flag}] {prompt_text[:60]}")
    if result.error:
        print(f"   ⚠ ERREUR : {result.error}")
        return
    print(f"   ⏱  {result.crawl_duration_ms}ms  ·  "
          f"📝 {len(result.response_text)} chars  ·  "
          f"🔗 {n_sources} sources")
    print(f"   {status} {PRIMARY_BRAND} — mentions: {primary.get('mention_count', 0)} | "
          f"position: {primary.get('position', '—')} | "
          f"sentiment: {primary.get('sentiment', '—')} | "
          f"score: {primary.get('geo_score', 0)}")


def print_summary(stats: dict):
    print("\n" + "═" * 70)
    print(f"  RÉCAPITULATIF")
    print("═" * 70)
    print(f"  Prompts traités    : {stats['total']}")
    print(f"  Succès             : {stats['success']}")
    print(f"  Échecs             : {stats['failed']}")
    print(f"  Mentions {PRIMARY_BRAND}     : {stats['mentioned']}/{stats['success']}")
    print(f"  Score moyen {PRIMARY_BRAND}: {stats['avg_score']:.1f}/100")
    print(f"  Sources collectées : {stats['total_sources']}")
    print(f"  Durée totale       : {stats['duration_min']:.1f} min")
    print("═" * 70 + "\n")


# ─────────────────────────────────────────────
# Filtre prompts
# ─────────────────────────────────────────────
def filter_prompts(all_prompts: list,
                    language_filter: Optional[str],
                    limit: Optional[int]) -> list:
    """Filtre la liste des prompts selon language et limit."""
    filtered = all_prompts
    if language_filter:
        filtered = [p for p in filtered if p["language"] == language_filter]
    if limit:
        filtered = filtered[:limit]
    return filtered


# ─────────────────────────────────────────────
# RUNNER PRINCIPAL
# ─────────────────────────────────────────────
def run_ui_tracker(slug: str,
                    language: Optional[str] = None,
                    limit: Optional[int] = None,
                    dry_run: bool = False) -> None:
    """Lance le tracker UI sur les prompts du slug donné."""

    # ── 1) Setup DB & prompts (utilise les helpers de tracker.py) ──
    db_path = BASE_DIR / f"voxa_{slug}.db"
    if not db_path.exists():
        print(f"✗ DB introuvable : {db_path}")
        print(f"  Lance d'abord 'python3 tracker.py' pour initialiser la DB Betclic.")
        sys.exit(1)

    conn = init_db(str(db_path))

    # On utilise CLIENT_NAME = "Betclic" (hardcodé dans tracker.py)
    # Le slug qu'on passe ne sert qu'à pointer la bonne DB
    from tracker import CLIENT_NAME
    client_id = get_or_create_client(conn, CLIENT_NAME)
    brand_ids = sync_brands(conn, client_id)
    all_prompts = sync_prompts(conn, client_id)

    # Filtrage des prompts
    prompts = filter_prompts(all_prompts, language, limit)
    if not prompts:
        print(f"✗ Aucun prompt trouvé pour language={language!r}, limit={limit}")
        conn.close()
        sys.exit(1)

    print_header(slug, language, len(prompts), dry_run)

    # ── 2) Stats agrégées ──
    stats = {
        "total": 0, "success": 0, "failed": 0,
        "mentioned": 0, "scores": [], "total_sources": 0,
        "duration_min": 0.0,
    }
    start_time = time.time()

    # ── 3) Boucle de crawl ──
    with PerplexityCrawler(headless=False) as crawler:
        total = len(prompts)
        for i, prompt in enumerate(prompts, start=1):
            stats["total"] += 1
            lang = prompt["language"]
            txt = prompt["text"]

            # Crawl
            result = crawler.query(txt, language=lang)

            if not result.is_success:
                print(f"\n[{i:02d}/{total}] ⚠ ÉCHEC")
                print(f"   Prompt : {txt[:60]}")
                print(f"   Erreur : {result.error}")
                stats["failed"] += 1
                continue

            # Parse de la réponse pour extraire scores marques
            parsed = parse_response(result.response_text, lang)

            # Liste des marques à insérer (primary + concurrents du marché)
            competitors = COMPETITORS_BY_MARKET.get(lang, ALL_COMPETITORS)
            brands_to_check = [PRIMARY_BRAND] + competitors

            # Compteurs stats
            primary = parsed.get(PRIMARY_BRAND, {})
            if primary.get("mentioned"):
                stats["mentioned"] += 1
            stats["scores"].append(primary.get("geo_score", 0))

            # Affichage
            print_progress(i, total, lang, txt, result, parsed, len(result.sources))

            # ── Persistence DB (sauf en dry-run) ──
            if not dry_run:
                run_id = insert_run_with_ui_metadata(conn, prompt["id"], lang, result)
                insert_results_for_brands(conn, run_id, brand_ids, parsed, brands_to_check)
                n_sources = insert_sources(conn, run_id, result.sources)
                stats["total_sources"] += n_sources

            stats["success"] += 1

            # ── Délais anti-rate-limit ──
            if i < total:
                delay = random.uniform(DELAY_MIN_S, DELAY_MAX_S)
                if i % LONG_PAUSE_EVERY == 0:
                    print(f"\n   ⏸  Pause longue ({LONG_PAUSE_S}s) toutes les {LONG_PAUSE_EVERY} prompts...")
                    time.sleep(LONG_PAUSE_S)
                else:
                    print(f"   💤 Pause {delay:.1f}s")
                    time.sleep(delay)

    conn.close()

    # ── 4) Résumé final ──
    stats["avg_score"] = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
    stats["duration_min"] = (time.time() - start_time) / 60
    print_summary(stats)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voxa Tracker UI — crawl Perplexity via navigateur",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")
    parser.add_argument("--language", choices=["fr", "pt", "fr-ci", "pl"],
                        help="Filtrer sur 1 marché. Sinon tous les marchés.")
    parser.add_argument("--limit", type=int,
                        help="Limiter à N prompts (utile pour tester)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Crawl sans écrire en DB")
    args = parser.parse_args()

    run_ui_tracker(
        slug=args.slug,
        language=args.language,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()