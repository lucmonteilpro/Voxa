"""
Voxa — Test prompt augmentation RAG vs Imagine
================================================
Compare 2 formulations du prompt augmenté :
  - Approche actuelle "Imagine que..." (ce qu'utilise QC actuel)
  - Approche RAG-like (sources structurées comme contexte)

Sur les mêmes 3 items du pack, on mesure le score réel pour chaque
formulation, ainsi que le score baseline (sans contenu).

Résultat attendu : tableau qui montre laquelle des 2 formulations
donne le meilleur delta vrai (score augmenté - baseline).

Usage :
    python3 test_qc_rag.py --slug betclic --pack-id 2 --limit 3
"""
import argparse
import logging
import sys
import time
from datetime import date

import voxa_db as vdb
from tracker import parse_response
from crawlers.perplexity import PerplexityCrawler


log = logging.getLogger("voxa.test_rag")


# Approche actuelle : "Imagine que..."
TEMPLATE_IMAGINE = """Imagine que le site officiel de {brand} \
publie aujourd'hui le contenu de référence suivant sur son site web :

---
{content}
---

Maintenant, en tenant compte de cette nouvelle source officielle, réponds \
de manière complète à la question suivante : {prompt}"""


# Approche RAG-like : sources structurées comme contexte
TEMPLATE_RAG = """SOURCE 1
URL: https://www.{brand_url}/
Date de publication: {today}
Titre: {brand} - Information officielle

{content}

---

En te basant sur la source ci-dessus et tes connaissances générales, \
réponds à la question suivante de manière factuelle et complète : {prompt}"""


# Map slug → URL pour les sources RAG
BRAND_URLS = {
    "betclic": "betclic.fr",
    "psg": "psg.fr",
    "winamax": "winamax.fr",
}


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


def crawl_and_score(crawler, prompt_text: str, language: str, brand: str) -> dict:
    """Lance un crawl et calcule le score Betclic."""
    try:
        cr = crawler.query(prompt_text, language=language)
    except Exception as e:
        return {"error": str(e), "score": None}

    if not cr.is_success:
        return {"error": cr.error or "crawl failed", "score": None}

    parsed = parse_response(cr.response_text, language)
    primary_data = parsed.get(brand, {})
    return {
        "score": round(primary_data.get("geo_score", 0), 1),
        "mentions": primary_data.get("mention_count", 0),
        "position": primary_data.get("position"),
        "sentiment": primary_data.get("sentiment"),
        "response_preview": cr.response_text[:250],
        "n_sources": len(cr.sources),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--pack-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    cfg = vdb.CLIENTS_CONFIG[args.slug]
    brand = cfg["primary"]
    brand_url = BRAND_URLS.get(args.slug, f"{args.slug}.fr")

    items = load_pack_items(args.slug, args.pack_id, limit=args.limit)
    if not items:
        print(f"✗ Aucun item trouvé pour pack #{args.pack_id}", file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()

    print()
    print("=" * 78)
    print(f"  TEST PROMPT AUGMENTATION : Imagine vs RAG vs Baseline")
    print("=" * 78)
    print(f"  Brand   : {brand}")
    print(f"  Source URL (RAG) : {brand_url}")
    print(f"  Items   : {len(items)}")
    print(f"  Crawls totaux : {len(items) * 2} (RAG + Baseline) - on réutilise QC déjà fait")
    print("=" * 78)

    results = []

    with PerplexityCrawler(headless=False) as crawler:
        for i, item in enumerate(items, 1):
            prompt = item["prompt_text"]
            language = item.get("language", "fr")
            content = item.get("content") or ""

            print(f"\n[{i}/{len(items)}] {item.get('category')} ({language}) — "
                  f"{prompt[:60]}...")

            # 1) Test approche RAG
            print(f"  Crawl RAG (source structurée)...")
            rag_prompt = TEMPLATE_RAG.format(
                brand=brand,
                brand_url=brand_url,
                today=today,
                content=content,
                prompt=prompt,
            )
            rag = crawl_and_score(crawler, rag_prompt, language, brand)
            print(f"    → score RAG : {rag.get('score', '—')}/100  "
                  f"({rag.get('mentions', 0)} mentions, "
                  f"position={rag.get('position', '—')})")

            time.sleep(8)

            # 2) Test baseline (déjà fait dans test_baseline.py mais on refait
            #    pour avoir des chiffres comparables sur la même journée)
            print(f"  Crawl baseline (prompt nu)...")
            base = crawl_and_score(crawler, prompt, language, brand)
            print(f"    → score baseline : {base.get('score', '—')}/100  "
                  f"({base.get('mentions', 0)} mentions)")

            results.append({
                "category": item.get("category"),
                "language": language,
                "prompt": prompt,
                "score_qc_imagine": item.get("score_real"),  # depuis DB
                "score_rag": rag.get("score"),
                "score_baseline": base.get("score"),
                "rag_response_preview": rag.get("response_preview"),
                "rag_mentions": rag.get("mentions"),
                "rag_position": rag.get("position"),
            })

            if i < len(items):
                time.sleep(8)

    # Tableau comparatif final
    print()
    print("=" * 78)
    print("  COMPARATIF FINAL")
    print("=" * 78)
    print()
    print(f"  {'Cat.':10s} {'Lang':5s} | "
          f"{'Imagine':>8s} {'RAG':>6s} {'Baseline':>9s} | "
          f"{'Δ Imagine':>10s} {'Δ RAG':>7s}")
    print("  " + "-" * 76)

    for r in results:
        sc_imagine = r["score_qc_imagine"]
        sc_rag = r["score_rag"]
        sc_base = r["score_baseline"]

        delta_imagine = (
            (sc_imagine - sc_base) if (sc_imagine is not None and sc_base is not None)
            else None
        )
        delta_rag = (
            (sc_rag - sc_base) if (sc_rag is not None and sc_base is not None)
            else None
        )

        sc_imagine_s = f"{sc_imagine:.0f}" if sc_imagine is not None else "—"
        sc_rag_s = f"{sc_rag:.0f}" if sc_rag is not None else "—"
        sc_base_s = f"{sc_base:.0f}" if sc_base is not None else "—"
        delta_imagine_s = (
            f"+{delta_imagine:.0f}" if delta_imagine and delta_imagine > 0
            else f"{delta_imagine:.0f}" if delta_imagine is not None
            else "—"
        )
        delta_rag_s = (
            f"+{delta_rag:.0f}" if delta_rag and delta_rag > 0
            else f"{delta_rag:.0f}" if delta_rag is not None
            else "—"
        )

        print(f"  {r['category']:10s} {r['language']:5s} | "
              f"{sc_imagine_s:>8s} {sc_rag_s:>6s} {sc_base_s:>9s} | "
              f"{delta_imagine_s:>10s} {delta_rag_s:>7s}")

    # Stats
    print()
    print("Légende :")
    print("  Imagine   : score QC actuel (formulation 'Imagine que...')")
    print("  RAG       : score avec format RAG (source structurée)")
    print("  Baseline  : score sans contenu augmenté")
    print("  Δ Imagine : Imagine - Baseline = apport net approche actuelle")
    print("  Δ RAG     : RAG - Baseline = apport net approche RAG")
    print()

    # Moyennes
    deltas_imagine = [r["score_qc_imagine"] - r["score_baseline"]
                      for r in results
                      if r["score_qc_imagine"] is not None and r["score_baseline"] is not None]
    deltas_rag = [r["score_rag"] - r["score_baseline"]
                  for r in results
                  if r["score_rag"] is not None and r["score_baseline"] is not None]

    avg_imagine = sum(deltas_imagine) / len(deltas_imagine) if deltas_imagine else 0
    avg_rag = sum(deltas_rag) / len(deltas_rag) if deltas_rag else 0

    print(f"  Delta moyen approche Imagine : +{avg_imagine:.0f} pts")
    print(f"  Delta moyen approche RAG     : +{avg_rag:.0f} pts")
    print()

    # Détail des réponses RAG (qualité, pas juste score)
    print("=" * 78)
    print("  DÉTAIL DES RÉPONSES PERPLEXITY (approche RAG)")
    print("=" * 78)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['category']} ({r['language']}) — score RAG {r['score_rag']}/100 "
              f"({r['rag_mentions']} mentions, position={r['rag_position']})")
        print(f"   Prompt : {r['prompt'][:80]}")
        print(f"   Réponse Perplexity : {r['rag_response_preview']}...")
    print()

    # Verdict
    print("=" * 78)
    print("  VERDICT")
    print("=" * 78)
    if avg_rag > avg_imagine + 10:
        print("  → ✓ L'approche RAG est SIGNIFICATIVEMENT meilleure")
        print("    Recommandation : remplacer le template du QC par l'approche RAG")
    elif avg_rag > avg_imagine:
        print("  → ◎ L'approche RAG est légèrement meilleure")
        print("    Recommandation : tester sur plus d'items avant de trancher")
    elif avg_rag < avg_imagine - 10:
        print("  → ✗ L'approche Imagine reste meilleure")
        print("    Recommandation : explorer d'autres formulations")
    else:
        print("  → = Les 2 approches sont équivalentes")
        print("    Recommandation : autre angle d'analyse à creuser")
    print()


if __name__ == "__main__":
    main()