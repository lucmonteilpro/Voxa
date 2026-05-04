"""
Voxa — Agent Quality Controller
================================
Valide les contenus générés par le Content Creator en re-crawlant Perplexity
avec un prompt augmenté incluant le contenu proposé.

Concept clé :
- Le Content Creator génère un contenu et prédit un score via simulation
- Le Quality Controller mesure le score RÉEL via Perplexity en condition réelle
- Compare prédiction vs réalité, valide si target atteint, sinon retour Content Creator

C'est ce qui rend Voxa unique vs Meikai : on ne se contente pas d'une
simulation interne, on valide dans Perplexity avant de recommander la
publication. Personne d'autre ne fait ça.

Architecture :
- Hérite de `Agent` (logging unifié dans `agent_runs`)
- Réutilise `PerplexityCrawler` (même crawler que tracker UI)
- Réutilise `parse_response` de tracker.py (cohérence des scores)
- Met à jour `action_items.score_real` (colonne déjà existante)

Workflow :
1. Récupère le pack à valider (dernier pack du slug, ou pack-id explicite)
2. Pour chaque item :
   a) Construit un prompt augmenté (prompt original + contenu proposé)
   b) Re-crawl Perplexity avec ce prompt
   c) Parse la réponse pour calculer le score réel
   d) Compare au target_score → décide validate / iterate
3. Update `action_items` avec score_real, measured_at, status

Usage CLI :
    # Valide le dernier pack (auto)
    python3 -m agents.quality_controller --slug betclic

    # Valide un pack spécifique
    python3 -m agents.quality_controller --slug betclic --pack-id 2

    # Target score exigeant
    python3 -m agents.quality_controller --slug betclic --target-score 75

    # Test rapide (limite à 2 items)
    python3 -m agents.quality_controller --slug betclic --limit 2

    # Dry-run (pas d'écriture DB)
    python3 -m agents.quality_controller --slug betclic --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import Agent

# Réutilisation existant Voxa
import voxa_db as vdb
from tracker import parse_response
from crawlers.perplexity import PerplexityCrawler


log = logging.getLogger("voxa.quality_controller")


# ─────────────────────────────────────────────
# Constantes (tunables)
# ─────────────────────────────────────────────
DEFAULT_TARGET_SCORE = 60      # score réel minimum pour valider
DEFAULT_LIMIT = None           # pas de limite par défaut

# Délai entre 2 crawls Perplexity (anti-rate-limit)
DELAY_BETWEEN_CRAWLS_S = 8


# ─────────────────────────────────────────────
# Format du prompt augmenté (Option A : structuré formel)
# ─────────────────────────────────────────────
PROMPT_AUGMENTATION_TEMPLATE = """Imagine que le site officiel de {brand} \
publie aujourd'hui le contenu de référence suivant sur son site web :

---
{content}
---

Maintenant, en tenant compte de cette nouvelle source officielle, réponds \
de manière complète à la question suivante : {prompt}"""


class QualityController(Agent):
    """Valide les contenus du Content Creator via re-crawl Perplexity réel.

    Output structuré :
    {
        "summary": {
            "slug": "betclic",
            "brand": "Betclic",
            "pack_id": 2,
            "target_score": 60,
            "n_items_tested": 3,
            "n_validated": 2,
            "n_need_iteration": 1,
            "avg_score_predicted": 47,
            "avg_score_real": 53,
            "delta_pred_vs_real": 6,
            "duration_s": 75,
        },
        "items": [
            {
                "item_id": 5,
                "prompt_text": "...",
                "category": "regulation",
                "language": "fr",
                "score_current": 0,
                "score_predicted": 60,
                "score_real": 65,
                "delta_pred_vs_real": 5,
                "status": "validated",      # ou "needs_iteration"
                "perplexity_response": "...",
                "n_sources_perplexity": 12,
            }
        ]
    }
    """

    name = "quality_controller"

    def __init__(self,
                 slug: str,
                 pack_id: Optional[int] = None,
                 target_score: int = DEFAULT_TARGET_SCORE,
                 limit: Optional[int] = None,
                 dry_run: bool = False,
                 **kwargs):
        super().__init__(slug=slug, **kwargs)
        self.pack_id = pack_id
        self.target_score = target_score
        self.limit = limit
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
        """Re-crawle Perplexity pour chaque item du pack et mesure le score réel."""
        cfg = vdb.CLIENTS_CONFIG[self.slug]
        brand = cfg["primary"]

        # 1) Récupère le pack à valider
        pack = self._load_pack()
        if not pack:
            return {
                "summary": {
                    "slug": self.slug,
                    "brand": brand,
                    "pack_id": None,
                    "target_score": self.target_score,
                    "n_items_tested": 0,
                    "message": "Aucun pack trouvé. Lance d'abord le Content Creator.",
                },
                "items": [],
            }

        items = pack["items"]
        if self.limit:
            items = items[:self.limit]

        if not items:
            return {
                "summary": {
                    "slug": self.slug,
                    "brand": brand,
                    "pack_id": pack.get("pack_id"),
                    "target_score": self.target_score,
                    "n_items_tested": 0,
                    "message": "Pack vide — aucun item à valider.",
                },
                "items": [],
            }

        # 2) Lance Perplexity et boucle sur les items
        results = []
        start_time = time.time()

        with PerplexityCrawler(headless=False) as crawler:
            for i, item in enumerate(items, 1):
                log.info(f"  [{i}/{len(items)}] Validation: {item['prompt_text'][:60]}...")
                result = self._validate_item(crawler, item, brand)
                results.append(result)

                # Délai anti-rate-limit (sauf après le dernier)
                if i < len(items):
                    log.info(f"  Pause {DELAY_BETWEEN_CRAWLS_S}s avant prochain crawl")
                    time.sleep(DELAY_BETWEEN_CRAWLS_S)

        # 3) Persiste en DB (sauf dry-run)
        if not self.dry_run:
            self._update_action_items(results)

        duration_s = time.time() - start_time

        # 4) Stats agrégées
        n_validated = sum(1 for r in results if r["status"] == "validated")
        n_need_iter = sum(1 for r in results if r["status"] == "needs_iteration")
        scores_pred = [r["score_predicted"] for r in results if r.get("score_predicted") is not None]
        scores_real = [r["score_real"] for r in results if r.get("score_real") is not None]
        avg_pred = round(sum(scores_pred) / len(scores_pred)) if scores_pred else 0
        avg_real = round(sum(scores_real) / len(scores_real)) if scores_real else 0

        return {
            "summary": {
                "slug": self.slug,
                "brand": brand,
                "pack_id": pack.get("pack_id"),
                "target_score": self.target_score,
                "n_items_tested": len(results),
                "n_validated": n_validated,
                "n_need_iteration": n_need_iter,
                "avg_score_predicted": avg_pred,
                "avg_score_real": avg_real,
                "delta_pred_vs_real": avg_real - avg_pred,
                "duration_s": round(duration_s, 1),
                "dry_run": self.dry_run,
            },
            "items": results,
        }

    # ─────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────
    def _load_pack(self) -> Optional[dict]:
        """Charge le pack à valider.

        Si pack_id explicite, on prend ce pack. Sinon le dernier du slug.
        """
        c = vdb.conn_accounts()
        try:
            if self.pack_id:
                pack_row = c.execute(
                    "SELECT * FROM action_packs WHERE id = ? AND client_slug = ?",
                    (self.pack_id, self.slug),
                ).fetchone()
            else:
                pack_row = c.execute(
                    "SELECT * FROM action_packs WHERE client_slug = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (self.slug,),
                ).fetchone()

            if not pack_row:
                return None

            items_rows = c.execute(
                "SELECT * FROM action_items WHERE pack_id = ? ORDER BY id ASC",
                (pack_row["id"],),
            ).fetchall()

            return {
                "pack_id": pack_row["id"],
                "week": pack_row["week"],
                "items": [dict(it) for it in items_rows],
            }
        finally:
            c.close()

    def _validate_item(self, crawler: PerplexityCrawler,
                        item: dict, brand: str) -> dict:
        """Valide 1 item via re-crawl Perplexity avec prompt augmenté."""
        prompt_original = item["prompt_text"]
        content = item.get("content") or ""
        language = item.get("language") or "fr"

        # 1) Construit le prompt augmenté
        augmented_prompt = PROMPT_AUGMENTATION_TEMPLATE.format(
            brand=brand,
            content=content,
            prompt=prompt_original,
        )

        # 2) Crawl Perplexity
        try:
            crawler_result = crawler.query(augmented_prompt, language=language)
        except Exception as e:
            log.warning(f"Crawl failed for item {item['id']}: {e}")
            return self._build_error_result(item, str(e))

        if not crawler_result.is_success:
            return self._build_error_result(item, crawler_result.error or "crawl failed")

        # 3) Parse la réponse pour calculer le score réel
        parsed = parse_response(crawler_result.response_text, language)
        primary_data = parsed.get(brand, {})
        score_real = round(primary_data.get("geo_score", 0), 1)

        # 4) Décision validate / needs_iteration
        status = "validated" if score_real >= self.target_score else "needs_iteration"

        score_predicted = item.get("score_predicted") or 0

        return {
            "item_id": item["id"],
            "prompt_text": prompt_original,
            "category": item.get("category"),
            "language": language,
            "score_current": item.get("score_current") or 0,
            "score_predicted": score_predicted,
            "score_real": score_real,
            "delta_pred_vs_real": score_real - score_predicted,
            "status": status,
            "perplexity_response": crawler_result.response_text[:500],
            "n_sources_perplexity": len(crawler_result.sources),
            "primary_mention": primary_data.get("mentioned", False),
            "primary_mention_count": primary_data.get("mention_count", 0),
            "primary_position": primary_data.get("position"),
            "primary_sentiment": primary_data.get("sentiment"),
        }

    def _build_error_result(self, item: dict, error_msg: str) -> dict:
        """Construit un résultat d'item en cas d'erreur de crawl."""
        return {
            "item_id": item["id"],
            "prompt_text": item["prompt_text"],
            "category": item.get("category"),
            "language": item.get("language"),
            "score_current": item.get("score_current") or 0,
            "score_predicted": item.get("score_predicted") or 0,
            "score_real": None,
            "delta_pred_vs_real": None,
            "status": "error",
            "error": error_msg,
        }

    def _update_action_items(self, results: list) -> None:
        """Met à jour la table action_items avec les scores réels."""
        c = vdb.conn_accounts()
        try:
            now = datetime.now().isoformat()
            for r in results:
                if r.get("score_real") is None:
                    continue  # skip les errors
                c.execute("""
                    UPDATE action_items
                    SET score_real = ?,
                        measured_at = ?,
                        status = ?
                    WHERE id = ?
                """, (
                    r["score_real"],
                    now,
                    r["status"],
                    r["item_id"],
                ))
            c.commit()
        finally:
            c.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_console_output(output: dict) -> None:
    """Affiche le rapport en console."""
    s = output["summary"]
    print()
    print("═" * 70)
    print(f"  Voxa Quality Controller — {s.get('brand', s['slug'])}")
    print("═" * 70)
    print(f"  Slug                 : {s['slug']}")
    print(f"  Pack ID              : {s.get('pack_id', '—')}")
    print(f"  Target score         : ≥ {s['target_score']}/100")
    print(f"  Items testés         : {s['n_items_tested']}")
    if s['n_items_tested'] > 0:
        print(f"  ✓ Validés            : {s['n_validated']}")
        print(f"  ⚠ À itérer           : {s['n_need_iteration']}")
        print(f"  Score prédit moyen   : {s['avg_score_predicted']}/100")
        print(f"  Score réel moyen     : {s['avg_score_real']}/100")
        delta = s.get("delta_pred_vs_real", 0)
        delta_label = (
            f"+{delta} (réel > prédit)" if delta > 0
            else f"{delta} (réel < prédit)" if delta < 0
            else "0 (pile)"
        )
        print(f"  Delta prédit→réel    : {delta_label}")
        print(f"  Durée totale         : {s.get('duration_s', '?')}s")
    if s.get("message"):
        print(f"  Note                 : {s['message']}")
    print("═" * 70)

    items = output.get("items", [])
    if items:
        print(f"\nDÉTAIL PAR ITEM ({len(items)})")
        print("─" * 70)
        for i, it in enumerate(items, 1):
            status_icon = {
                "validated": "✓",
                "needs_iteration": "⚠",
                "error": "✗",
            }.get(it["status"], "?")

            print(f"\n[{i}] {status_icon} {it['status'].upper()} — "
                  f"{it.get('category', '?')} ({it.get('language', '?')})")
            print(f"   Prompt : {it['prompt_text'][:80]}")

            if it.get("status") == "error":
                print(f"   Erreur : {it.get('error', '?')}")
                continue

            sc_curr = it.get('score_current', 0)
            sc_pred = it.get('score_predicted', 0)
            sc_real = it.get('score_real', 0)
            print(f"   Scores : initial {sc_curr:.0f} → "
                  f"prédit {sc_pred:.0f} → "
                  f"RÉEL {sc_real:.0f}")
            print(f"   Mention {it.get('primary_mention_count', 0)}× | "
                  f"position {it.get('primary_position', '—')} | "
                  f"sentiment {it.get('primary_sentiment', '—')} | "
                  f"{it.get('n_sources_perplexity', 0)} sources Perplexity")
            response_preview = (it.get('perplexity_response') or '')[:200]
            if response_preview:
                print(f"   Réponse Perplexity (extrait) : {response_preview}...")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Voxa Quality Controller — valide le contenu via Perplexity réel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")
    parser.add_argument("--pack-id", type=int,
                        help="Pack à valider (défaut : dernier pack du slug)")
    parser.add_argument("--target-score", type=int, default=DEFAULT_TARGET_SCORE,
                        help=f"Score réel minimum pour valider (défaut : {DEFAULT_TARGET_SCORE})")
    parser.add_argument("--limit", type=int,
                        help="Limiter à N items (économise les requêtes Perplexity)")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en DB (debug)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    try:
        agent = QualityController(
            slug=args.slug,
            pack_id=args.pack_id,
            target_score=args.target_score,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"⏳ Validation Perplexity en cours pour {args.slug} ...", file=sys.stderr)
    print(f"   (chaque item = 1 crawl Perplexity ~25s + délai)", file=sys.stderr)

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