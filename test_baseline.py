"""
Voxa — Test de baseline (validité QC)
======================================
Mesure le score Perplexity réel sur les prompts du dernier pack
SANS aucune augmentation de contenu.

Objectif : comparer le score "à nu" (baseline) vs le score "augmenté"
mesuré par le Quality Controller, pour vérifier que le QC mesure vraiment
l'apport du contenu et pas un artefact lié au prompt méta.

Usage :
    python3 test_baseline.py --slug betclic --pack-id 2 --limit 3
"""
import argparse
import logging
import sys
import time

import voxa_db as vdb
from tracker import parse_response
from crawlers.perplexity import PerplexityCrawler


log = logging.getLogger("voxa.baseline_test")


def load_pack_items(slug: str, pack_id: int, limit: int = None) -> list:
    """Charge les items d'un pack."""
    c = vdb.conn_accounts()
    try:
        rows = c.execute(
            "SELECT * FROM action_items WHERE pack_id = ? ORDER BY id ASC",
            (pack_id,),
        ).fetchall()
        items = [dict(r) for r in rows]
        if limit:
            items = items[:limit]
        return items
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--pack-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    cfg = vdb.CLIENTS_CONFIG[args.slug]
    brand = cfg["primary"]

    items = load_pack_items(args.slug, args.pack_id, limit=args.limit)
    if not items:
        print(f"✗ Aucun item trouvé pour pack #{args.pack_id}", file=sys.stderr)
        sys.exit(1)

    print()
    print("=" * 70)
    print(f"  TEST DE BASELINE — Pack #{args.pack_id} ({len(items)} items)")
    print("=" * 70)
    print(f"  Brand : {brand}")
    print(f"  Méthode : prompt original SANS contenu augmenté")
    print("=" * 70)

    results = []
    with PerplexityCrawler(headless=False) as crawler:
        for i, item in enumerate(items, 1):
            prompt = item["prompt_text"]
            language = item.get("language", "fr")

            print(f"\n[{i}/{len(items)}] Crawl baseline : {prompt[:60]}...")

            try:
                cr = crawler.query(prompt, language=language)
            except Exception as e:
                print(f"  ✗ Crawl failed : {e}")
                continue

            if not cr.is_success:
                print(f"  ✗ Crawl failed : {cr.error}")
                continue

            parsed = parse_response(cr.response_text, language)
            primary_data = parsed.get(brand, {})
            score_baseline = round(primary_data.get("geo_score", 0), 1)
            mention_count = primary_data.get("mention_count", 0)
            position = primary_data.get("position")
            sentiment = primary_data.get("sentiment")

            results.append({
                "category": item.get("category"),
                "language": language,
                "prompt": prompt,
                "score_current_db": item.get("score_current") or 0,
                "score_predicted": item.get("score_predicted") or 0,
                "score_real_qc": item.get("score_real"),
                "score_baseline": score_baseline,
                "mention_count": mention_count,
                "position": position,
                "sentiment": sentiment,
                "response_preview": cr.response_text[:200],
                "n_sources": len(cr.sources),
            })

            print(f"  → score baseline : {score_baseline}/100")
            print(f"    {mention_count} mentions, position={position}, sentiment={sentiment}")

            if i < len(items):
                print(f"  Pause 8s...")
                time.sleep(8)

    # Tableau comparatif
    print()
    print("=" * 70)
    print("  COMPARATIF BASELINE vs QC")
    print("=" * 70)
    print()
    print(f"  {'Catégorie':12s} {'Lang':5s} | "
          f"{'Initial':>7s} {'Prédit':>7s} {'QC réel':>8s} {'Baseline':>9s} | {'Delta vrai':>11s}")
    print("  " + "-" * 78)

    for r in results:
        sc_qc = r["score_real_qc"] if r["score_real_qc"] is not None else None
        sc_base = r["score_baseline"]
        delta_vrai = (sc_qc - sc_base) if sc_qc is not None else None

        sc_qc_str = f"{sc_qc:.0f}" if sc_qc is not None else "—"
        delta_str = (
            f"+{delta_vrai:.0f}" if (delta_vrai is not None and delta_vrai > 0)
            else f"{delta_vrai:.0f}" if delta_vrai is not None
            else "—"
        )

        print(f"  {r['category']:12s} {r['language']:5s} | "
              f"{r['score_current_db']:>7.0f} "
              f"{r['score_predicted']:>7.0f} "
              f"{sc_qc_str:>8s} "
              f"{sc_base:>9.0f} | "
              f"{delta_str:>11s}")

    print()
    print("Légende :")
    print("  - Initial    : score mesuré au tracker UI initial (peut être ancien)")
    print("  - Prédit     : score prédit par le Content Creator (simulation)")
    print("  - QC réel    : score mesuré par le Quality Controller (avec contenu augmenté)")
    print("  - Baseline   : score Perplexity AUJOURD'HUI sur prompt nu (sans contenu)")
    print("  - Delta vrai : QC réel - Baseline = apport NET du contenu")
    print()

    # Conclusions
    delta_vrais = [
        (r["score_real_qc"] - r["score_baseline"])
        for r in results
        if r["score_real_qc"] is not None
    ]
    if delta_vrais:
        avg_delta = sum(delta_vrais) / len(delta_vrais)
        print(f"  Delta vrai moyen : {avg_delta:+.0f} pts")
        if avg_delta > 30:
            print("  → ✓ Le contenu augmenté apporte un gain SIGNIFICATIF")
        elif avg_delta > 10:
            print("  → ◎ Le contenu augmenté apporte un gain MODÉRÉ")
        elif avg_delta > 0:
            print("  → ⚠ Le contenu augmenté apporte un gain FAIBLE")
        else:
            print("  → ✗ Le contenu augmenté n'apporte RIEN ou DÉGRADE")
            print("    → Refacto du prompt augmenté nécessaire")
    print()


if __name__ == "__main__":
    main()