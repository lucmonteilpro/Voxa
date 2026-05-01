"""
Voxa — Agent Gap Analyzer
==========================
Identifie les angles morts de la marque primaire dans les réponses Perplexity.
Pour chaque angle mort, propose une reco actionnable basée sur :
- Les concurrents cités sur ce prompt
- Les sources web stratégiques utilisées par Perplexity

Architecture extensible :
- v1 (actuel) : recos générées par templates Python pur (gratuit, déterministe)
- v2 (futur) : possibilité d'enrichir via Claude API quand client paie

Pour basculer en v2 : modifier `_build_recommendation()` pour appeler une nouvelle
fonction `_build_recommendation_llm()` qui passe les données à Claude.

Usage CLI :
    # Run sur Betclic FR avec seuil par défaut (60)
    python3 -m agents.gap_analyzer --slug betclic --language fr

    # Run avec seuil différent (toutes présences faibles ≤ 80)
    python3 -m agents.gap_analyzer --slug betclic --language fr --threshold 80

    # Run sans persister en DB (debug)
    python3 -m agents.gap_analyzer --slug betclic --language fr --dry-run

    # Run multi-marchés
    python3 -m agents.gap_analyzer --slug betclic
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from .base import Agent


# ─────────────────────────────────────────────
# Constantes (tunables)
# ─────────────────────────────────────────────
DEFAULT_THRESHOLD = 60.0      # score ≤ ce seuil = angle mort
MIN_TOP_SOURCES = 3           # min de sources stratégiques affichées par angle mort
MAX_TOP_SOURCES = 5
MAX_TOP_COMPETITORS = 5

# Labels lisibles pour les catégories Betclic
CATEGORY_LABELS = {
    "visibility": "Visibilité (meilleur site)",
    "brand": "Image de marque",
    "odds": "Cotes & paris",
    "regulation": "Régulation & légalité",
    "payment": "Paiement & retraits",
    # Catégories sport (au cas où le slug ≠ betclic)
    "discovery": "Découverte",
    "comparison": "Comparaison",
    "reputation": "Réputation",
    "transactional": "Transactionnel",
}


class GapAnalyzer(Agent):
    """Analyse les angles morts d'un client donné dans les réponses Perplexity.

    Output structuré :
    {
        "summary": {
            "primary_brand": "Betclic",
            "language": "fr",
            "threshold": 60,
            "n_blind_spots": 2,
            "n_prompts_total": 22,
            "avg_score_global": 83.5,
        },
        "blind_spots": [
            {
                "prompt": "...",
                "category": "regulation",
                "category_label": "Régulation & légalité",
                "score": 0.0,
                "n_runs": 1,
                "competitors_cited": [
                    {"name": "Winamax", "mentions": 5},
                    {"name": "FDJ", "mentions": 4},
                ],
                "top_sources": [
                    {"domain": "anj.fr", "n_citations": 3},
                    {"domain": "lebonparisportif.com", "n_citations": 2},
                ],
                "recommendation": "...",
            }
        ],
        "category_summary": {
            "regulation": {"n_blind_spots": 1, "avg_score": 0.0},
            "payment": {"n_blind_spots": 1, "avg_score": 0.0},
        },
        "global_top_sources": [...],
        "global_top_competitors": [...],
    }
    """

    name = "gap_analyzer"

    def __init__(self, slug: str, language: Optional[str] = None,
                 threshold: float = DEFAULT_THRESHOLD, **kwargs):
        super().__init__(slug=slug, language=language, **kwargs)
        self.threshold = threshold

    def validate_input(self, input_data: dict) -> None:
        """Vérifie que la DB a les tables nécessaires."""
        conn = self.db_connect()
        try:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            required = {"prompts", "results", "runs", "brands", "sources"}
            missing = required - tables
            if missing:
                raise RuntimeError(
                    f"Tables manquantes dans {self.db_path}: {missing}. "
                    f"Lance migrate_v2.py si pas encore fait."
                )
        finally:
            conn.close()

    def execute(self, input_data: dict) -> dict:
        """Lance l'analyse et retourne le rapport structuré."""
        primary_brand = self._get_primary_brand()

        # 1) Récupère TOUS les prompts avec leur score moyen
        all_prompts = self._load_all_prompts_with_scores(primary_brand)

        # 2) Filtre les angles morts (score ≤ threshold)
        blind_spots_raw = [p for p in all_prompts if p["avg_score"] <= self.threshold]

        # 3) Pour chaque angle mort, enrichit avec concurrents + sources
        blind_spots = []
        for prompt in blind_spots_raw:
            enriched = self._enrich_blind_spot(prompt, primary_brand)
            blind_spots.append(enriched)

        # 4) Trie par priorité : score croissant (plus bas = plus prioritaire)
        blind_spots.sort(key=lambda x: (x["score"], -x["n_runs"]))

        # 5) Statistiques globales
        category_summary = self._build_category_summary(blind_spots)
        global_top_sources = self._global_top_sources()
        global_top_competitors = self._global_top_competitors(primary_brand)

        avg_score_global = (
            sum(p["avg_score"] for p in all_prompts) / len(all_prompts)
            if all_prompts else 0
        )

        return {
            "summary": {
                "primary_brand": primary_brand,
                "slug": self.slug,
                "language": self.language,
                "threshold": self.threshold,
                "n_blind_spots": len(blind_spots),
                "n_prompts_total": len(all_prompts),
                "avg_score_global": round(avg_score_global, 1),
            },
            "blind_spots": blind_spots,
            "category_summary": category_summary,
            "global_top_sources": global_top_sources,
            "global_top_competitors": global_top_competitors,
        }

    # ─────────────────────────────────────────────
    # DB queries
    # ─────────────────────────────────────────────
    def _get_primary_brand(self) -> str:
        """Trouve le nom de la marque primaire (is_primary=1) pour ce slug.

        On utilise la 1ère marque primaire trouvée. Si plusieurs clients dans
        la DB, on prend celle dont le client_name correspond au slug.
        """
        conn = self.db_connect()
        try:
            row = conn.execute("""
                SELECT b.name FROM brands b
                JOIN clients c ON b.client_id = c.id
                WHERE b.is_primary = 1
                ORDER BY b.id ASC LIMIT 1
            """).fetchone()
            if not row:
                raise RuntimeError(f"Aucune marque primaire trouvée dans {self.db_path}")
            return row["name"]
        finally:
            conn.close()

    def _language_clause(self, table_alias: str = "ru") -> tuple:
        """Retourne (sql_fragment, params) pour filtrer par language.

        On filtre sur ru.language (table runs) parce que c'est la langue de la run,
        pas du prompt (un même prompt peut être crawlé en plusieurs langues).
        """
        if self.language:
            return f"AND {table_alias}.language = ?", [self.language]
        return "", []

    def _load_all_prompts_with_scores(self, brand: str) -> list:
        """Charge tous les prompts crawlés en mode UI avec leur score moyen pour la marque primaire."""
        conn = self.db_connect()
        try:
            lang_clause, lang_params = self._language_clause("ru")
            params = [brand] + lang_params

            rows = conn.execute(f"""
                SELECT p.id as prompt_id, p.text, p.category, p.language,
                       AVG(r.geo_score) as avg_score,
                       COUNT(DISTINCT ru.id) as n_runs
                FROM prompts p
                JOIN runs ru ON ru.prompt_id = p.id
                JOIN results r ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                WHERE b.name = ?
                  AND ru.crawl_method = 'ui'
                  AND ru.is_demo = 0
                  {lang_clause}
                GROUP BY p.id
                ORDER BY avg_score ASC
            """, params).fetchall()

            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _enrich_blind_spot(self, prompt: dict, primary_brand: str) -> dict:
        """Pour 1 prompt faible, récupère concurrents cités + sources stratégiques."""
        conn = self.db_connect()
        try:
            lang_clause, lang_params = self._language_clause("ru")

            # Concurrents cités sur les runs de ce prompt
            comp_rows = conn.execute(f"""
                SELECT b.name, SUM(r.mention_count) as mentions
                FROM results r
                JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                WHERE ru.prompt_id = ?
                  AND r.mentioned = 1
                  AND b.name != ?
                  AND ru.crawl_method = 'ui'
                  AND ru.is_demo = 0
                  {lang_clause}
                GROUP BY b.name
                ORDER BY mentions DESC
                LIMIT ?
            """, [prompt["prompt_id"], primary_brand] + lang_params + [MAX_TOP_COMPETITORS]).fetchall()

            competitors_cited = [
                {"name": r["name"], "mentions": int(r["mentions"])}
                for r in comp_rows
            ]

            # Sources Perplexity utilisées sur les runs de ce prompt
            src_rows = conn.execute(f"""
                SELECT s.domain, COUNT(*) as n_citations
                FROM sources s
                JOIN runs ru ON s.run_id = ru.id
                WHERE ru.prompt_id = ?
                  AND ru.crawl_method = 'ui'
                  AND ru.is_demo = 0
                  AND s.domain IS NOT NULL
                  {lang_clause}
                GROUP BY s.domain
                ORDER BY n_citations DESC
                LIMIT ?
            """, [prompt["prompt_id"]] + lang_params + [MAX_TOP_SOURCES]).fetchall()

            top_sources = [
                {"domain": r["domain"], "n_citations": r["n_citations"]}
                for r in src_rows
            ]

            recommendation = self._build_recommendation(
                prompt=prompt,
                primary_brand=primary_brand,
                competitors_cited=competitors_cited,
                top_sources=top_sources,
            )

            return {
                "prompt": prompt["text"],
                "prompt_id": prompt["prompt_id"],
                "category": prompt["category"],
                "category_label": CATEGORY_LABELS.get(prompt["category"], prompt["category"]),
                "language": prompt["language"],
                "score": round(prompt["avg_score"], 1),
                "n_runs": prompt["n_runs"],
                "competitors_cited": competitors_cited,
                "top_sources": top_sources,
                "recommendation": recommendation,
            }
        finally:
            conn.close()

    def _build_category_summary(self, blind_spots: list) -> dict:
        """Agrège les angles morts par catégorie."""
        by_cat = defaultdict(list)
        for bs in blind_spots:
            by_cat[bs["category"]].append(bs)

        summary = {}
        for cat, items in by_cat.items():
            summary[cat] = {
                "label": CATEGORY_LABELS.get(cat, cat),
                "n_blind_spots": len(items),
                "avg_score": round(sum(i["score"] for i in items) / len(items), 1),
            }
        return summary

    def _global_top_sources(self) -> list:
        """Top 10 domaines cités par Perplexity globalement (tous prompts)."""
        conn = self.db_connect()
        try:
            lang_clause, lang_params = self._language_clause("ru")
            rows = conn.execute(f"""
                SELECT s.domain, COUNT(*) as n_citations
                FROM sources s
                JOIN runs ru ON s.run_id = ru.id
                WHERE ru.crawl_method = 'ui'
                  AND ru.is_demo = 0
                  AND s.domain IS NOT NULL
                  {lang_clause}
                GROUP BY s.domain
                ORDER BY n_citations DESC
                LIMIT 10
            """, lang_params).fetchall()
            return [{"domain": r["domain"], "n_citations": r["n_citations"]}
                    for r in rows]
        finally:
            conn.close()

    def _global_top_competitors(self, primary_brand: str) -> list:
        """Top concurrents cités globalement (toutes les marques sauf la primaire)."""
        conn = self.db_connect()
        try:
            lang_clause, lang_params = self._language_clause("ru")
            rows = conn.execute(f"""
                SELECT b.name, COUNT(*) as mentions
                FROM results r
                JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                WHERE r.mentioned = 1
                  AND b.name != ?
                  AND ru.crawl_method = 'ui'
                  AND ru.is_demo = 0
                  {lang_clause}
                GROUP BY b.name
                ORDER BY mentions DESC
                LIMIT 10
            """, [primary_brand] + lang_params).fetchall()
            return [{"name": r["name"], "mentions": r["mentions"]}
                    for r in rows]
        finally:
            conn.close()

    # ─────────────────────────────────────────────
    # Génération de la reco — V1 templates Python
    # Pour passer en V2 (Claude API), créer une fonction `_build_recommendation_llm()`
    # qui prend les mêmes params et la rendre activable via un flag `use_llm`.
    # ─────────────────────────────────────────────
    def _build_recommendation(self,
                                prompt: dict,
                                primary_brand: str,
                                competitors_cited: list,
                                top_sources: list) -> str:
        """Génère une recommandation actionnable en français (template).

        À terme, override possible avec un appel Claude API pour formulation
        en langage naturel (V2 — quand clients paient).
        """
        category = prompt["category"]
        category_label = CATEGORY_LABELS.get(category, category)
        score = prompt["avg_score"]

        # Préfixe selon score
        if score == 0:
            severity = f"{primary_brand} est totalement absent des réponses Perplexity."
        elif score <= 30:
            severity = f"{primary_brand} est très faiblement mentionné (score {score:.0f}/100)."
        else:
            severity = f"{primary_brand} est mentionné mais sa présence est à améliorer (score {score:.0f}/100)."

        # Concurrents
        if competitors_cited:
            top_comps = ", ".join(c["name"] for c in competitors_cited[:3])
            competitors_part = f"Concurrents qui dominent ce prompt : {top_comps}."
        else:
            competitors_part = "Aucun concurrent particulier ne domine ce prompt — opportunité 'first-mover'."

        # Sources stratégiques
        if top_sources:
            top_srcs = " · ".join(
                f"{s['domain']} ({s['n_citations']})" for s in top_sources[:3]
            )
            sources_part = (
                f"Sources stratégiques utilisées par Perplexity : {top_srcs}. "
                f"Viser une présence éditoriale sur ces domaines."
            )
        else:
            sources_part = "Pas de source dominante identifiée pour ce prompt."

        # Action recommandée selon catégorie
        action = self._action_for_category(category, prompt["text"], primary_brand)

        return " ".join([severity, competitors_part, sources_part, action])

    def _action_for_category(self, category: str, prompt_text: str,
                                primary_brand: str) -> str:
        """Suggère une action concrète selon la catégorie du prompt."""
        actions = {
            "regulation": (
                f"Action : créer une page dédiée mettant en avant le statut "
                f"légal/agréé de {primary_brand}, avec un schema JSON-LD FAQPage "
                f"sur la régulation locale."
            ),
            "payment": (
                f"Action : enrichir la page d'aide aux paiements de {primary_brand} "
                f"avec un schema JSON-LD FAQPage listant tous les moyens de "
                f"paiement acceptés et leurs délais."
            ),
            "visibility": (
                f"Action : produire un article comparatif (ou FAQ) qui mentionne "
                f"explicitement {primary_brand} parmi les leaders du marché, "
                f"hébergé sur le blog ou les pages d'aide du site."
            ),
            "brand": (
                f"Action : créer du contenu éditorial mettant en valeur les "
                f"atouts de {primary_brand} (UX, sécurité, bonus, etc.) "
                f"correspondant au sous-thème de cette requête."
            ),
            "odds": (
                f"Action : publier une page comparative des cotes "
                f"de {primary_brand}, idéalement avec un widget dynamique "
                f"et un schema JSON-LD pour faciliter le crawl par les LLMs."
            ),
            "discovery": (
                f"Action : enrichir la fiche {primary_brand} (Wikipedia, "
                f"presse spécialisée, partenariats média) pour augmenter la "
                f"présence éditoriale."
            ),
            "comparison": (
                f"Action : produire un comparatif explicite intégrant "
                f"{primary_brand} face à ses pairs, pour offrir aux LLMs "
                f"un contenu structuré citable."
            ),
            "reputation": (
                f"Action : capitaliser sur les RP et le content marketing "
                f"pour générer des mentions positives de {primary_brand} "
                f"dans la presse spécialisée."
            ),
            "transactional": (
                f"Action : optimiser les pages transactionnelles de "
                f"{primary_brand} (achat, abonnement, billetterie) avec "
                f"un schema JSON-LD Product/Offer."
            ),
        }
        return actions.get(category, f"Action : produire du contenu structuré sur '{prompt_text[:50]}...'")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_blind_spot(bs: dict, idx: int) -> str:
    """Formatte un angle mort pour affichage console lisible."""
    lines = [
        f"\n[{idx}] {bs['category_label']} — Score {bs['score']:.0f}/100",
        f"    Prompt : {bs['prompt']}",
    ]
    if bs["competitors_cited"]:
        comps = ", ".join(f"{c['name']} ({c['mentions']}×)"
                          for c in bs["competitors_cited"][:3])
        lines.append(f"    Concurrents : {comps}")
    if bs["top_sources"]:
        srcs = ", ".join(f"{s['domain']} ({s['n_citations']}×)"
                         for s in bs["top_sources"][:3])
        lines.append(f"    Sources    : {srcs}")
    lines.append(f"    → {bs['recommendation']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Voxa Gap Analyzer — identifie les angles morts GEO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")
    parser.add_argument("--language", choices=["fr", "pt", "fr-ci", "pl", "en"],
                        help="Marché à analyser. Sinon tous les marchés disponibles.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Seuil score sous lequel un prompt est un angle mort (défaut : {DEFAULT_THRESHOLD})")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en DB (n'appelle pas .run(), bypass le logging agent_runs)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut (au lieu d'affichage console formaté)")
    args = parser.parse_args()

    agent = GapAnalyzer(
        slug=args.slug,
        language=args.language,
        threshold=args.threshold,
    )

    # En dry-run, on bypass le logging DB en appelant directement execute()
    if args.dry_run:
        try:
            agent.validate_input({})
            output = agent.execute({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Mode normal : log dans agent_runs
        try:
            output = agent.run({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)

    # Output
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # Affichage console formaté
    s = output["summary"]
    print()
    print("═" * 70)
    print(f"  Voxa Gap Analyzer — {s['primary_brand']} ({s['language'] or 'tous marchés'})")
    print("═" * 70)
    print(f"  Prompts analysés   : {s['n_prompts_total']}")
    print(f"  Score moyen        : {s['avg_score_global']}/100")
    print(f"  Seuil angle mort   : ≤ {s['threshold']}")
    print(f"  Angles morts       : {s['n_blind_spots']}")
    print("═" * 70)

    # Détail des angles morts
    if output["blind_spots"]:
        print("\nANGLES MORTS DÉTECTÉS (triés par priorité)")
        print("─" * 70)
        for i, bs in enumerate(output["blind_spots"], 1):
            print(_format_blind_spot(bs, i))
    else:
        print(f"\n✓ Aucun angle mort sous le seuil {s['threshold']}/100")

    # Récap par catégorie
    if output["category_summary"]:
        print("\n\nRÉCAP PAR CATÉGORIE")
        print("─" * 70)
        for cat, info in output["category_summary"].items():
            print(f"  {info['label']:30s} : {info['n_blind_spots']} angle(s) mort(s)"
                  f" — score moyen {info['avg_score']:.0f}/100")

    # Top sources
    if output["global_top_sources"]:
        print("\n\nTOP DOMAINES PERPLEXITY (toutes catégories)")
        print("─" * 70)
        for src in output["global_top_sources"]:
            print(f"  {src['n_citations']:3d}×  {src['domain']}")

    # Top concurrents
    if output["global_top_competitors"]:
        print("\nTOP CONCURRENTS")
        print("─" * 70)
        for comp in output["global_top_competitors"]:
            print(f"  {comp['mentions']:3d}×  {comp['name']}")

    print()


if __name__ == "__main__":
    main()