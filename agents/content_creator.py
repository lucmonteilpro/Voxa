"""
Voxa — Agent Content Creator
=============================
Génère le contenu GEO (texte + JSON-LD FAQPage) pour combler les angles morts
identifiés par le Gap Analyzer.

Architecture :
- Hérite de `Agent` (logging unifié dans `agent_runs`)
- Réutilise les fonctions de `action_pack.py` (pas de duplication)
- Continue d'écrire dans la table `action_items` (lue par le dashboard)
- Mode `--from-gap` : récupère automatiquement les angles morts du dernier Gap

Workflow :
1. Identifie les prompts faibles à traiter :
   - Soit fournis explicitement (input_data["target_prompts"])
   - Soit récupérés du dernier Gap Analyzer (mode --from-gap)
   - Soit récupérés via voxa_db.get_weak_prompts (fallback)
2. Pour chaque prompt :
   - Génère contenu (paragraphe 150-200 mots) via Claude API
   - Génère JSON-LD FAQPage (2 paires Q&R)
   - Pré-teste via score_simulator (mode iterate=True)
3. Sauvegarde le pack dans action_packs/action_items
4. Logge le run complet dans agent_runs

Usage CLI :
    # Mode auto (utilise le dernier Gap Analyzer)
    python3 -m agents.content_creator --slug betclic --from-gap

    # Mode legacy (utilise voxa_db.get_weak_prompts)
    python3 -m agents.content_creator --slug betclic

    # Avec self-eval iterate (meilleurs scores prédits, plus lent)
    python3 -m agents.content_creator --slug betclic --iterate

    # Sans persister
    python3 -m agents.content_creator --slug betclic --dry-run

    # Output JSON brut
    python3 -m agents.content_creator --slug betclic --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import Agent

# Réutilisation de action_pack — pas de duplication
import action_pack
import voxa_db as vdb
from score_simulator import simulate, simulate_and_iterate
from geo_optimizer import make_faq_schema


log = logging.getLogger("voxa.content_creator")


# ─────────────────────────────────────────────
# Constantes (tunables)
# ─────────────────────────────────────────────
DEFAULT_N_ITEMS = 5         # max items dans un pack
DEFAULT_TARGET_SCORE = 70   # score cible pour mode iterate
DEFAULT_THRESHOLD = 60      # seuil sous lequel un prompt est faible


class ContentCreator(Agent):
    """Génère contenu GEO + JSON-LD pour les angles morts identifiés.

    Output structuré :
    {
        "summary": {
            "slug": "betclic",
            "brand": "Betclic",
            "week": "2026-W18",
            "pack_id": 42,            # null si dry_run
            "n_items": 5,
            "avg_delta": 35,
            "iterate": True,
            "from_gap": True,
            "gap_run_id": 4,          # null si pas de Gap utilisé
        },
        "items": [
            {
                "prompt_text": "Quels sont les risques de parier sur un site non agréé ANJ ?",
                "category": "regulation",
                "language": "fr",
                "score_current": 0,
                "score_predicted": 78,
                "delta": 78,
                "n_iterations": 3,
                "content": "...",                # texte 150-200 mots
                "jsonld_schema": "{...}",        # FAQPage JSON-LD
            }
        ]
    }
    """

    name = "content_creator"

    def __init__(self,
                 slug: str,
                 n_items: int = DEFAULT_N_ITEMS,
                 iterate: bool = False,
                 target_score: int = DEFAULT_TARGET_SCORE,
                 threshold: int = DEFAULT_THRESHOLD,
                 from_gap: bool = False,
                 dry_run: bool = False,
                 **kwargs):
        super().__init__(slug=slug, **kwargs)
        self.n_items = n_items
        self.iterate = iterate
        self.target_score = target_score
        self.threshold = threshold
        self.from_gap = from_gap
        self.dry_run = dry_run

    def validate_input(self, input_data: dict) -> None:
        """Vérifie que la config client existe."""
        cfg = vdb.CLIENTS_CONFIG.get(self.slug)
        if not cfg:
            raise ValueError(
                f"Client '{self.slug}' inconnu dans voxa_db.CLIENTS_CONFIG. "
                f"Disponibles : {list(vdb.CLIENTS_CONFIG.keys())}"
            )

    def execute(self, input_data: dict) -> dict:
        """Génère le pack content pour les prompts faibles."""
        cfg = vdb.CLIENTS_CONFIG[self.slug]
        brand = cfg["primary"]
        vertical = cfg["vertical"]
        week = action_pack._current_week()

        # 1) Identifier les prompts à traiter
        weak_prompts, gap_run_id = self._select_prompts(input_data)

        if not weak_prompts:
            return {
                "summary": {
                    "slug": self.slug,
                    "brand": brand,
                    "week": week,
                    "pack_id": None,
                    "n_items": 0,
                    "avg_delta": 0,
                    "iterate": self.iterate,
                    "from_gap": self.from_gap,
                    "gap_run_id": gap_run_id,
                    "message": f"Aucun prompt sous {self.threshold}/100 — rien à optimiser",
                },
                "items": [],
            }

        # Limiter au n_items
        weak_prompts = weak_prompts[:self.n_items]

        # 2) Idempotence : check si pack déjà généré cette semaine
        if not self.dry_run:
            existing = action_pack._get_pack_by_week(self.slug, week)
            if existing:
                log.info(f"Pack déjà généré pour {self.slug} semaine {week}")
                return {
                    "summary": {
                        "slug": self.slug,
                        "brand": brand,
                        "week": week,
                        "pack_id": existing["pack_id"],
                        "n_items": existing["n_items"],
                        "avg_delta": 0,  # pas recalculé sur pack existant
                        "iterate": self.iterate,
                        "from_gap": self.from_gap,
                        "gap_run_id": gap_run_id,
                        "message": f"Pack déjà existant cette semaine ({week})",
                    },
                    "items": existing["items"],
                }

        # 3) Pour chaque prompt, générer + simuler
        items = []
        for i, wp in enumerate(weak_prompts, 1):
            item = self._process_prompt(wp, brand, vertical)
            items.append(item)

        # 4) Sauvegarde en DB (sauf dry_run)
        pack_id = None
        if not self.dry_run and items:
            pack_id = action_pack._save_pack(self.slug, week, items)

        avg_delta = round(sum(it["delta"] for it in items) / len(items)) if items else 0

        return {
            "summary": {
                "slug": self.slug,
                "brand": brand,
                "week": week,
                "pack_id": pack_id,
                "n_items": len(items),
                "avg_delta": avg_delta,
                "iterate": self.iterate,
                "from_gap": self.from_gap,
                "gap_run_id": gap_run_id,
                "dry_run": self.dry_run,
            },
            "items": items,
        }

    # ─────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────
    def _select_prompts(self, input_data: dict) -> tuple:
        """Retourne (liste de prompts faibles, gap_run_id ou None).

        Stratégie en cascade :
          1. input_data["target_prompts"] explicite (mode orchestrateur)
          2. Mode --from-gap : dernier run réussi du Gap Analyzer
          3. Fallback : voxa_db.get_weak_prompts (legacy action_pack)
        """
        # Cas 1 : prompts explicites (mode orchestrateur)
        if input_data.get("target_prompts"):
            prompts = input_data["target_prompts"]
            return self._normalize_prompts(prompts), None

        # Cas 2 : mode from-gap
        if self.from_gap:
            last_gap = self.get_last_run("gap_analyzer")
            if last_gap:
                blind_spots = last_gap.get("output", {}).get("blind_spots", [])
                # Convertit le format Gap vers le format attendu par action_pack
                prompts = [
                    {
                        "text": bs["prompt"],
                        "score": bs["score"],
                        "category": bs["category"],
                        "language": bs.get("language", "fr"),
                    }
                    for bs in blind_spots
                ]
                # Tri par priorité : score croissant (les pires d'abord),
                # puis catégorie pour stabilité (régulation/paiement remontent)
                category_priority = {
                    "regulation": 0, "payment": 1,
                    "visibility": 2, "brand": 3, "odds": 4,
                }
                prompts.sort(key=lambda p: (
                    p["score"],
                    category_priority.get(p["category"], 99),
                ))
                return prompts, last_gap["id"]
            log.warning(f"Mode --from-gap mais aucun run Gap Analyzer trouvé pour {self.slug}")

        # Cas 3 : fallback legacy
        prompts = vdb.get_weak_prompts(self.slug, threshold=self.threshold)
        return prompts, None

    def _normalize_prompts(self, prompts: list) -> list:
        """Normalise la structure des prompts (format hétérogène possible)."""
        normalized = []
        for p in prompts:
            normalized.append({
                "text": p.get("text") or p.get("prompt"),
                "score": p.get("score", 0),
                "category": p.get("category", "general"),
                "language": p.get("language", "fr"),
            })
        return normalized

    def _process_prompt(self, wp: dict, brand: str, vertical: str,
                         previous_attempts: list | None = None) -> dict:
        """Génère content + jsonld pour un prompt faible.

        Réutilise action_pack._generate_content et _content_to_faq.
        Mode iterate optionnel pour self-eval loop.

        Si `previous_attempts` est non-None, propagé à `_generate_content` pour
        régénération contextualisée (Phase 2F orchestrateur). Comportement par
        défaut (None) strictement inchangé.
        """
        prompt_text = wp["text"]
        score_current = wp["score"]
        category = wp["category"]
        language = wp.get("language", "fr")

        log.info(f"Processing: {prompt_text[:60]}... (score={score_current})")

        if self.iterate:
            # Self-eval loop via simulate_and_iterate
            result = simulate_and_iterate(
                prompt=prompt_text,
                brand=brand,
                vertical=vertical,
                target_score=self.target_score,
                max_iterations=5,
                llms=["claude"],
            )
            content = result["best_content"]
            score_predicted = result["best_score"]
            n_iterations = result["n_iterations"]
        else:
            # Mode simple : 1 génération + 1 simulation
            content = action_pack._generate_content(
                prompt_text, brand, vertical, category,
                previous_attempts=previous_attempts,
            )
            sim = simulate(prompt_text, content, brand, vertical, llms=["claude"])
            score_predicted = sim["score_predicted"]
            n_iterations = 1

        # Génération JSON-LD FAQPage
        faq_questions = action_pack._content_to_faq(content, brand, prompt_text)
        jsonld = json.dumps(
            make_faq_schema(brand, faq_questions),
            ensure_ascii=False, indent=2,
        ) if faq_questions else None

        return {
            "prompt_text": prompt_text,
            "category": category,
            "language": language,
            "score_current": score_current,
            "score_predicted": score_predicted,
            "content_type": "faq_jsonld",
            "content": content,
            "jsonld_schema": jsonld,
            "n_iterations": n_iterations,
            "status": "pending",
            "delta": score_predicted - score_current,
        }

    # ─────────────────────────────────────────────
    # API publique pour l'orchestrateur (Phase 2F)
    # ─────────────────────────────────────────────
    def regenerate_for_item(self, item: dict,
                             previous_attempts: list | None = None) -> str:
        """Régénère le content pour 1 item donné, optionnellement avec le contexte
        des tentatives précédentes rejetées par QC v2 (Phase 2F orchestrateur).

        Différences vs `execute()` (mode batch) :
        - Travaille sur un seul item explicite (pas de Gap Analyzer / get_weak_prompts)
        - Ne persiste rien (l'orchestrateur gère via _persist_orchestrator_results)
        - Pas de check idempotence pack semaine
        - Pas de mode iterate (si previous_attempts est fourni, le score est mesuré
          par QC v2 réel à l'itération suivante, pas par self-eval)
        - Retourne le content (string), pas le dict d'item complet

        Args:
            item: dict avec au minimum keys `prompt_text`, `category`, `language`,
                  `score_current`. Typiquement une ligne lue de `action_items`.
            previous_attempts: liste des tentatives précédentes rejetées par QC v2,
                  format `[{iteration, content, qc_v2_status, delta, verdicts}, ...]`.
                  None = première génération (équivalent comportement standard).

        Returns:
            Le content généré (string), 150-200 mots typiquement.
        """
        cfg = vdb.CLIENTS_CONFIG[self.slug]
        brand = cfg["primary"]
        vertical = cfg["vertical"]

        wp = {
            "text":     item["prompt_text"],
            "score":    item.get("score_current", 0) or 0,
            "category": item.get("category", "general"),
            "language": item.get("language", "fr"),
        }
        # Force le path non-iterate : `previous_attempts` est incompatible avec
        # `simulate_and_iterate` qui fait sa propre boucle de régénération interne.
        saved_iterate = self.iterate
        self.iterate = False
        try:
            result = self._process_prompt(wp, brand, vertical,
                                            previous_attempts=previous_attempts)
        finally:
            self.iterate = saved_iterate

        return result["content"]


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_console_output(output: dict) -> None:
    """Affiche le rapport en console de façon lisible."""
    s = output["summary"]
    print()
    print("═" * 70)
    print(f"  Voxa Content Creator — {s.get('brand', s['slug'])}")
    print("═" * 70)
    print(f"  Slug          : {s['slug']}")
    print(f"  Semaine       : {s['week']}")
    print(f"  Items générés : {s['n_items']}")
    print(f"  Delta moyen   : +{s['avg_delta']} pts")
    if s.get("pack_id"):
        print(f"  Pack ID       : {s['pack_id']}")
    if s.get("from_gap"):
        if s.get("gap_run_id"):
            print(f"  Source        : Gap Analyzer run #{s['gap_run_id']}")
        else:
            print(f"  Source        : Gap Analyzer (aucun run trouvé, fallback legacy)")
    print(f"  Mode iterate  : {s['iterate']}")
    if s.get("message"):
        print(f"  Note          : {s['message']}")
    print("═" * 70)

    items = output.get("items", [])
    if items:
        print(f"\nITEMS GÉNÉRÉS ({len(items)})")
        print("─" * 70)
        for i, it in enumerate(items, 1):
            # Items issus d'un pack existant en DB n'ont pas la clé 'delta'
            # (calculée à la volée). On la recalcule au besoin.
            score_current = it.get('score_current', 0) or 0
            score_predicted = it.get('score_predicted', 0) or 0
            delta = it.get('delta', score_predicted - score_current)
            delta_sign = "+" if delta >= 0 else ""

            n_iter = it.get('n_iterations', 1)
            category = it.get('category', '?')
            language = it.get('language', '?')

            print(f"\n[{i}] {category} ({language}) — "
                  f"score {score_current:.0f} → {score_predicted:.0f} "
                  f"({delta_sign}{delta:.0f} pts) "
                  f"[{n_iter} itération(s)]")
            print(f"   Prompt : {it.get('prompt_text', '?')[:80]}")
            content_preview = (it.get('content') or '')[:200]
            if content_preview:
                print(f"   Contenu (extrait) : {content_preview}...")
            if it.get("jsonld_schema"):
                print(f"   JSON-LD : ✓ ({len(it['jsonld_schema'])} chars)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Voxa Content Creator — génère contenu GEO pour angles morts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")
    parser.add_argument("--n-items", type=int, default=DEFAULT_N_ITEMS,
                        help=f"Nombre max d'items dans le pack (défaut : {DEFAULT_N_ITEMS})")
    parser.add_argument("--iterate", action="store_true",
                        help="Self-eval loop pour scores plus élevés (plus lent)")
    parser.add_argument("--target-score", type=int, default=DEFAULT_TARGET_SCORE,
                        help=f"Score cible si --iterate (défaut : {DEFAULT_TARGET_SCORE})")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Seuil prompts faibles (défaut : {DEFAULT_THRESHOLD})")
    parser.add_argument("--from-gap", action="store_true",
                        help="Utilise le dernier run Gap Analyzer comme source des angles morts")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en DB (debug)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    try:
        agent = ContentCreator(
            slug=args.slug,
            n_items=args.n_items,
            iterate=args.iterate,
            target_score=args.target_score,
            threshold=args.threshold,
            from_gap=args.from_gap,
            dry_run=args.dry_run,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"⏳ Génération en cours pour {args.slug} ...", file=sys.stderr)

    # Mode dry-run : bypass logging agent_runs
    if args.dry_run:
        try:
            agent.validate_input({})
            output = agent.execute({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            output = agent.run({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    _format_console_output(output)


if __name__ == "__main__":
    main()