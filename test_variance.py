"""
Voxa — Test variance Perplexity v2 (sur spectre complet de scores)
====================================================================
Quantifie l'instabilité Perplexity sur 3 profils de prompts différents :
- Prompts FORTS (Betclic mentionné régulièrement, score historique > 80)
- Prompts MOYENS (Betclic parfois mentionné, score 30-70)
- Prompts FAIBLES (Betclic jamais mentionné, score 0)

Hypothèse : la variance dépend du profil. Aux extrêmes (0 ou 100), c'est
stable. Aux scores intermédiaires, c'est instable.

Si l'hypothèse se confirme, ça change le design du QC :
- Multi-crawl OBLIGATOIRE pour les scores intermédiaires
- Multi-crawl FACULTATIF pour les extrêmes

Usage :
    python3 test_variance.py --slug betclic --n-runs 3
"""
import argparse
import logging
import statistics
import sys
import time

import voxa_db as vdb
from tracker import parse_response
from crawlers.perplexity import PerplexityCrawler


log = logging.getLogger("voxa.test_variance")
DELAY_BETWEEN_CRAWLS_S = 8


def select_prompts_by_profile(slug: str, brand: str) -> list:
    """Sélectionne 3 prompts représentatifs : fort / moyen / faible.

    Stratégie :
      - FORT : prompt avec score moyen Betclic > 80 (basé sur runs UI existants)
      - MOYEN : score moyen 30-70
      - FAIBLE : score moyen 0-20

    Si pas de prompt dans une catégorie, on prend le plus proche.
    """
    cfg = vdb.CLIENTS_CONFIG[slug]
    db_path = cfg["db"]

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT p.id, p.text, p.category, p.language,
               AVG(r.geo_score) as avg_score,
               COUNT(DISTINCT ru.id) as n_runs
        FROM prompts p
        JOIN runs ru ON ru.prompt_id = p.id
        JOIN results r ON r.run_id = ru.id
        JOIN brands b ON r.brand_id = b.id
        WHERE b.name = ?
          AND ru.crawl_method = 'ui'
          AND ru.is_demo = 0
        GROUP BY p.id
        HAVING n_runs > 0
        ORDER BY avg_score DESC
    """, (brand,)).fetchall()

    if not rows:
        conn.close()
        return []

    # Cherche 1 prompt par profil
    fort = next((r for r in rows if r["avg_score"] >= 80), None)
    moyen = next((r for r in rows if 30 <= r["avg_score"] <= 70), None)
    faible = next((r for r in rows if r["avg_score"] <= 20), None)

    # Fallback si pas de match exact
    if not fort:
        fort = rows[0]  # le plus haut
    if not faible:
        faible = rows[-1]  # le plus bas
    if not moyen:
        # On prend celui le plus proche de 50
        moyen = min(rows, key=lambda r: abs(r["avg_score"] - 50))

    # Élimine les doublons
    selected = []
    seen_ids = set()
    for label, p in [("FORT", fort), ("MOYEN", moyen), ("FAIBLE", faible)]:
        if p["id"] not in seen_ids:
            selected.append({
                "profile": label,
                "id": p["id"],
                "text": p["text"],
                "category": p["category"],
                "language": p["language"],
                "historical_avg_score": round(p["avg_score"], 1),
                "n_runs_historical": p["n_runs"],
            })
            seen_ids.add(p["id"])

    conn.close()
    return selected


def crawl_score(crawler, prompt: str, language: str, brand: str) -> dict:
    try:
        cr = crawler.query(prompt, language=language)
    except Exception as e:
        return {"error": str(e), "score": None}
    if not cr.is_success:
        return {"error": cr.error or "fail", "score": None}

    parsed = parse_response(cr.response_text, language)
    pd = parsed.get(brand, {})
    return {
        "score": round(pd.get("geo_score", 0), 1),
        "mentions": pd.get("mention_count", 0),
        "position": pd.get("position"),
        "sentiment": pd.get("sentiment"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--n-runs", type=int, default=3)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    cfg = vdb.CLIENTS_CONFIG[args.slug]
    brand = cfg["primary"]

    selected = select_prompts_by_profile(args.slug, brand)
    if not selected:
        print(f"✗ Aucun prompt trouvé pour {args.slug}", file=sys.stderr)
        sys.exit(1)

    n_total = len(selected) * args.n_runs
    duration_estimate = n_total * 30

    print()
    print("=" * 78)
    print(f"  TEST VARIANCE PERPLEXITY v2 — Spectre complet de scores")
    print("=" * 78)
    print(f"  Brand          : {brand}")
    print(f"  Profils        : FORT / MOYEN / FAIBLE")
    print(f"  Runs / prompt  : {args.n_runs}")
    print(f"  Crawls totaux  : {n_total}")
    print(f"  Durée estimée  : ~{duration_estimate}s = {duration_estimate // 60}min")
    print("=" * 78)

    print("\nPROMPTS SÉLECTIONNÉS :")
    for s in selected:
        print(f"  [{s['profile']:6s}] score historique {s['historical_avg_score']:.0f}/100 "
              f"({s['n_runs_historical']} runs)")
        print(f"           {s['text'][:80]}")
    print()

    all_results = []

    with PerplexityCrawler(headless=False) as crawler:
        for i, item in enumerate(selected, 1):
            prompt = item["text"]
            language = item["language"]
            profile = item["profile"]
            histo = item["historical_avg_score"]

            print(f"\n[{i}/{len(selected)}] [{profile}] (historique {histo:.0f}/100) "
                  f"{prompt[:50]}...")

            scores = []
            mentions_list = []
            for run_idx in range(1, args.n_runs + 1):
                print(f"  Run {run_idx}/{args.n_runs}...", end=" ", flush=True)
                r = crawl_score(crawler, prompt, language, brand)
                if r.get("error"):
                    print(f"ERREUR : {r['error']}")
                    continue
                scores.append(r["score"])
                mentions_list.append(r["mentions"])
                print(f"score={r['score']:.0f}  mentions={r['mentions']}  "
                      f"position={r.get('position', '—')}")

                is_last = (i == len(selected)) and (run_idx == args.n_runs)
                if not is_last:
                    time.sleep(DELAY_BETWEEN_CRAWLS_S)

            all_results.append({
                "profile": profile,
                "historical_avg": histo,
                "category": item["category"],
                "language": language,
                "scores": scores,
                "mentions_list": mentions_list,
            })

    # ─────────────────────────────────────────────
    # Tableau d'analyse
    # ─────────────────────────────────────────────
    print()
    print("=" * 78)
    print("  ANALYSE DE VARIANCE PAR PROFIL")
    print("=" * 78)
    print()
    print(f"  {'Profil':7s} {'Histo':>5s} {'Lang':5s} | "
          f"{'Run1':>5s} {'Run2':>5s} {'Run3':>5s} | "
          f"{'Min':>4s} {'Max':>4s} {'Med':>4s} {'StDev':>5s} | {'Range':>6s}")
    print("  " + "-" * 76)

    for r in all_results:
        scores = r["scores"]
        if not scores:
            continue

        score_strs = [f"{s:>5.0f}" for s in scores] + ["    —"] * (3 - len(scores))
        score_strs = score_strs[:3]
        s_min = min(scores)
        s_max = max(scores)
        s_med = statistics.median(scores)
        s_std = statistics.stdev(scores) if len(scores) >= 2 else 0
        s_range = s_max - s_min

        print(f"  {r['profile']:7s} "
              f"{r['historical_avg']:>5.0f} "
              f"{r['language']:5s} | "
              f"{score_strs[0]} {score_strs[1]} {score_strs[2]} | "
              f"{s_min:>4.0f} {s_max:>4.0f} {s_med:>4.0f} {s_std:>5.1f} | "
              f"{s_range:>6.0f}")

    # ─────────────────────────────────────────────
    # Verdict par profil
    # ─────────────────────────────────────────────
    print()
    print("=" * 78)
    print("  VERDICT PAR PROFIL")
    print("=" * 78)
    print()

    for r in all_results:
        scores = r["scores"]
        if not scores:
            continue
        s_range = max(scores) - min(scores)
        profile = r["profile"]

        if s_range == 0:
            stability = "✓ STABLE PARFAIT (range 0)"
            recommendation = "1 crawl suffit"
        elif s_range < 10:
            stability = f"✓ TRÈS STABLE (range {s_range:.0f} pts)"
            recommendation = "1 crawl suffit"
        elif s_range < 30:
            stability = f"◎ INSTABLE MODÉRÉ (range {s_range:.0f} pts)"
            recommendation = "2-3 crawls + médiane"
        else:
            stability = f"✗ TRÈS INSTABLE (range {s_range:.0f} pts)"
            recommendation = "3-5 crawls + médiane obligatoire"

        print(f"  [{profile}]  {stability}")
        print(f"             → {recommendation}")
        print()

    # ─────────────────────────────────────────────
    # Implication pour Voxa
    # ─────────────────────────────────────────────
    print("=" * 78)
    print("  IMPLICATION POUR LE DESIGN DU QC")
    print("=" * 78)

    fort = next((r for r in all_results if r["profile"] == "FORT"), None)
    moyen = next((r for r in all_results if r["profile"] == "MOYEN"), None)
    faible = next((r for r in all_results if r["profile"] == "FAIBLE"), None)

    fort_range = (max(fort["scores"]) - min(fort["scores"])) if fort and fort["scores"] else None
    moyen_range = (max(moyen["scores"]) - min(moyen["scores"])) if moyen and moyen["scores"] else None
    faible_range = (max(faible["scores"]) - min(faible["scores"])) if faible and faible["scores"] else None

    print()
    if fort_range is not None and faible_range is not None:
        if fort_range < 10 and faible_range < 10 and (moyen_range is None or moyen_range > 30):
            print("  ✓ HYPOTHÈSE CONFIRMÉE : variance dépend de la zone du score")
            print("    - Aux extrêmes (0 ou 100) : stable")
            print("    - En zone intermédiaire : instable")
            print()
            print("  → DESIGN QC :")
            print("     - Si score visé < 20 ou > 80 : 1 crawl suffit")
            print("     - Si score visé 20-80 : 3 crawls + médiane obligatoire")
            print("     - Comme on cible souvent 60+ (target_score), multi-crawl par défaut")
        elif fort_range < 10 and faible_range < 10:
            print("  ≈ HYPOTHÈSE PARTIELLEMENT CONFIRMÉE")
            print("    - Extrêmes stables")
            print("    - Mais le profil moyen n'est pas non plus très instable")
        else:
            print("  ✗ HYPOTHÈSE INVALIDÉE : la variance n'est pas liée au score absolu")
            print("    Tous les profils ont une variance non négligeable")
            print("    → Multi-crawl obligatoire dans tous les cas")

    print()


if __name__ == "__main__":
    main()