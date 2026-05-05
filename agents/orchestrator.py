"""
Voxa — Orchestrateur hybride (Phase 2F)
========================================
Prend un Pack existant et fait converger ses items rejetés par le QC v2 via
une boucle de régénération contextualisée.

Pipeline par item en `qc_v2_status='needs_iteration'` :
  loop while iteration ≤ N_MAX_ITERATIONS AND not plateau :
    iteration += 1
    history = [{ "iteration": ..., "content": ..., "qc_v2_status": ...,
                  "delta": ..., "verdicts": [...] }, ...]
    new_content = ContentCreator.regenerate_for_item(item, history)
    qc_result   = QualityController.validate_single_content(item, new_content)
    history.append({iteration, content: new_content, ...qc_result})

    if qc_result.qc_v2_status == "validated" :
       persist(status="validated") ; break
    if iteration ≥ 2 AND _is_plateau(deltas_history) :
       persist(status="abandoned_plateau") ; break

  if iteration > N_MAX_ITERATIONS :
    persist(status="abandoned_after_max_iterations")

Items déjà `validated` au début → SKIP (pas de re-test, pas de régénération).

Statuts finaux possibles :
- `validated` (succès orchestrateur)
- `abandoned_after_max_iterations`
- `abandoned_plateau`
- `error` (déjà géré par QC v2, propagé tel quel)

Le statut `needs_iteration` est uniquement transitoire pendant la boucle,
jamais persisté en final par l'orchestrateur.

Coût attendu (1 item) :
- Pire cas (5 itérations sans converger) : ~25 min crawl + ~0.30$ Anthropic
- Cas moyen (converge en 2-3 itérations) : ~10-15 min, ~0.15$
- Cas optimiste (converge en 1 itération) : ~5 min, ~0.05$

Cible des écritures DB : voxa_accounts.db (table action_items).
Colonnes touchées : orchestrator_iterations, orchestrator_history_json,
orchestrator_run_id, qc_v2_status (et qc_v2_* si nouveau verdict final).

Usage CLI :
    python3 -m agents.orchestrator --slug betclic
    python3 -m agents.orchestrator --slug betclic --pack-id 2
    python3 -m agents.orchestrator --slug betclic --pack-id 2 --dry-run
    python3 -m agents.orchestrator --slug betclic --pack-id 2 --json
    python3 -m agents.orchestrator --slug betclic --pack-id 2 --limit 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from .base import Agent
from .content_creator import ContentCreator
from .quality_controller import QualityController

import voxa_db as vdb


load_dotenv()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


log = logging.getLogger("voxa.orchestrator")


# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────
N_MAX_ITERATIONS = 5
PLATEAU_THRESHOLD = 5  # delta_N ≤ delta_(N-1) + 5 → plateau quantitatif strict


class Orchestrator(Agent):
    """Boucle de convergence pour les items rejetés par QC v2.

    Output structuré :
    {
        "summary": {
            "slug": "betclic",
            "pack_id": 2,
            "n_items_in_pack": 3,
            "n_items_skipped_validated": 2,
            "n_items_processed": 1,
            "n_validated": 1,
            "n_abandoned_plateau": 0,
            "n_abandoned_after_max_iterations": 0,
            "n_error": 0,
            "total_iterations": 2,
            "duration_s": 612.4,
            "n_max_iterations": 5,
            "plateau_threshold": 5,
            "dry_run": false,
        },
        "items": [
            {
                "item_id": 6,
                "skipped": false,
                "final_status": "validated",
                "iterations": 2,
                "history": [...],
                "final_content": "...",
                "final_qc_result": {...},
            },
            {
                "item_id": 7,
                "skipped": true,
                "skip_reason": "qc_v2_status='validated' déjà",
            },
            ...
        ]
    }
    """

    name = "orchestrator"

    def __init__(self,
                 slug: str,
                 pack_id: Optional[int] = None,
                 limit: Optional[int] = None,
                 dry_run: bool = False,
                 **kwargs):
        super().__init__(slug=slug, **kwargs)
        self.pack_id = pack_id
        self.limit = limit
        self.dry_run = dry_run
        # Instances créées paresseusement pour éviter de payer init Patchright
        # si rien à converger.
        self._content_creator: Optional[ContentCreator] = None
        self._quality_controller: Optional[QualityController] = None

    def validate_input(self, input_data: dict) -> None:
        cfg = vdb.CLIENTS_CONFIG.get(self.slug)
        if not cfg:
            raise ValueError(
                f"Client '{self.slug}' inconnu dans voxa_db.CLIENTS_CONFIG. "
                f"Disponibles : {list(vdb.CLIENTS_CONFIG.keys())}"
            )
        if not ANTHROPIC_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY absente de l'environnement / .env "
                "(régénération + filtre Haiku impossibles)."
            )

    def execute(self, input_data: dict) -> dict:
        cfg = vdb.CLIENTS_CONFIG[self.slug]
        brand = cfg["primary"]

        pack = self._load_pack()
        if not pack:
            return self._empty_summary(brand, None,
                                        "Aucun pack trouvé.")

        all_items = pack["items"]
        if self.limit:
            all_items = all_items[:self.limit]

        results = []
        start = time.time()
        n_skipped = 0

        # 1) Boucle sur tous les items du pack
        for item in all_items:
            current_status = item.get("qc_v2_status")
            if current_status == "validated":
                log.info(f"  item #{item['id']} SKIP — qc_v2_status='validated' déjà")
                results.append({
                    "item_id": item["id"],
                    "skipped": True,
                    "skip_reason": "qc_v2_status='validated' déjà",
                })
                n_skipped += 1
                continue

            if current_status not in ("needs_iteration", None):
                log.info(f"  item #{item['id']} SKIP — qc_v2_status='{current_status}' "
                         f"(pas needs_iteration, pas de convergence applicable)")
                results.append({
                    "item_id": item["id"],
                    "skipped": True,
                    "skip_reason": f"qc_v2_status='{current_status}' "
                                    f"(pas needs_iteration)",
                })
                n_skipped += 1
                continue

            # Item à converger
            log.info(f"  item #{item['id']} CONVERGE — "
                     f"prompt: {item['prompt_text'][:60]}...")
            converge_result = self._converge(item)
            results.append(converge_result)

        # 2) Persist (sauf dry-run)
        if not self.dry_run:
            for r in results:
                if not r.get("skipped"):
                    self._persist_orchestrator_results(r)

        duration_s = time.time() - start

        # 3) Stats agrégées
        processed = [r for r in results if not r.get("skipped")]
        n_validated = sum(1 for r in processed if r["final_status"] == "validated")
        n_plateau   = sum(1 for r in processed if r["final_status"] == "abandoned_plateau")
        n_max       = sum(1 for r in processed if r["final_status"] == "abandoned_after_max_iterations")
        n_error     = sum(1 for r in processed if r["final_status"] == "error")
        total_iter  = sum(r["iterations"] for r in processed)

        return {
            "summary": {
                "slug": self.slug,
                "brand": brand,
                "pack_id": pack["pack_id"],
                "n_items_in_pack": len(all_items),
                "n_items_skipped_validated": n_skipped,
                "n_items_processed": len(processed),
                "n_validated": n_validated,
                "n_abandoned_plateau": n_plateau,
                "n_abandoned_after_max_iterations": n_max,
                "n_error": n_error,
                "total_iterations": total_iter,
                "duration_s": round(duration_s, 1),
                "n_max_iterations": N_MAX_ITERATIONS,
                "plateau_threshold": PLATEAU_THRESHOLD,
                "dry_run": self.dry_run,
            },
            "items": results,
        }

    # ─────────────────────────────────────────────
    # Boucle de convergence d'1 item
    # ─────────────────────────────────────────────
    def _converge(self, item: dict) -> dict:
        """Boucle de convergence d'1 item. Return final result dict."""
        history: list = []
        deltas_history: list = []

        for iteration in range(1, N_MAX_ITERATIONS + 1):
            log.info(f"    iteration {iteration}/{N_MAX_ITERATIONS}")

            # 1) Régénération contextualisée
            try:
                new_content = self._regenerate_content(item, history)
            except Exception as e:
                log.warning(f"    régénération failed à it.{iteration} : {e}")
                return {
                    "item_id": item["id"],
                    "skipped": False,
                    "final_status": "error",
                    "iterations": iteration - 1,
                    "history": history,
                    "error": f"regenerate failed at iter {iteration}: {e}",
                }

            # 2) Validation QC v2 (4 crawls Perplexity + 3 Haiku)
            try:
                qc_result = self._validate_via_qc_v2(item, new_content)
            except Exception as e:
                log.warning(f"    validation QC v2 failed à it.{iteration} : {e}")
                return {
                    "item_id": item["id"],
                    "skipped": False,
                    "final_status": "error",
                    "iterations": iteration,
                    "history": history,
                    "error": f"qc_v2 failed at iter {iteration}: {e}",
                }

            # 3) Track history (avec snapshot du content au moment de cette itération)
            entry = {
                "iteration": iteration,
                "content": new_content,
                "qc_v2_status": qc_result["qc_v2_status"],
                "score_baseline": qc_result.get("score_baseline"),
                "score_test_median": qc_result.get("score_test_median"),
                "delta": qc_result.get("delta"),
                "verdicts": qc_result.get("verdicts", []),
            }
            history.append(entry)
            current_delta = qc_result.get("delta") or 0
            deltas_history.append(current_delta)

            log.info(f"    iter {iteration} → status={qc_result['qc_v2_status']}, "
                     f"delta={current_delta}")

            # 4) Cas de sortie 1 : validé
            if qc_result["qc_v2_status"] == "validated":
                return {
                    "item_id": item["id"],
                    "skipped": False,
                    "final_status": "validated",
                    "iterations": iteration,
                    "history": history,
                    "final_content": new_content,
                    "final_qc_result": qc_result,
                }

            # 5) Cas de sortie 2 : plateau quantitatif (à partir de l'itération 2)
            if iteration >= 2 and self._is_plateau(deltas_history):
                log.info(f"    plateau détecté (deltas {deltas_history[-2:]}, "
                         f"seuil={PLATEAU_THRESHOLD}) → abandon")
                return {
                    "item_id": item["id"],
                    "skipped": False,
                    "final_status": "abandoned_plateau",
                    "iterations": iteration,
                    "history": history,
                    "final_content": new_content,
                    "final_qc_result": qc_result,
                }

        # 6) Cas de sortie 3 : max itérations atteintes
        log.info(f"    {N_MAX_ITERATIONS} itérations atteintes sans converger → abandon")
        last = history[-1]
        return {
            "item_id": item["id"],
            "skipped": False,
            "final_status": "abandoned_after_max_iterations",
            "iterations": N_MAX_ITERATIONS,
            "history": history,
            "final_content": last["content"],
            "final_qc_result": {
                "qc_v2_status": last["qc_v2_status"],
                "score_baseline": last["score_baseline"],
                "score_test_median": last["score_test_median"],
                "delta": last["delta"],
                "verdicts": last["verdicts"],
            },
        }

    # ─────────────────────────────────────────────
    # Régénération + validation
    # ─────────────────────────────────────────────
    def _regenerate_content(self, item: dict, history: list) -> str:
        """Appelle ContentCreator.regenerate_for_item.

        Si history est vide (1ère itération), pas de bloc contextuel injecté
        → équivalent à une génération fraîche standard.
        Sinon, history est passé comme `previous_attempts`.
        """
        if self._content_creator is None:
            self._content_creator = ContentCreator(slug=self.slug, dry_run=True)
            # validate_input pour s'assurer que la config existe
            self._content_creator.validate_input({})

        previous = history if history else None
        return self._content_creator.regenerate_for_item(
            item, previous_attempts=previous
        )

    def _validate_via_qc_v2(self, item: dict, new_content: str) -> dict:
        """Appelle QualityController.validate_single_content.

        Chaque appel ouvre son propre crawler (option simple, cf. brief Phase 2F).
        Coût startup ~5-10s × N itérations max = acceptable.
        """
        if self._quality_controller is None:
            self._quality_controller = QualityController(slug=self.slug, dry_run=True)
            self._quality_controller.validate_input({})

        return self._quality_controller.validate_single_content(item, new_content)

    @staticmethod
    def _is_plateau(deltas: list) -> bool:
        """True si les 2 derniers deltas n'ont pas progressé de plus de
        PLATEAU_THRESHOLD pts.

        Le seuil de 5 pts absorbe la variance Sonar 2 résiduelle observée
        en Phase 2E (sur item #6 : variance [100, 98, 0]).
        """
        if len(deltas) < 2:
            return False
        return deltas[-1] <= deltas[-2] + PLATEAU_THRESHOLD

    # ─────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────
    def _persist_orchestrator_results(self, result: dict) -> None:
        """UPDATE action_items SET orchestrator_*, qc_v2_* (refletant la
        dernière itération), content (si validated).

        Ne touche PAS les colonnes legacy v1 (status, score_real, measured_at).
        """
        item_id = result["item_id"]
        final_status = result["final_status"]
        iterations = result["iterations"]
        history = result.get("history", [])

        # Snapshot de la dernière itération QC v2 pour update qc_v2_*
        final_qc = result.get("final_qc_result") or {}

        c = vdb.conn_accounts()
        try:
            # Toujours écrire les colonnes orchestrator_*
            c.execute("""
                UPDATE action_items
                SET orchestrator_iterations = ?,
                    orchestrator_history_json = ?,
                    orchestrator_run_id = ?,
                    qc_v2_status = ?,
                    qc_v2_score_baseline = COALESCE(?, qc_v2_score_baseline),
                    qc_v2_score_test_median = COALESCE(?, qc_v2_score_test_median),
                    qc_v2_delta = COALESCE(?, qc_v2_delta),
                    qc_v2_verdicts_json = COALESCE(?, qc_v2_verdicts_json),
                    qc_v2_validated_at = ?
                WHERE id = ?
            """, (
                iterations,
                json.dumps(history, ensure_ascii=False),
                self.run_id,
                final_status,
                final_qc.get("score_baseline"),
                final_qc.get("score_test_median"),
                final_qc.get("delta"),
                json.dumps(final_qc["verdicts"], ensure_ascii=False)
                    if final_qc.get("verdicts") is not None else None,
                datetime.now().isoformat(),
                item_id,
            ))

            # Si validated → remplace aussi content (le nouveau contenu validé)
            if final_status == "validated" and result.get("final_content"):
                c.execute(
                    "UPDATE action_items SET content = ? WHERE id = ?",
                    (result["final_content"], item_id),
                )

            c.commit()
        finally:
            c.close()

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────
    def _load_pack(self) -> Optional[dict]:
        """Charge le pack à converger (pack_id explicite ou dernier du slug)."""
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

    def _empty_summary(self, brand: str, pack_id: Optional[int],
                        message: str) -> dict:
        return {
            "summary": {
                "slug": self.slug, "brand": brand,
                "pack_id": pack_id, "n_items_in_pack": 0,
                "n_items_skipped_validated": 0, "n_items_processed": 0,
                "n_validated": 0,
                "n_abandoned_plateau": 0,
                "n_abandoned_after_max_iterations": 0,
                "n_error": 0,
                "total_iterations": 0,
                "n_max_iterations": N_MAX_ITERATIONS,
                "plateau_threshold": PLATEAU_THRESHOLD,
                "dry_run": self.dry_run,
                "message": message,
            },
            "items": [],
        }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_console_output(output: dict) -> None:
    s = output["summary"]
    print()
    print("═" * 70)
    print(f"  Voxa Orchestrator (Phase 2F) — {s.get('brand', s['slug'])}")
    print("═" * 70)
    print(f"  Slug                              : {s['slug']}")
    print(f"  Pack ID                           : {s.get('pack_id', '—')}")
    print(f"  Items dans le pack                : {s['n_items_in_pack']}")
    print(f"  Items skip (validated)            : {s['n_items_skipped_validated']}")
    print(f"  Items traités (needs_iteration)   : {s['n_items_processed']}")
    if s["n_items_processed"] > 0:
        print(f"  ✓ Convergés (validated)           : {s['n_validated']}")
        print(f"  ⚠ Abandonnés (plateau)            : {s['n_abandoned_plateau']}")
        print(f"  ⚠ Abandonnés (max itérations)     : {s['n_abandoned_after_max_iterations']}")
        if s.get("n_error"):
            print(f"  ✗ Erreurs                         : {s['n_error']}")
        print(f"  Total itérations                  : {s['total_iterations']}")
    print(f"  Max itérations                    : {s['n_max_iterations']}")
    print(f"  Seuil plateau (delta)             : ≤ +{s['plateau_threshold']} pts")
    if "duration_s" in s:
        print(f"  Durée totale                      : {s['duration_s']}s")
    if s.get("message"):
        print(f"  Note                              : {s['message']}")
    print("═" * 70)

    items = output.get("items", [])
    if items:
        print(f"\nDÉTAIL PAR ITEM ({len(items)})")
        print("─" * 70)
        for i, it in enumerate(items, 1):
            if it.get("skipped"):
                print(f"\n[{i}] ⊘ SKIP — item #{it['item_id']} — "
                      f"{it.get('skip_reason', '?')}")
                continue

            icon = {
                "validated": "✓",
                "abandoned_plateau": "⚠",
                "abandoned_after_max_iterations": "⚠",
                "error": "✗",
            }.get(it["final_status"], "?")
            print(f"\n[{i}] {icon} {it['final_status'].upper()} — "
                  f"item #{it['item_id']} en {it['iterations']} itération(s)")

            if it["final_status"] == "error":
                print(f"   Erreur : {it.get('error', '?')}")
                continue

            history = it.get("history", [])
            print(f"   Historique des itérations :")
            for h in history:
                verdicts = h.get("verdicts", [])
                n_pert = sum(1 for v in verdicts if v.get("verdict") == "pertinent")
                n_cos  = sum(1 for v in verdicts if v.get("verdict") == "cosmetique")
                n_abs  = sum(1 for v in verdicts if v.get("verdict") == "absent")
                n_amb  = sum(1 for v in verdicts if v.get("verdict") == "ambiguous")
                content_preview = (h.get("content") or "")[:200].replace("\n", " ")
                print(f"     iter {h['iteration']}: "
                      f"status={h['qc_v2_status']}, "
                      f"baseline={h.get('score_baseline')}, "
                      f"test_med={h.get('score_test_median')}, "
                      f"Δ={h.get('delta', 0):+d}, "
                      f"verdicts pert/cos/abs/amb={n_pert}/{n_cos}/{n_abs}/{n_amb}")
                print(f"       content: {content_preview}…")
                for j, v in enumerate(verdicts, 1):
                    raison = (v.get("raison") or "")[:90]
                    print(f"         [{j}] {v.get('verdict', '?')}: {raison}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Voxa Orchestrator (Phase 2F) — boucle de convergence Pack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--pack-id", type=int)
    parser.add_argument("--limit", type=int,
                        help="Limiter à N items (test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en DB (mais consomme bien Perplexity + Haiku + Claude)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    try:
        agent = Orchestrator(
            slug=args.slug,
            pack_id=args.pack_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"⏳ Orchestrator sur {args.slug} (max {N_MAX_ITERATIONS} itérations/item, "
          f"seuil plateau Δ≤{PLATEAU_THRESHOLD})", file=sys.stderr)

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
