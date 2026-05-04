"""
Voxa — Analyse statistique de la variance historique
=====================================================
Utilise les 80+ mesures historiques (API Claude/GPT/Sonar) pour quantifier
rigoureusement la variance des scores GEO et déterminer le nombre minimal
de mesures nécessaires pour avoir un signal exploitable.

Questions auxquelles ce script répond :

1. Quelle est la distribution réelle des scores Betclic par prompt ?
   (Binaire 0/100, continue, ou bimodale 0+80 ?)

2. La variance est-elle homogène entre prompts ?
   (Tous les prompts oscillent pareil, ou certains sont plus stables ?)

3. La variance est-elle homogène entre LLMs ?
   (Claude Haiku plus stable que GPT-4o-mini ?)

4. Combien de mesures N faut-il pour que la médiane soit stable à ±5 pts ?
   (Test bootstrap : tirage aléatoire de N mesures, mesure de la dispersion
   des médianes obtenues)

5. Recommandation finale pour le protocole de mesure Voxa.

Usage :
    python3 analyze_variance.py --slug betclic
    python3 analyze_variance.py --slug betclic --top 5     # 5 prompts les plus mesurés
"""
import argparse
import logging
import sqlite3
import statistics
import random
from collections import defaultdict
from pathlib import Path

import voxa_db as vdb


log = logging.getLogger("voxa.analyze_variance")


def load_all_measurements(slug: str, brand: str) -> list:
    """Charge toutes les mesures historiques pour un client."""
    cfg = vdb.CLIENTS_CONFIG[slug]
    db_path = cfg["db"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT p.id as prompt_id, p.text, p.category, p.language,
               ru.llm, ru.crawl_method, ru.run_date, ru.created_at,
               r.geo_score, r.mention_count, r.position
        FROM prompts p
        JOIN runs ru ON ru.prompt_id = p.id
        JOIN results r ON r.run_id = ru.id
        JOIN brands b ON r.brand_id = b.id
        WHERE b.name = ?
          AND ru.is_demo = 0
        ORDER BY p.id, ru.created_at
    """, (brand,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def group_by_prompt(measurements: list) -> dict:
    """Groupe les mesures par prompt."""
    by_prompt = defaultdict(list)
    for m in measurements:
        by_prompt[m["prompt_id"]].append(m)
    return dict(by_prompt)


def group_by_llm(measurements: list) -> dict:
    """Groupe les mesures par LLM."""
    by_llm = defaultdict(list)
    for m in measurements:
        llm = m["llm"] or "unknown"
        by_llm[llm].append(m)
    return dict(by_llm)


def compute_stats(scores: list) -> dict:
    """Calcule statistiques descriptives."""
    if not scores:
        return {"n": 0}
    return {
        "n": len(scores),
        "min": min(scores),
        "max": max(scores),
        "mean": round(statistics.mean(scores), 1),
        "median": round(statistics.median(scores), 1),
        "stdev": round(statistics.stdev(scores), 1) if len(scores) >= 2 else 0,
        "p25": round(statistics.quantiles(scores, n=4)[0], 1) if len(scores) >= 4 else 0,
        "p75": round(statistics.quantiles(scores, n=4)[2], 1) if len(scores) >= 4 else 0,
    }


def bootstrap_median_stability(scores: list, n_samples_per_size: int = 1000) -> dict:
    """Pour différentes tailles N, estime la stabilité de la médiane.

    Méthode : pour chaque N entre 1 et 10, on tire 1000 échantillons aléatoires
    de N mesures, on calcule la médiane de chacun, et on mesure la dispersion
    (écart-type) des 1000 médianes obtenues.

    Retourne un dict {N: stdev_des_medianes} qui dit "avec N mesures, la médiane
    fluctue de ± stdev pts".
    """
    if len(scores) < 5:
        return {}  # pas assez de données

    results = {}
    for sample_size in [1, 2, 3, 5, 7, 10]:
        if sample_size > len(scores):
            continue
        medians = []
        for _ in range(n_samples_per_size):
            sample = random.choices(scores, k=sample_size)  # avec remise
            medians.append(statistics.median(sample))
        results[sample_size] = {
            "median_of_medians": round(statistics.median(medians), 1),
            "stdev_of_medians": round(statistics.stdev(medians), 1),
            "p5": round(sorted(medians)[int(0.05 * len(medians))], 1),
            "p95": round(sorted(medians)[int(0.95 * len(medians))], 1),
        }
    return results


def detect_distribution_shape(scores: list) -> str:
    """Détecte si la distribution est binaire, bimodale ou continue."""
    if not scores:
        return "vide"
    n_zeros = sum(1 for s in scores if s == 0)
    n_high = sum(1 for s in scores if s >= 70)
    n_mid = sum(1 for s in scores if 0 < s < 70)
    total = len(scores)

    pct_zero = n_zeros / total * 100
    pct_high = n_high / total * 100
    pct_mid = n_mid / total * 100

    if pct_zero > 80:
        return "MAJORITAIREMENT-ZERO (jamais mentionné)"
    elif pct_high > 80:
        return "MAJORITAIREMENT-HAUT (toujours mentionné)"
    elif pct_zero + pct_high > 80 and pct_mid < 20:
        return "BIMODAL (alterne 0 et 70+)"
    elif pct_mid > 40:
        return "CONTINU (scores intermédiaires fréquents)"
    else:
        return f"MIXTE (zéros={pct_zero:.0f}%, hauts={pct_high:.0f}%, milieux={pct_mid:.0f}%)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--top", type=int, default=10,
                        help="Nombre de prompts à analyser (les plus mesurés)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    cfg = vdb.CLIENTS_CONFIG[args.slug]
    brand = cfg["primary"]

    measurements = load_all_measurements(args.slug, brand)

    if not measurements:
        print(f"✗ Aucune mesure trouvée pour {args.slug}")
        return

    by_prompt = group_by_prompt(measurements)

    print()
    print("=" * 78)
    print(f"  ANALYSE STATISTIQUE — {brand}")
    print("=" * 78)
    print(f"  Total mesures   : {len(measurements)}")
    print(f"  Prompts uniques : {len(by_prompt)}")
    print(f"  LLMs distincts  : {len(set(m['llm'] for m in measurements if m['llm']))}")
    print("=" * 78)

    # ─────────────────────────────────────────────
    # Section 1 : Distribution globale
    # ─────────────────────────────────────────────
    all_scores = [m["geo_score"] for m in measurements if m["geo_score"] is not None]
    global_stats = compute_stats(all_scores)
    global_shape = detect_distribution_shape(all_scores)

    print("\n1. DISTRIBUTION GLOBALE DES SCORES")
    print("-" * 78)
    print(f"   N total      : {global_stats['n']}")
    print(f"   Médiane      : {global_stats['median']}/100")
    print(f"   Moyenne      : {global_stats['mean']}/100")
    print(f"   StDev        : {global_stats['stdev']}")
    print(f"   IQR (P25-P75): {global_stats['p25']} - {global_stats['p75']}")
    print(f"   Range        : {global_stats['min']} - {global_stats['max']}")
    print(f"   Forme        : {global_shape}")

    # ─────────────────────────────────────────────
    # Section 2 : Variance par LLM
    # ─────────────────────────────────────────────
    by_llm = group_by_llm(measurements)
    print("\n2. VARIANCE PAR LLM")
    print("-" * 78)
    print(f"   {'LLM':30s} {'N':>4s} {'Med':>5s} {'Mean':>5s} {'StDev':>6s} {'Forme':>30s}")
    for llm, ms in sorted(by_llm.items(), key=lambda x: -len(x[1])):
        scores = [m["geo_score"] for m in ms if m["geo_score"] is not None]
        s = compute_stats(scores)
        if s["n"] == 0:
            continue
        shape = detect_distribution_shape(scores)
        print(f"   {llm:30s} {s['n']:>4d} {s['median']:>5.0f} {s['mean']:>5.0f} {s['stdev']:>6.1f} {shape[:30]:>30s}")

    # ─────────────────────────────────────────────
    # Section 3 : Variance par prompt (top N les plus mesurés)
    # ─────────────────────────────────────────────
    prompts_with_count = sorted(by_prompt.items(),
                                  key=lambda x: -len(x[1]))[:args.top]

    print(f"\n3. VARIANCE PAR PROMPT (top {args.top} les plus mesurés)")
    print("-" * 78)
    print(f"   {'Cat':10s} {'Lang':4s} {'N':>3s} {'Med':>4s} {'Mean':>5s} {'StDev':>6s} {'Range':>6s}")

    prompt_stats_list = []
    for prompt_id, ms in prompts_with_count:
        scores = [m["geo_score"] for m in ms if m["geo_score"] is not None]
        s = compute_stats(scores)
        if s["n"] < 3:
            continue
        first_m = ms[0]
        cat = first_m["category"] or "?"
        lang = first_m["language"] or "?"

        prompt_stats_list.append({
            "prompt_id": prompt_id,
            "text": first_m["text"][:50],
            "category": cat,
            "language": lang,
            "scores": scores,
            "stats": s,
        })

        print(f"   {cat[:10]:10s} {lang:4s} {s['n']:>3d} {s['median']:>4.0f} "
              f"{s['mean']:>5.0f} {s['stdev']:>6.1f} {s['max']-s['min']:>6.0f}")

    # ─────────────────────────────────────────────
    # Section 4 : Bootstrap — combien de mesures pour stabiliser la médiane ?
    # ─────────────────────────────────────────────
    print("\n4. STABILITÉ DE LA MÉDIANE PAR TAILLE D'ÉCHANTILLON (BOOTSTRAP)")
    print("-" * 78)
    print("   Pour chaque N (1, 2, 3, 5, 7, 10 mesures), simulation de 1000 tirages :")
    print("   on calcule la médiane et on mesure sa dispersion (écart-type).")
    print("   Plus la dispersion est faible, plus la médiane est fiable.")
    print()
    print(f"   {'Prompt':40s} | {'N=1':>5s} {'N=3':>5s} {'N=5':>5s} {'N=7':>5s} {'N=10':>5s}")
    print("   " + "-" * 73)

    avg_stdev_by_n = defaultdict(list)
    for ps in prompt_stats_list:
        if ps["stats"]["n"] < 5:
            continue
        boot = bootstrap_median_stability(ps["scores"])
        if not boot:
            continue
        prompt_label = f"{ps['category'][:10]} {ps['language']} ({ps['stats']['n']})"
        line = f"   {prompt_label:40s} |"
        for size in [1, 3, 5, 7, 10]:
            if size in boot:
                stdev = boot[size]["stdev_of_medians"]
                avg_stdev_by_n[size].append(stdev)
                line += f" {stdev:>5.1f}"
            else:
                line += f"   —"
        print(line)

    print()
    if avg_stdev_by_n:
        print("   StDev moyen sur tous les prompts :")
        for size in sorted(avg_stdev_by_n.keys()):
            avg = statistics.mean(avg_stdev_by_n[size])
            print(f"     N={size:2d} mesures → médiane stable à ±{avg:.1f} pts")

    # ─────────────────────────────────────────────
    # Section 5 : Recommandation finale
    # ─────────────────────────────────────────────
    print()
    print("=" * 78)
    print("  RECOMMANDATION FINALE")
    print("=" * 78)
    print()

    if avg_stdev_by_n:
        # Trouve le N tel que stdev moyen < 10 pts (= IC 95% à ±20)
        # ou stdev < 5 pts (= IC 95% à ±10) idéalement
        target_stdev = 5
        recommendations = {}
        for n in sorted(avg_stdev_by_n.keys()):
            avg = statistics.mean(avg_stdev_by_n[n])
            recommendations[n] = avg

        # Affiche les 3 niveaux de précision
        for n in sorted(recommendations.keys()):
            stdev = recommendations[n]
            ic95 = stdev * 1.96
            print(f"   Avec {n} mesures : médiane à ±{stdev:.1f} pts (IC 95% ±{ic95:.0f} pts)")

        print()
        # Reco principale
        n_for_5 = min((n for n, s in recommendations.items() if s < 5), default=None)
        n_for_10 = min((n for n, s in recommendations.items() if s < 10), default=None)

        if n_for_5:
            print(f"   ✓ Pour précision ±5 pts (haute) : {n_for_5} mesures suffisent")
        if n_for_10:
            print(f"   ✓ Pour précision ±10 pts (acceptable) : {n_for_10} mesures suffisent")

        print()
        print("   IMPLICATION POUR LE QC VOXA :")
        if n_for_10 and n_for_10 <= 3:
            print(f"   → 3 crawls + médiane suffit pour précision ±10 pts")
            print(f"   → Coût Perplexity Pro : 3× au lieu de 1×")
            print(f"   → Durée par item : ~75s au lieu de 25s")
        elif n_for_10:
            print(f"   → {n_for_10} crawls nécessaires pour précision ±10 pts")
            print(f"   → Coût Perplexity Pro : {n_for_10}× au lieu de 1×")
            print(f"   → Durée par item : ~{n_for_10*25}s au lieu de 25s")
        else:
            print(f"   → Avec les données disponibles, impossible de garantir ±10 pts")
            print(f"   → Voxa doit présenter le score avec un IC explicite")

    print()


if __name__ == "__main__":
    main()