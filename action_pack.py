"""
Voxa — Action Pack Generator v1.0
===================================
Génère un "Pack Action Hebdo" pour un client :
  1. Identifie les 3-5 prompts les plus faibles
  2. Génère du contenu optimisé (FAQ/JSON-LD) pour chaque
  3. Pré-teste chaque contenu via score_simulator
  4. Stocke le pack en DB pour affichage dans le dashboard

Usage :
    python3 action_pack.py --slug betclic
    python3 action_pack.py --slug betclic --iterate   # avec self-eval loop
    python3 action_pack.py --slug betclic --dry-run   # sans écrire en DB

Scheduler (après le tracker, le mardi matin) :
    python3 action_pack.py --slug betclic --iterate >> logs/action_pack.log 2>&1
"""

import os
import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("voxa.action_pack")

BASE_DIR = Path(__file__).parent.resolve()

import voxa_db as vdb
from score_simulator import simulate, simulate_and_iterate, call_llm
from geo_optimizer import make_faq_schema


# ─────────────────────────────────────────────
# DB SCHEMA (dans voxa_accounts.db)
# ─────────────────────────────────────────────

PACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_packs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_slug   TEXT    NOT NULL,
    week          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id         INTEGER NOT NULL REFERENCES action_packs(id),
    prompt_text     TEXT    NOT NULL,
    category        TEXT,
    language        TEXT,
    score_current   INTEGER NOT NULL DEFAULT 0,
    score_predicted INTEGER NOT NULL DEFAULT 0,
    score_real      INTEGER,
    content_type    TEXT    NOT NULL DEFAULT 'faq_jsonld',
    content         TEXT    NOT NULL,
    jsonld_schema   TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    implemented_at  TEXT,
    measured_at     TEXT,
    n_iterations    INTEGER DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_packs_slug_week
    ON action_packs(client_slug, week);
CREATE INDEX IF NOT EXISTS idx_items_pack
    ON action_items(pack_id, status);
"""


def _init_pack_tables():
    """Crée les tables action_packs/action_items si absentes."""
    c = vdb.conn_accounts()
    try:
        c.executescript(PACK_SCHEMA)
        c.commit()
    finally:
        c.close()


_init_pack_tables()


# ─────────────────────────────────────────────
# PACK GENERATOR
# ─────────────────────────────────────────────

def generate_pack(slug: str, n_items: int = 5, iterate: bool = False,
                  target_score: int = 70, dry_run: bool = False) -> dict:
    """Génère le pack action de la semaine pour un client.

    Args:
        slug:         identifiant client
        n_items:      nombre d'actions max dans le pack (3-5)
        iterate:      True = self-eval loop (meilleurs résultats, plus lent)
        target_score: score cible pour l'itération
        dry_run:      True = ne pas écrire en DB

    Returns:
        dict avec pack_id, items, stats
    """
    cfg = vdb.CLIENTS_CONFIG.get(slug)
    if not cfg:
        return {"error": f"Client inconnu : {slug}"}

    brand    = cfg["primary"]
    vertical = cfg["vertical"]
    week     = _current_week()

    log.info(f"Generating pack for {cfg['name']} (week {week})")

    # Vérifier s'il existe déjà un pack cette semaine
    if not dry_run:
        existing = _get_pack_by_week(slug, week)
        if existing:
            log.info(f"Pack déjà généré pour {slug} semaine {week}")
            return existing

    # 1. Récupérer les prompts les plus faibles
    weak_prompts = vdb.get_weak_prompts(slug, threshold=60)
    if not weak_prompts:
        log.info(f"Aucun prompt sous 60/100 pour {slug} — rien à optimiser")
        return {"slug": slug, "week": week, "items": [],
                "message": "Tous les scores sont au-dessus de 60/100"}

    weak_prompts = weak_prompts[:n_items]
    log.info(f"  {len(weak_prompts)} prompts faibles identifiés")

    # 2. Pour chaque prompt, générer et pré-tester le contenu

    items = []
    for i, wp in enumerate(weak_prompts, 1):
        prompt_text  = wp["text"]
        score_current = wp["score"]
        category     = wp["category"]
        language     = wp.get("language", "fr")

        log.info(f"  [{i}/{len(weak_prompts)}] {prompt_text[:55]}... (score={score_current})")

        if iterate:
            # Self-eval loop : itérer jusqu'au score cible
            result = simulate_and_iterate(
                prompt=prompt_text, brand=brand, vertical=vertical,
                target_score=target_score, max_iterations=5,
                llms=["claude"])

            content         = result["best_content"]
            score_predicted = result["best_score"]
            n_iterations    = result["n_iterations"]
        else:
            # Mode simple : générer + simuler une fois
            content = _generate_content(prompt_text, brand, vertical, category)
            sim = simulate(prompt_text, content, brand, vertical, llms=["claude"])
            score_predicted = sim["score_predicted"]
            n_iterations = 1

        # Générer le JSON-LD FAQ
        faq_questions = _content_to_faq(content, brand, prompt_text)
        jsonld = json.dumps(make_faq_schema(brand, faq_questions),
                            ensure_ascii=False, indent=2) if faq_questions else None

        item = {
            "prompt_text":     prompt_text,
            "category":        category,
            "language":        language,
            "score_current":   score_current,
            "score_predicted": score_predicted,
            "content_type":    "faq_jsonld",
            "content":         content,
            "jsonld_schema":   jsonld,
            "n_iterations":    n_iterations,
            "status":          "pending",
            "delta":           score_predicted - score_current,
        }
        items.append(item)

        log.info(f"    → score prédit: {score_predicted}/100 "
                 f"(+{score_predicted - score_current}) "
                 f"[{n_iterations} itérations]")

    # 3. Stocker en DB
    pack_id = None
    if not dry_run and items:
        pack_id = _save_pack(slug, week, items)
        log.info(f"  ✓ Pack #{pack_id} sauvegardé ({len(items)} items)")

    result = {
        "slug":      slug,
        "brand":     brand,
        "week":      week,
        "pack_id":   pack_id,
        "n_items":   len(items),
        "items":     items,
        "avg_delta":  round(sum(it["delta"] for it in items) / len(items)) if items else 0,
        "timestamp": datetime.utcnow().isoformat(),
    }

    log.info(f"  Pack terminé : {len(items)} actions, delta moyen +{result['avg_delta']} pts")
    return result


def _generate_content(prompt: str, brand: str, vertical: str, category: str) -> str:
    """Génère du contenu FAQ initial pour un prompt faible."""
    system = (
        f"Tu es un expert en contenu web optimisé pour les moteurs IA (GEO). "
        f"Écris un paragraphe de 150-200 mots qui répond directement à la question. "
        f"Mentionne {brand} dans les 2 premières phrases de façon factuelle. "
        f"Inclure des chiffres ou preuves concrètes si possible. "
        f"Ton professionnel, pas marketing. Texte brut uniquement."
    )
    try:
        return call_llm(system, prompt, llm="claude", max_tokens=400)
    except Exception as e:
        log.warning(f"Content generation failed: {e}")
        return (f"{brand} est une référence dans son secteur. "
                f"Pour répondre à '{prompt}', {brand} se distingue par sa fiabilité "
                f"et son expertise reconnue sur le marché.")


def _content_to_faq(content: str, brand: str, prompt: str) -> list:
    """Transforme un contenu en paires Q&R pour le JSON-LD FAQPage."""
    system = (
        "Transforme le contenu ci-dessous en exactement 2 paires question-réponse "
        "pour un schéma FAQPage JSON-LD. "
        "Réponds UNIQUEMENT en JSON : [{\"question\": \"...\", \"answer\": \"...\"}]"
    )
    try:
        raw = call_llm(system, f"Prompt original : {prompt}\n\nContenu :\n{content}",
                        llm="claude", max_tokens=400)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        return [{"question": prompt, "answer": content[:300]}]


# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def _current_week() -> str:
    """Retourne la semaine au format ISO (2026-W14)."""
    today = date.today()
    return f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"


def _save_pack(slug: str, week: str, items: list) -> int:
    """Sauvegarde un pack et ses items en DB."""
    c = vdb.conn_accounts()
    try:
        c.execute("INSERT INTO action_packs (client_slug, week) VALUES (?,?)",
                  (slug, week))
        pack_id = c.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        for item in items:
            c.execute("""
                INSERT INTO action_items
                (pack_id, prompt_text, category, language,
                 score_current, score_predicted, content_type,
                 content, jsonld_schema, n_iterations, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (pack_id, item["prompt_text"], item["category"],
                  item["language"], item["score_current"],
                  item["score_predicted"], item["content_type"],
                  item["content"], item.get("jsonld_schema"),
                  item["n_iterations"], "pending"))
        c.commit()
        return pack_id
    finally:
        c.close()


def _get_pack_by_week(slug: str, week: str) -> dict | None:
    """Récupère un pack existant pour une semaine donnée."""
    c = vdb.conn_accounts()
    try:
        pack = c.execute(
            "SELECT * FROM action_packs WHERE client_slug=? AND week=?",
            (slug, week)).fetchone()
        if not pack:
            return None

        items = c.execute(
            "SELECT * FROM action_items WHERE pack_id=? ORDER BY score_current ASC",
            (pack["id"],)).fetchall()

        return {
            "slug": slug, "week": week, "pack_id": pack["id"],
            "n_items": len(items),
            "items": [dict(it) for it in items],
            "created_at": pack["created_at"],
        }
    finally:
        c.close()


def get_latest_pack(slug: str) -> dict | None:
    """Récupère le dernier pack d'un client (pour le dashboard)."""
    c = vdb.conn_accounts()
    try:
        pack = c.execute(
            "SELECT * FROM action_packs WHERE client_slug=? ORDER BY created_at DESC LIMIT 1",
            (slug,)).fetchone()
        if not pack:
            return None

        items = c.execute(
            "SELECT * FROM action_items WHERE pack_id=? ORDER BY score_current ASC",
            (pack["id"],)).fetchall()

        return {
            "slug": slug, "week": pack["week"], "pack_id": pack["id"],
            "n_items": len(items),
            "items": [dict(it) for it in items],
            "created_at": pack["created_at"],
        }
    finally:
        c.close()


def get_pack_history(slug: str, limit: int = 12) -> list:
    """Historique des packs pour le dashboard."""
    c = vdb.conn_accounts()
    try:
        packs = c.execute("""
            SELECT p.*, COUNT(i.id) as n_items,
                   AVG(i.score_current) as avg_current,
                   AVG(i.score_predicted) as avg_predicted,
                   AVG(i.score_real) as avg_real,
                   SUM(CASE WHEN i.status='implemented' THEN 1 ELSE 0 END) as n_implemented
            FROM action_packs p
            LEFT JOIN action_items i ON i.pack_id = p.id
            WHERE p.client_slug = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (slug, limit)).fetchall()
        return [dict(p) for p in packs]
    finally:
        c.close()


def mark_item_implemented(item_id: int):
    """Le client marque une action comme implémentée."""
    c = vdb.conn_accounts()
    try:
        c.execute(
            "UPDATE action_items SET status='implemented', implemented_at=datetime('now') WHERE id=?",
            (item_id,))
        c.commit()
    finally:
        c.close()


def update_item_real_score(item_id: int, score_real: int):
    """Met à jour le score réel après re-mesure (4 semaines plus tard)."""
    c = vdb.conn_accounts()
    try:
        c.execute(
            "UPDATE action_items SET score_real=?, measured_at=datetime('now'), status='measured' WHERE id=?",
            (score_real, item_id))
        c.commit()
    finally:
        c.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Voxa — Action Pack Generator")
    parser.add_argument("--slug", required=True, help="Client slug")
    parser.add_argument("--iterate", action="store_true", help="Self-eval loop")
    parser.add_argument("--target", type=int, default=70, help="Score cible")
    parser.add_argument("--n-items", type=int, default=5, help="Nombre d'actions")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire en DB")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"\n{'='*60}")
    print(f"  VOXA — Action Pack Generator v1.0")
    print(f"  Client  : {args.slug}")
    print(f"  Mode    : {'Self-eval loop' if args.iterate else 'Simple'}")
    print(f"  Cible   : {args.target}/100")
    print(f"  Actions : {args.n_items}")
    print(f"{'='*60}\n")

    result = generate_pack(
        slug=args.slug,
        n_items=args.n_items,
        iterate=args.iterate,
        target_score=args.target,
        dry_run=args.dry_run)

    if "error" in result:
        print(f"  ✗ {result['error']}")
    else:
        print(f"\n  Pack {result['week']} — {result['n_items']} actions")
        print(f"  Delta moyen : +{result['avg_delta']} pts")
        for i, item in enumerate(result["items"], 1):
            print(f"\n  [{i}] {item['prompt_text'][:60]}...")
            print(f"      Score actuel: {item['score_current']}/100")
            print(f"      Score prédit: {item['score_predicted']}/100 (+{item['delta']})")
            print(f"      Itérations : {item['n_iterations']}")
            print(f"      Contenu    : {item['content'][:100]}...")

    print(f"\n{'='*60}\n")