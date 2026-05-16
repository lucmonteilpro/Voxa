"""
Voxa — Tracker UI v2 (Perplexity headed)
=========================================
Tracker en mode UI qui interroge Perplexity via le navigateur (vs API).
Réutilise toute la logique de scoring de tracker.py pour garantir la
cohérence des données avec l'historique.

Nouveautés v2 (vs v1) :
- Mode --all-markets : enchaîne FR → PT → FR-CI → PL automatiquement
- Idempotence : skip les prompts déjà crawlés aujourd'hui (même date calendaire)
- Resume après coupure : relance la commande, ça reprend où ça s'était arrêté
- ETA dynamique : projette la fin du run basé sur la durée moyenne par prompt
- Gestion gracieuse erreurs : ne s'arrête plus sur une query qui plante
- Logs verbeux : timestamp + alertes sur durées anormales
- Stats globales : par marché + cumulées + sources collectées + domaines top

Différences vs tracker.py (API) :
- Pas d'API key requise (login Perplexity manuel persistant via cookies)
- Réponses = celles vues réellement par les utilisateurs (pas API stub)
- Sources web réelles capturées + screenshot pour audit
- Stocke dans les nouvelles colonnes (screenshot_path, crawl_duration_ms, crawl_method='ui')
- Insère les sources dans la table `sources` (jointe à `runs`)

Compatibilité dashboard :
- Réutilise sync_brands, sync_prompts, init_db de tracker.py
- Réutilise parse_response (donc compute_geo_score, detect_sentiment, detect_position)
- Les runs UI apparaissent dans le dashboard à côté des runs API existants
- Distinction via `runs.crawl_method` ('api' pour anciens, 'ui' pour nouveaux)

Usage :
    # Test minimal sur 3 prompts FR
    python3 tracker_ui.py --slug betclic --language fr --limit 3 --dry-run

    # Run complet sur 1 marché (~25 min, ~22 prompts)
    python3 tracker_ui.py --slug betclic --language fr

    # Run complet sur tous les marchés (~2h, ~80 prompts)
    python3 tracker_ui.py --slug betclic --all-markets

    # Force le re-crawl même si déjà fait aujourd'hui
    python3 tracker_ui.py --slug betclic --language fr --force

    # Mode dry-run : crawl sans écrire en DB (debug)
    python3 tracker_ui.py --slug betclic --language fr --limit 3 --dry-run
"""

import argparse
import json
import random
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Réutilisation de la logique métier existante
from tracker import (
    init_db, get_or_create_client, sync_brands, sync_prompts,
    parse_response,
    PRIMARY_BRAND, COMPETITORS_BY_MARKET, ALL_COMPETITORS,
    LANGUAGE_LABELS, MODEL,
)

# Crawlers UI
from crawlers.perplexity import PerplexityCrawler
from crawlers.claude_ai import ClaudeAICrawler
from crawlers.gemini import GeminiCrawler
from crawlers.base import CrawlerResult

# Mapping --llm → classe de crawler
CRAWLER_CLASSES = {
    "perplexity": PerplexityCrawler,
    "claude": ClaudeAICrawler,
    "gemini": GeminiCrawler,
}


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# Délais entre prompts (anti-rate-limit + détection bot)
DELAY_MIN_S = 8
DELAY_MAX_S = 15
LONG_PAUSE_EVERY = 20      # toutes les N prompts → pause longue
LONG_PAUSE_S = 60

# Pause inter-marchés (pour le mode --all-markets)
BETWEEN_MARKETS_PAUSE_S = 90

# Alerte si une query prend plus de N secondes (signal de problème)
ALERT_DURATION_MS = 60_000

# Ordre d'exécution des marchés en mode --all-markets
ALL_MARKETS_ORDER = ["fr", "pt", "fr-ci", "pl"]


# ─────────────────────────────────────────────
# IDEMPOTENCE
# ─────────────────────────────────────────────
def get_prompts_already_crawled_today(conn: sqlite3.Connection,
                                       language: Optional[str] = None,
                                       llm_prefix: Optional[str] = None) -> set:
    """Retourne l'ensemble des prompt_id déjà crawlés en mode UI aujourd'hui.

    "Aujourd'hui" = même date calendaire (pas 24h glissantes).
    On filtre sur crawl_method='ui' + optionnellement sur llm LIKE prefix%.
    """
    today = date.today().isoformat()
    conditions = ["crawl_method = 'ui'", "DATE(created_at) = ?"]
    params: list = [today]

    if language:
        conditions.append("language = ?")
        params.append(language)

    if llm_prefix:
        conditions.append("llm LIKE ?")
        params.append(f"{llm_prefix}%")

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT DISTINCT prompt_id FROM runs WHERE {where}", params
    ).fetchall()
    return {row["prompt_id"] for row in rows}


# ─────────────────────────────────────────────
# DB persistence (étendue par rapport à tracker.py)
# ─────────────────────────────────────────────
def _ensure_metadata_column(conn: sqlite3.Connection) -> None:
    """Ajoute crawl_metadata_json à la table runs si absente."""
    try:
        conn.execute(
            "ALTER TABLE runs ADD COLUMN crawl_metadata_json TEXT"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # colonne existe déjà


def insert_run_with_ui_metadata(conn: sqlite3.Connection,
                                  prompt_id: int,
                                  language: str,
                                  result: CrawlerResult) -> int:
    """Insert un run en DB avec les nouvelles colonnes UI (migration v2).

    Retourne le run_id créé.
    """
    _ensure_metadata_column(conn)

    metadata_json = json.dumps(result.metadata) if result.metadata else None

    c = conn.cursor()
    c.execute("""
        INSERT INTO runs (
            prompt_id, llm, language, raw_response,
            is_demo, created_at,
            screenshot_path, crawl_duration_ms, crawl_method,
            crawl_metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        prompt_id,
        result.model_used or "perplexity-default",
        language,
        result.response_text,
        0,  # not demo
        datetime.now().isoformat(),
        result.screenshot_path,
        result.crawl_duration_ms,
        "ui",
        metadata_json,
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
    """Insert les sources URL citées dans la table `sources`.

    Retourne le nombre de sources insérées.
    """
    if not sources:
        return 0
    c = conn.cursor()
    n = 0
    for src in sources:
        if not src.url:
            continue  # skip text-only sources (url NOT NULL in DB)
        c.execute("""
            INSERT INTO sources
            (run_id, url, title, domain, position, snippet)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_id, src.url, src.title, src.domain, src.position, src.snippet
        ))
        n += 1
    conn.commit()
    return n


# ─────────────────────────────────────────────
# Affichage console
# ─────────────────────────────────────────────
def now_hms() -> str:
    """Timestamp HH:MM:SS pour les logs."""
    return datetime.now().strftime("%H:%M:%S")


def format_duration(seconds: float) -> str:
    """Formatte une durée en string lisible."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def print_header(slug: str, mode: str, n_prompts: int,
                  dry_run: bool, force: bool, n_skipped: int):
    print("\n" + "═" * 70)
    print(f"  VOXA — UI Tracker v2 (Perplexity headed)")
    print(f"  Client     : {slug}")
    print(f"  Mode       : {mode}")
    print(f"  Prompts    : {n_prompts} à crawler"
          + (f" ({n_skipped} skip car déjà fait aujourd'hui)" if n_skipped else ""))
    print(f"  Persistence: {'🔍 DRY-RUN (pas d écriture DB)' if dry_run else '💾 LIVE (DB)'}")
    print(f"  Idempotence: {'❌ FORCE (re-crawl tout)' if force else '✓ Skip si déjà fait aujourd hui'}")
    print(f"  Date       : {date.today()}")
    print(f"  Heure      : {now_hms()}")
    print("═" * 70 + "\n")


def print_progress(idx: int, total: int, lang: str, prompt_text: str,
                    result: CrawlerResult, parsed: dict, n_sources: int,
                    eta_minutes: Optional[float] = None):
    flag = LANGUAGE_LABELS.get(lang, lang)
    primary = parsed.get(PRIMARY_BRAND, {})
    status = "✓" if primary.get("mentioned") else "✗"

    eta_str = f" · ETA: ~{eta_minutes:.0f}min" if eta_minutes else ""

    print(f"\n[{idx:02d}/{total}] [{now_hms()}] [{flag}]{eta_str}")
    print(f"   {prompt_text[:70]}")

    if result.error:
        print(f"   ⚠ ERREUR : {result.error}")
        return

    # Alerte si durée anormalement longue
    duration_warn = ""
    if result.crawl_duration_ms and result.crawl_duration_ms > ALERT_DURATION_MS:
        duration_warn = " ⚠"

    print(f"   ⏱  {result.crawl_duration_ms}ms{duration_warn}  ·  "
          f"📝 {len(result.response_text)} chars  ·  "
          f"🔗 {n_sources} sources")
    print(f"   {status} {PRIMARY_BRAND} — mentions: {primary.get('mention_count', 0)} | "
          f"position: {primary.get('position', '—')} | "
          f"sentiment: {primary.get('sentiment', '—')} | "
          f"score: {primary.get('geo_score', 0)}")


def print_market_summary(language: str, stats: dict):
    """Récap d'1 marché à la fin de son passage."""
    flag = LANGUAGE_LABELS.get(language, language)
    print("\n" + "─" * 70)
    print(f"  Récap marché {flag}")
    print("─" * 70)
    print(f"   Prompts      : {stats['success']}/{stats['total']} succès"
          f" ({stats['skipped']} skip, {stats['failed']} erreurs)")
    if stats['success']:
        print(f"   Mentions     : {stats['mentioned']}/{stats['success']}"
              f" ({stats['mentioned'] * 100 // stats['success']}%)")
        avg = sum(stats['scores']) / len(stats['scores']) if stats['scores'] else 0
        print(f"   Score moyen  : {avg:.1f}/100")
    print(f"   Sources      : {stats['total_sources']} URLs collectées")
    print(f"   Durée        : {format_duration(stats['duration_s'])}")


def print_global_summary(global_stats: dict):
    """Récap final tous marchés confondus."""
    print("\n" + "═" * 70)
    print(f"  RÉCAPITULATIF GLOBAL [{now_hms()}]")
    print("═" * 70)
    print(f"  Marchés traités    : {len(global_stats['markets'])}")
    print(f"  Prompts crawlés    : {global_stats['success']}/{global_stats['total']}")
    print(f"  Skipped (dédup)    : {global_stats['skipped']}")
    print(f"  Erreurs            : {global_stats['failed']}")
    if global_stats['scores']:
        avg = sum(global_stats['scores']) / len(global_stats['scores'])
        print(f"  Score moyen {PRIMARY_BRAND} : {avg:.1f}/100")
    print(f"  Mentions {PRIMARY_BRAND}    : "
          f"{global_stats['mentioned']}/{global_stats['success']} "
          f"({global_stats['mentioned'] * 100 // max(global_stats['success'], 1)}%)")
    print(f"  Sources collectées : {global_stats['total_sources']} URLs")

    # Top 10 domaines cités
    if global_stats['domain_counts']:
        print(f"\n  Top 10 domaines cités par Perplexity :")
        for domain, count in global_stats['domain_counts'].most_common(10):
            print(f"    {count:3d}× {domain}")

    print(f"\n  Durée totale       : {format_duration(global_stats['duration_s'])}")
    print("═" * 70 + "\n")


# ─────────────────────────────────────────────
# Crawl d'un marché unique
# ─────────────────────────────────────────────
def crawl_market(crawler,
                  conn: sqlite3.Connection,
                  prompts: list,
                  language: str,
                  brand_ids: dict,
                  dry_run: bool,
                  force: bool,
                  global_idx_start: int = 0,
                  global_total: int = 0,
                  llm_prefix: Optional[str] = None) -> dict:
    """Crawl tous les prompts d'un marché donné.

    Retourne stats du marché.
    """
    stats = {
        "total": len(prompts),
        "success": 0, "failed": 0, "skipped": 0,
        "mentioned": 0,
        "scores": [],
        "total_sources": 0,
        "domains": Counter(),
        "duration_s": 0.0,
    }
    market_start = time.time()

    # Récupère les prompts déjà crawlés aujourd'hui (sauf si --force)
    already_done = (set() if force
                    else get_prompts_already_crawled_today(conn, language, llm_prefix))
    if already_done and not force:
        print(f"\n[{language}] {len(already_done)} prompts déjà crawlés aujourd'hui, skip\n")

    # Durées par prompt pour calcul ETA
    durations_ms = []

    market_total = len(prompts)
    for i, prompt in enumerate(prompts, start=1):
        # Idempotence : skip si déjà crawlé aujourd'hui
        if prompt["id"] in already_done:
            stats["skipped"] += 1
            continue

        # Calcul ETA basé sur la durée moyenne des prompts précédents
        eta_minutes = None
        if durations_ms:
            avg_ms = sum(durations_ms) / len(durations_ms)
            remaining = market_total - i + 1
            # Inclut le délai entre prompts (~12s en moyenne)
            eta_seconds = remaining * (avg_ms / 1000 + 12)
            # Ajoute pause longue si applicable
            n_long_pauses = (remaining // LONG_PAUSE_EVERY)
            eta_seconds += n_long_pauses * LONG_PAUSE_S
            eta_minutes = eta_seconds / 60

        # Crawl
        try:
            result = crawler.query(prompt["text"], language=language)
        except Exception as e:
            print(f"\n[{i:02d}/{market_total}] [{now_hms()}] ⚠ EXCEPTION inattendue")
            print(f"   Prompt : {prompt['text'][:60]}")
            print(f"   Erreur : {type(e).__name__}: {e}")
            stats["failed"] += 1
            continue

        if not result.is_success:
            stats["failed"] += 1
            print_progress(i, market_total, language, prompt["text"],
                          result, {}, 0, eta_minutes)
            continue

        # Parse de la réponse
        parsed = parse_response(result.response_text, language)

        # Liste des marques à insérer
        competitors = COMPETITORS_BY_MARKET.get(language, ALL_COMPETITORS)
        brands_to_check = [PRIMARY_BRAND] + competitors

        # Stats
        primary = parsed.get(PRIMARY_BRAND, {})
        if primary.get("mentioned"):
            stats["mentioned"] += 1
        stats["scores"].append(primary.get("geo_score", 0))
        for src in result.sources:
            if src.domain:
                stats["domains"][src.domain] += 1

        # Affichage
        print_progress(i, market_total, language, prompt["text"],
                      result, parsed, len(result.sources), eta_minutes)

        # Persistence DB (sauf en dry-run)
        if not dry_run:
            try:
                run_id = insert_run_with_ui_metadata(conn, prompt["id"], language, result)
                insert_results_for_brands(conn, run_id, brand_ids, parsed, brands_to_check)
                n_sources = insert_sources(conn, run_id, result.sources)
                stats["total_sources"] += n_sources
            except Exception as e:
                print(f"   ⚠ Erreur DB : {e}")
                # On continue malgré l'erreur DB (le crawl a marché)
        else:
            stats["total_sources"] += len(result.sources)

        stats["success"] += 1
        if result.crawl_duration_ms:
            durations_ms.append(result.crawl_duration_ms)

        # Délais anti-rate-limit
        if i < market_total:
            delay = random.uniform(DELAY_MIN_S, DELAY_MAX_S)
            if i % LONG_PAUSE_EVERY == 0:
                print(f"\n   ⏸  Pause longue ({LONG_PAUSE_S}s) toutes les "
                      f"{LONG_PAUSE_EVERY} prompts...")
                time.sleep(LONG_PAUSE_S)
            else:
                print(f"   💤 Pause {delay:.1f}s")
                time.sleep(delay)

    stats["duration_s"] = time.time() - market_start
    return stats


# ─────────────────────────────────────────────
# RUNNER PRINCIPAL
# ─────────────────────────────────────────────
def run_ui_tracker(slug: str,
                    language: Optional[str] = None,
                    all_markets: bool = False,
                    limit: Optional[int] = None,
                    dry_run: bool = False,
                    force: bool = False,
                    llm: str = "perplexity") -> None:
    """Lance le tracker UI sur les prompts du slug donné."""

    # ── 1) Setup DB & prompts ──
    db_path = BASE_DIR / f"voxa_{slug}.db"
    if not db_path.exists():
        print(f"✗ DB introuvable : {db_path}")
        sys.exit(1)

    conn = init_db(str(db_path))
    from tracker import CLIENT_NAME
    client_id = get_or_create_client(conn, CLIENT_NAME)
    brand_ids = sync_brands(conn, client_id)
    all_prompts = sync_prompts(conn, client_id)

    # ── 2) Détermine les marchés à traiter ──
    if all_markets:
        markets_to_process = ALL_MARKETS_ORDER
        mode = f"📊 ALL MARKETS ({', '.join(m.upper() for m in ALL_MARKETS_ORDER)})"
    elif language:
        markets_to_process = [language]
        mode = f"🎯 SINGLE MARKET ({language.upper()})"
    else:
        # Default : single market FR
        markets_to_process = ["fr"]
        mode = "🎯 SINGLE MARKET (FR par défaut)"

    # Filtrage par limit (s'applique sur le total à travers tous les marchés)
    market_prompts = {}
    n_total = 0
    n_skipped_idempotence = 0
    for mkt in markets_to_process:
        prompts = [p for p in all_prompts if p["language"] == mkt]
        if limit:
            prompts = prompts[:limit]
        # Compte combien seront skip (sans modifier la liste)
        # llm_prefix sépare l'idempotence par LLM
        llm_prefix_map = {"claude": "claude", "gemini": "gemini"}
        llm_prefix = llm_prefix_map.get(llm, "perplexity")
        if not force:
            already = get_prompts_already_crawled_today(conn, mkt, llm_prefix)
            n_skipped_idempotence += sum(1 for p in prompts if p["id"] in already)
        market_prompts[mkt] = prompts
        n_total += len(prompts)

    if n_total == 0:
        print(f"✗ Aucun prompt trouvé. language={language!r}, all_markets={all_markets}, limit={limit}")
        conn.close()
        sys.exit(1)

    print_header(slug, mode, n_total, dry_run, force, n_skipped_idempotence)

    # ── 3) Stats globales ──
    global_stats = {
        "markets": [],
        "total": 0, "success": 0, "failed": 0, "skipped": 0,
        "mentioned": 0,
        "scores": [],
        "total_sources": 0,
        "domain_counts": Counter(),
        "duration_s": 0.0,
    }
    global_start = time.time()

    # ── 4) Boucle de crawl par marché ──
    crawler_class = CRAWLER_CLASSES.get(llm, PerplexityCrawler)
    llm_prefix_map = {"claude": "claude", "gemini": "gemini"}
    llm_prefix = llm_prefix_map.get(llm, "perplexity")

    with crawler_class(headless=False) as crawler:
        for mkt_idx, mkt in enumerate(markets_to_process):
            prompts = market_prompts[mkt]
            if not prompts:
                continue

            flag = LANGUAGE_LABELS.get(mkt, mkt)
            print(f"\n{'═' * 70}")
            print(f"  MARCHÉ {mkt_idx + 1}/{len(markets_to_process)} : {flag}")
            print(f"{'═' * 70}")

            market_stats = crawl_market(
                crawler=crawler,
                conn=conn,
                prompts=prompts,
                language=mkt,
                brand_ids=brand_ids,
                dry_run=dry_run,
                force=force,
                llm_prefix=llm_prefix,
            )
            print_market_summary(mkt, market_stats)

            # Agrège dans global_stats
            global_stats["markets"].append(mkt)
            global_stats["total"] += market_stats["total"]
            global_stats["success"] += market_stats["success"]
            global_stats["failed"] += market_stats["failed"]
            global_stats["skipped"] += market_stats["skipped"]
            global_stats["mentioned"] += market_stats["mentioned"]
            global_stats["scores"].extend(market_stats["scores"])
            global_stats["total_sources"] += market_stats["total_sources"]
            global_stats["domain_counts"].update(market_stats["domains"])

            # Pause inter-marchés (sauf après le dernier)
            if mkt_idx < len(markets_to_process) - 1:
                next_mkt = markets_to_process[mkt_idx + 1]
                next_flag = LANGUAGE_LABELS.get(next_mkt, next_mkt)
                print(f"\n   ⏸  Pause inter-marchés ({BETWEEN_MARKETS_PAUSE_S}s) "
                      f"avant {next_flag}...")
                time.sleep(BETWEEN_MARKETS_PAUSE_S)

    conn.close()

    # ── 5) Résumé final ──
    global_stats["duration_s"] = time.time() - global_start
    print_global_summary(global_stats)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voxa Tracker UI v2 — crawl Perplexity via navigateur",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")

    # Modes mutuellement exclusifs : --language XOR --all-markets
    market_group = parser.add_mutually_exclusive_group()
    market_group.add_argument("--language", choices=["fr", "pt", "fr-ci", "pl"],
                               help="Crawler 1 marché spécifique")
    market_group.add_argument("--all-markets", action="store_true",
                               help="Crawler tous les marchés "
                                    "(FR → PT → FR-CI → PL)")

    parser.add_argument("--limit", type=int,
                        help="Limiter à N prompts (utile pour tester)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Crawl sans écrire en DB")
    parser.add_argument("--force", action="store_true",
                        help="Force le re-crawl même si déjà fait aujourd hui")
    parser.add_argument("--llm", choices=["perplexity", "claude", "gemini"],
                        default="perplexity",
                        help="LLM à crawler (défaut : perplexity)")
    args = parser.parse_args()

    run_ui_tracker(
        slug=args.slug,
        language=args.language,
        all_markets=args.all_markets,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        llm=args.llm,
    )


if __name__ == "__main__":
    main()