"""
Voxa — Agent Quality Controller v2
==================================
Valide les contenus du Content Creator via une comparaison contrôle / test
sur Perplexity, complétée par un filtre Claude Haiku pour évaluer la
pertinence qualitative de la mention.

Concept v2 :
- Un crawl CONTROL (prompt brut, sans injection)        -> score_baseline
- Trois crawls TEST (prompt + contenu via template
  factuel neutre)                                        -> 3 scores → médiane
- delta = score_test_median - score_baseline
- Un appel Claude Haiku par crawl test produit un verdict parmi
  {pertinent, cosmetique, absent, ambiguous, error} sur la mention de la
  marque dans la réponse Perplexity. `ambiguous` = parsing JSON Haiku
  raté ou verdict hors taxonomie. `error` = item entier non testable
  (cf qc_v2_status='error', verdicts unique avec verdict='error').
- Statut final : 'validated' si delta > DELTA_THRESHOLD ET au moins
  PERTINENT_VERDICTS_THRESHOLD verdicts == 'pertinent', sinon
  'needs_iteration' (ou 'error' si l'item est non testable).

Différences vs QC v1 :
- v1 = 1 crawl avec injection + seuil de score brut
- v2 = 4 crawls (1 control + 3 test) + filtre LLM Haiku + delta
- v2 écrit dans des colonnes parallèles qc_v2_* (cf migrate_v3_2.py),
  ne touche PAS aux colonnes legacy (status, score_real, measured_at).

Cible des écritures DB : voxa_accounts.db (table action_items),
cohérent avec l'archi centralisée du module Pack (action_pack.py:38).

Usage CLI :
    python3 -m agents.quality_controller --slug betclic
    python3 -m agents.quality_controller --slug betclic --pack-id 2
    python3 -m agents.quality_controller --slug betclic --pack-id 2 --dry-run
    python3 -m agents.quality_controller --slug betclic --pack-id 2 --json
    python3 -m agents.quality_controller --slug betclic --pack-id 2 --limit 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from .base import Agent

# Réutilisation existant Voxa
import voxa_db as vdb
from tracker import parse_response
from crawlers.perplexity import PerplexityCrawler


# Pattern Voxa : dotenv chargé au top du module (cohérence avec
# voxa_engine.py, tracker_generic.py, action_pack.py, server.py).
load_dotenv()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


log = logging.getLogger("voxa.quality_controller")


# ─────────────────────────────────────────────
# Constantes (tunables)
# ─────────────────────────────────────────────
N_CRAWLS_TEST = 3
N_CRAWLS_CONTROL = 1
DELTA_THRESHOLD = 10
PERTINENT_VERDICTS_THRESHOLD = 2  # sur N_CRAWLS_TEST

HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_MAX_TOKENS = 300
HAIKU_TEMPERATURE = 0.0

# Délai inter-crawls (anti-rate-limit Perplexity). Géré par
# _sleep_between_crawls() qui skip le tout 1er crawl du run.
DELAY_BETWEEN_CRAWLS_S = 8

# Retry max sur erreur réseau d'un crawl unique
CRAWL_RETRY_MAX = 1


# ─────────────────────────────────────────────
# Template factuel neutre (D2)
# ─────────────────────────────────────────────
PROMPT_AUGMENTATION_TEMPLATE = (
    "Le site {domain} a récemment publié le texte suivant :\n\n"
    "« {content} »\n\n"
    "Sur la base de cette information et de tes autres sources, "
    "réponds factuellement à la question : {prompt}"
)


# ─────────────────────────────────────────────
# Filtre Haiku — system prompt JSON strict
# ─────────────────────────────────────────────
HAIKU_SYSTEM_PROMPT = """\
Tu es un évaluateur factuel. Tu reçois un prompt utilisateur, une réponse \
Perplexity, et un nom de marque. Tu dois juger si la marque est mentionnée \
dans la réponse de manière utile à l'utilisateur, ou seulement de façon \
superficielle, ou pas du tout.

Réponds UNIQUEMENT en JSON valide, sans markdown, avec ce schéma exact :
{
  "verdict": "pertinent" | "cosmetique" | "absent",
  "raison": "<phrase courte>",
  "extrait": "<courte citation de la réponse, ou null si verdict=absent>"
}

Critères :
- "pertinent" : la marque est citée avec une info utile (positionnement, \
caractéristique, comparaison étayée, recommandation contextuelle)
- "cosmetique" : la marque apparaît dans une liste sans valeur ajoutée, \
ou en mention de passage sans contexte
- "absent" : la marque n'est pas du tout dans la réponse"""


class QualityController(Agent):
    """Valide les contenus du Content Creator via control/test + Haiku.

    Output structuré (par item) :
    {
        "item_id": 6,
        "prompt_text": "...",
        "category": "regulation",
        "language": "fr",
        "score_baseline": 25,
        "scores_test": [78, 82, 71],
        "score_test_median": 78,
        "delta": 53,
        "verdicts": [
            {"verdict": "pertinent", "raison": "...", "extrait": "...",
             "score_perplexity": 78},
            ...
        ],
        "qc_v2_status": "validated",
        "control_response_preview": "...",
        "test_responses_preview": ["...", "...", "..."]
    }
    """

    name = "quality_controller"

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
        # Compteur global de crawls effectués sur le run entier (anti-rate-limit
        # est une session globale, pas un état par item).
        self._crawl_count = 0

    def validate_input(self, input_data: dict) -> None:
        """Vérifie config client + clé API Haiku présente."""
        cfg = vdb.CLIENTS_CONFIG.get(self.slug)
        if not cfg:
            raise ValueError(
                f"Client '{self.slug}' inconnu dans voxa_db.CLIENTS_CONFIG. "
                f"Disponibles : {list(vdb.CLIENTS_CONFIG.keys())}"
            )
        if not ANTHROPIC_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY absente de l'environnement / .env (filtre Haiku impossible)."
            )

    def execute(self, input_data: dict) -> dict:
        cfg = vdb.CLIENTS_CONFIG[self.slug]
        brand = cfg["primary"]
        domain = cfg.get("domain") or f"https://www.{self.slug}.fr/"

        pack = self._load_pack()
        if not pack:
            return self._empty_summary(brand, domain, None,
                                        "Aucun pack trouvé. Lance d'abord le Content Creator.")

        items = pack["items"]
        if self.limit:
            items = items[:self.limit]
        if not items:
            return self._empty_summary(brand, domain, pack["pack_id"], "Pack vide.")

        results = []
        start = time.time()

        with PerplexityCrawler(headless=False) as crawler:
            for i, item in enumerate(items, 1):
                log.info(f"  [{i}/{len(items)}] item #{item['id']}: "
                         f"{item['prompt_text'][:60]}...")
                result = self._validate_item(crawler, item, brand, domain)
                results.append(result)

        # Persist (Haiku AVANT persist — D3 — donc results contient déjà status final)
        if not self.dry_run:
            for r in results:
                self._persist_qc_v2(r)

        duration_s = time.time() - start

        # Stats agrégées
        n_validated = sum(1 for r in results if r["qc_v2_status"] == "validated")
        n_need_iter = sum(1 for r in results if r["qc_v2_status"] == "needs_iteration")
        n_error = sum(1 for r in results if r["qc_v2_status"] == "error")
        deltas = [r["delta"] for r in results if r.get("delta") is not None]
        avg_delta = round(sum(deltas) / len(deltas)) if deltas else 0

        return {
            "summary": {
                "slug": self.slug,
                "brand": brand,
                "domain": domain,
                "pack_id": pack["pack_id"],
                "n_items_tested": len(results),
                "n_validated": n_validated,
                "n_need_iteration": n_need_iter,
                "n_error": n_error,
                "avg_delta": avg_delta,
                "duration_s": round(duration_s, 1),
                "delta_threshold": DELTA_THRESHOLD,
                "pertinent_verdicts_threshold": PERTINENT_VERDICTS_THRESHOLD,
                "n_crawls_test": N_CRAWLS_TEST,
                "haiku_model": HAIKU_MODEL,
                "dry_run": self.dry_run,
            },
            "items": results,
        }

    # ─────────────────────────────────────────────
    # Pipeline par item
    # ─────────────────────────────────────────────
    def _validate_item(self, crawler: PerplexityCrawler,
                        item: dict, brand: str, domain: str) -> dict:
        """1 control + 3 test + 3 verdicts Haiku → status."""
        prompt_original = item["prompt_text"]
        content = item.get("content") or ""
        language = item.get("language") or "fr"

        if not content.strip():
            return self._build_error_result(item, "content vide, item non testable")

        # 1) Crawl control
        try:
            score_baseline, control_text = self._crawl_control(
                crawler, prompt_original, language, brand)
        except Exception as e:
            log.warning(f"    control crawl failed: {e}")
            return self._build_error_result(item, f"control crawl: {e}")

        # 2) Crawls test x3
        try:
            test_results = self._crawl_test(
                crawler, prompt_original, content, language, brand, domain)
        except Exception as e:
            log.warning(f"    test crawls failed: {e}")
            return self._build_error_result(item, f"test crawls: {e}")

        scores_test = [r["score"] for r in test_results]
        score_test_median = round(statistics.median(scores_test))
        delta = score_test_median - score_baseline

        # 3) Verdicts Haiku x3 (un par crawl test)
        verdicts = []
        for tr in test_results:
            v = self._evaluate_with_haiku(prompt_original, tr["response_text"], brand)
            v["score_perplexity"] = tr["score"]
            verdicts.append(v)

        # 4) Statut final (Haiku AVANT persist — D3)
        qc_v2_status = self._compute_status(delta, verdicts)

        return {
            "item_id": item["id"],
            "prompt_text": prompt_original,
            "category": item.get("category"),
            "language": language,
            "score_current": item.get("score_current") or 0,
            "score_predicted": item.get("score_predicted") or 0,
            "score_baseline": score_baseline,
            "scores_test": scores_test,
            "score_test_median": score_test_median,
            "delta": delta,
            "verdicts": verdicts,
            "qc_v2_status": qc_v2_status,
            "control_response_preview": control_text[:300],
            "test_responses_preview": [r["response_text"][:300] for r in test_results],
        }

    def _sleep_between_crawls(self) -> None:
        """Sleep DELAY_BETWEEN_CRAWLS_S sauf avant le tout 1er crawl du run.

        Le compteur est sur le run entier (pas reset par item) parce que
        l'anti-rate-limit Perplexity est une session globale, pas un état
        par item.
        """
        if self._crawl_count > 0:
            time.sleep(DELAY_BETWEEN_CRAWLS_S)
        self._crawl_count += 1

    def _crawl_control(self, crawler, prompt: str, language: str, brand: str) -> tuple:
        """1 crawl prompt original brut. Retourne (score_baseline, response_text)."""
        self._sleep_between_crawls()
        log.info(f"    control crawl")
        result = self._crawl_with_retry(crawler, prompt, language)
        score = self._score_for_brand(result.response_text, language, brand)
        log.info(f"    control score = {score}")
        return score, result.response_text

    def _crawl_test(self, crawler, prompt: str, content: str,
                     language: str, brand: str, domain: str) -> list:
        """N_CRAWLS_TEST crawls avec injection. Retourne [{score, response_text}]."""
        augmented = PROMPT_AUGMENTATION_TEMPLATE.format(
            domain=domain, content=content, prompt=prompt,
        )
        results = []
        for k in range(N_CRAWLS_TEST):
            self._sleep_between_crawls()
            log.info(f"    test crawl {k+1}/{N_CRAWLS_TEST}")
            r = self._crawl_with_retry(crawler, augmented, language)
            score = self._score_for_brand(r.response_text, language, brand)
            log.info(f"    test {k+1} score = {score}")
            results.append({"score": score, "response_text": r.response_text})
        return results

    def _crawl_with_retry(self, crawler, prompt: str, language: str):
        """Retry simple sur erreur réseau (CRAWL_RETRY_MAX tentatives supplémentaires)."""
        last_exc: Optional[Exception] = None
        for attempt in range(CRAWL_RETRY_MAX + 1):
            try:
                r = crawler.query(prompt, language=language)
                if r.is_success:
                    return r
                last_exc = RuntimeError(r.error or "crawl returned not-success")
            except Exception as e:
                last_exc = e
            if attempt < CRAWL_RETRY_MAX:
                log.warning(f"    crawl retry ({attempt+1}/{CRAWL_RETRY_MAX}) after: {last_exc}")
                time.sleep(DELAY_BETWEEN_CRAWLS_S)
        raise last_exc or RuntimeError("crawl failed (unknown reason)")

    @staticmethod
    def _score_for_brand(response_text: str, language: str, brand: str) -> int:
        parsed = parse_response(response_text, language)
        return round(parsed.get(brand, {}).get("geo_score", 0))

    # ─────────────────────────────────────────────
    # Filtre Haiku
    # ─────────────────────────────────────────────
    def _evaluate_with_haiku(self, prompt: str, response_text: str, brand: str) -> dict:
        """Appel Anthropic Haiku, parse JSON. Fallback ambiguous si parse_failed."""
        import anthropic  # lazy import (cohérence codebase)

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        user_msg = (
            f"PROMPT UTILISATEUR : {prompt}\n\n"
            f"RÉPONSE PERPLEXITY : {response_text}\n\n"
            f"MARQUE À ÉVALUER : {brand}"
        )

        try:
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=HAIKU_MAX_TOKENS,
                temperature=HAIKU_TEMPERATURE,
                system=HAIKU_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as e:
            return {"verdict": "ambiguous", "raison": f"haiku_call_failed: {e}",
                    "extrait": None}

        raw = resp.content[0].text if resp.content else ""

        # Strip défensif des fences markdown si Haiku en met malgré tout
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"verdict": "ambiguous", "raison": "parse_failed",
                    "extrait": None}

        verdict = parsed.get("verdict")
        if verdict not in ("pertinent", "cosmetique", "absent"):
            return {"verdict": "ambiguous",
                    "raison": f"invalid_verdict={verdict!r}",
                    "extrait": None}
        return {
            "verdict": verdict,
            "raison": parsed.get("raison", ""),
            "extrait": parsed.get("extrait"),
        }

    # ─────────────────────────────────────────────
    # Statut final
    # ─────────────────────────────────────────────
    @staticmethod
    def _compute_status(delta: int, verdicts: list) -> str:
        """validated si delta > DELTA_THRESHOLD ET ≥ PERTINENT_VERDICTS_THRESHOLD pertinents."""
        n_pertinent = sum(1 for v in verdicts if v.get("verdict") == "pertinent")
        if delta > DELTA_THRESHOLD and n_pertinent >= PERTINENT_VERDICTS_THRESHOLD:
            return "validated"
        return "needs_iteration"

    # ─────────────────────────────────────────────
    # Persist (UPDATE action_items SET qc_v2_*)
    # ─────────────────────────────────────────────
    def _persist_qc_v2(self, result: dict) -> None:
        """UPDATE qc_v2_* WHERE id = ?

        Ne touche PAS status / score_real / measured_at (D1).
        Pour les items en error, on persiste qc_v2_status='error' avec
        un verdict 'error' au format cohérent (cf _persist_qc_v2_error).
        """
        if result["qc_v2_status"] == "error":
            self._persist_qc_v2_error(result)
            return

        c = vdb.conn_accounts()
        try:
            c.execute("""
                UPDATE action_items
                SET qc_v2_status = ?,
                    qc_v2_score_baseline = ?,
                    qc_v2_score_test_median = ?,
                    qc_v2_delta = ?,
                    qc_v2_verdicts_json = ?,
                    qc_v2_run_id = ?,
                    qc_v2_validated_at = ?
                WHERE id = ?
            """, (
                result["qc_v2_status"],
                result["score_baseline"],
                result["score_test_median"],
                result["delta"],
                json.dumps(result["verdicts"], ensure_ascii=False),
                self.run_id,
                datetime.now().isoformat(),
                result["item_id"],
            ))
            c.commit()
        finally:
            c.close()

    def _persist_qc_v2_error(self, result: dict) -> None:
        """UPDATE en mode error.

        qc_v2_verdicts_json reste TOUJOURS une liste de verdicts (A2) :
        ici une liste à un seul élément avec verdict='error'. Tout
        consommateur peut faire `verdicts[0]['verdict'] == 'error'` sans
        schéma alternatif à gérer.
        """
        error_verdict = [{
            "verdict": "error",
            "raison": result.get("error", "unknown"),
            "extrait": None,
            "score_perplexity": None,
        }]
        c = vdb.conn_accounts()
        try:
            c.execute("""
                UPDATE action_items
                SET qc_v2_status = ?,
                    qc_v2_run_id = ?,
                    qc_v2_validated_at = ?,
                    qc_v2_verdicts_json = ?
                WHERE id = ?
            """, (
                "error",
                self.run_id,
                datetime.now().isoformat(),
                json.dumps(error_verdict, ensure_ascii=False),
                result["item_id"],
            ))
            c.commit()
        finally:
            c.close()

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────
    def _load_pack(self) -> Optional[dict]:
        """Charge le pack à valider (pack_id explicite ou dernier du slug)."""
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

    def _empty_summary(self, brand: str, domain: str,
                        pack_id: Optional[int], message: str) -> dict:
        return {
            "summary": {
                "slug": self.slug, "brand": brand, "domain": domain,
                "pack_id": pack_id, "n_items_tested": 0,
                "delta_threshold": DELTA_THRESHOLD,
                "pertinent_verdicts_threshold": PERTINENT_VERDICTS_THRESHOLD,
                "n_crawls_test": N_CRAWLS_TEST,
                "haiku_model": HAIKU_MODEL,
                "dry_run": self.dry_run,
                "message": message,
            },
            "items": [],
        }

    @staticmethod
    def _build_error_result(item: dict, error_msg: str) -> dict:
        return {
            "item_id": item["id"],
            "prompt_text": item.get("prompt_text", ""),
            "category": item.get("category"),
            "language": item.get("language"),
            "score_baseline": None,
            "scores_test": [],
            "score_test_median": None,
            "delta": None,
            "verdicts": [],
            "qc_v2_status": "error",
            "error": error_msg,
        }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_console_output(output: dict) -> None:
    s = output["summary"]
    print()
    print("═" * 70)
    print(f"  Voxa Quality Controller v2 — {s.get('brand', s['slug'])}")
    print("═" * 70)
    print(f"  Slug                      : {s['slug']}")
    print(f"  Pack ID                   : {s.get('pack_id', '—')}")
    print(f"  Domain (augmentation)     : {s.get('domain', '—')}")
    print(f"  Items testés              : {s['n_items_tested']}")
    if s["n_items_tested"] > 0:
        print(f"  ✓ Validés                 : {s['n_validated']}")
        print(f"  ⚠ À itérer                : {s['n_need_iteration']}")
        if s.get("n_error"):
            print(f"  ✗ Erreurs                 : {s['n_error']}")
        print(f"  Δ moyen                   : {s['avg_delta']:+d} pts")
    print(f"  Seuil delta               : > {s['delta_threshold']} pts")
    print(f"  Seuil verdicts pertinents : ≥ {s['pertinent_verdicts_threshold']}/{s['n_crawls_test']}")
    print(f"  Modèle filtre LLM         : {s['haiku_model']}")
    if s["n_items_tested"] > 0:
        print(f"  Durée totale              : {s.get('duration_s', '?')}s")
    if s.get("message"):
        print(f"  Note                      : {s['message']}")
    print("═" * 70)

    items = output.get("items", [])
    if items:
        print(f"\nDÉTAIL PAR ITEM ({len(items)})")
        print("─" * 70)
        for i, it in enumerate(items, 1):
            icon = {"validated": "✓", "needs_iteration": "⚠",
                    "error": "✗"}.get(it["qc_v2_status"], "?")
            print(f"\n[{i}] {icon} {it['qc_v2_status'].upper()} — "
                  f"item #{it['item_id']} — "
                  f"{it.get('category', '?')} ({it.get('language', '?')})")
            print(f"   Prompt : {it['prompt_text'][:80]}")

            if it["qc_v2_status"] == "error":
                print(f"   Erreur : {it.get('error', '?')}")
                continue

            sc_b = it["score_baseline"]
            sc_t = it["scores_test"]
            sc_m = it["score_test_median"]
            d = it["delta"]
            print(f"   Scores : baseline {sc_b} → test {sc_t} → "
                  f"médiane {sc_m} → Δ {d:+d}")

            verdicts = it.get("verdicts", [])
            n_pert = sum(1 for v in verdicts if v.get("verdict") == "pertinent")
            n_cos = sum(1 for v in verdicts if v.get("verdict") == "cosmetique")
            n_abs = sum(1 for v in verdicts if v.get("verdict") == "absent")
            n_amb = sum(1 for v in verdicts if v.get("verdict") == "ambiguous")
            print(f"   Verdicts Haiku : pertinent={n_pert} cosmetique={n_cos} "
                  f"absent={n_abs} ambiguous={n_amb}")
            for j, v in enumerate(verdicts, 1):
                extrait = v.get("extrait") or "—"
                if isinstance(extrait, str) and len(extrait) > 80:
                    extrait = extrait[:80] + "…"
                print(f"     [{j}] {v.get('verdict', '?')} "
                      f"(perp_score={v.get('score_perplexity', '?')}) "
                      f": {(v.get('raison') or '')[:100]}")
                if v.get("extrait"):
                    print(f"         > {extrait}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Voxa Quality Controller v2 — control + test x3 + Haiku filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic")
    parser.add_argument("--pack-id", type=int)
    parser.add_argument("--limit", type=int,
                        help="Limiter à N items (économise les crawls)")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en DB (mais consomme bien Perplexity + Haiku)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    try:
        agent = QualityController(
            slug=args.slug,
            pack_id=args.pack_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    n_per_item = N_CRAWLS_CONTROL + N_CRAWLS_TEST
    print(f"⏳ QC v2 sur {args.slug} ({n_per_item} crawls + Haiku x{N_CRAWLS_TEST} par item)",
          file=sys.stderr)

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
