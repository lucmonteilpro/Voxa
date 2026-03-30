"""
Voxa DB — Couche de lecture sur les DB existantes
==================================================
Ne modifie PAS voxa.db ni voxa_betclic.db.
Lit les données et calcule les KPIs.

Aussi gère voxa_accounts.db (nouvelle DB séparée
pour auth + alertes + recommandations).

Usage :
    from voxa_db import get_score, get_nss, get_competitors, ...
"""

import os
import sqlite3
import json
import secrets
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# ─────────────────────────────────────────────
# DB PATHS
# ─────────────────────────────────────────────

DB_PSG      = BASE_DIR / "voxa.db"
DB_BETCLIC  = BASE_DIR / "voxa_betclic.db"
DB_ACCOUNTS = BASE_DIR / "voxa_accounts.db"  # nouvelle — auth + meta

# Mapping slug → fichier DB + config
CLIENTS_CONFIG = {
    "psg": {
        "db":           DB_PSG,
        "name":         "PSG",
        "full":         "Paris Saint-Germain",
        "vertical":     "sport",
        "primary":      "OM",        # marque primaire telle qu'en DB
        "markets":      ["fr", "en"],
        "dashboard_url": "/psg/",
    },
    "betclic": {
        "db":           DB_BETCLIC,
        "name":         "Betclic",
        "full":         "Betclic",
        "vertical":     "bet",
        "primary":      "Betclic",
        "markets":      ["fr", "pt", "fr-ci", "pl"],
        "dashboard_url": "/betclic/",
    },
}


# ── Chargement dynamique des configs JSON (nouveaux clients) ──
def _load_dynamic_configs():
    """Charge automatiquement les configs JSON depuis configs/ et les ajoute à CLIENTS_CONFIG."""
    config_dir = BASE_DIR / "configs"
    if not config_dir.exists():
        return
    import json as _json
    for p in config_dir.glob("*.json"):
        try:
            cfg = _json.load(open(p, encoding="utf-8"))
            slug = cfg.get("slug", "")
            if not slug or slug in CLIENTS_CONFIG:
                continue
            db_path = BASE_DIR / f"voxa_{slug}.db"
            if not db_path.exists():
                continue  # DB pas encore créée — skip
            CLIENTS_CONFIG[slug] = {
                "db":            db_path,
                "name":          cfg.get("client_name", slug),
                "full":          cfg.get("client_name", slug),
                "vertical":      cfg.get("vertical", "sport"),
                "primary":       cfg.get("primary_brand", slug),
                "markets":       cfg.get("markets", ["fr"]),
                "dashboard_url": f"/{slug}/",
            }
        except Exception:
            pass

_load_dynamic_configs()


# ─────────────────────────────────────────────
# CONNEXIONS
# ─────────────────────────────────────────────

def conn_for(slug: str) -> sqlite3.Connection:
    cfg = CLIENTS_CONFIG.get(slug)
    if not cfg:
        raise ValueError(f"Client inconnu : {slug}")
    c = sqlite3.connect(str(cfg["db"]))
    c.row_factory = sqlite3.Row
    return c


def conn_accounts() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_ACCOUNTS))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


# ─────────────────────────────────────────────
# INIT ACCOUNTS DB (séparée, non destructive)
# ─────────────────────────────────────────────

ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    plan          TEXT    NOT NULL DEFAULT 'trial',
    api_key       TEXT    UNIQUE,
    is_active     INTEGER NOT NULL DEFAULT 1,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_slug TEXT   NOT NULL,
    type       TEXT   NOT NULL,
    severity   TEXT   NOT NULL DEFAULT 'info',
    title      TEXT   NOT NULL,
    body       TEXT   NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT   NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recommendations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_slug  TEXT    NOT NULL,
    prompt_text  TEXT,
    category     TEXT    NOT NULL,
    priority     TEXT    NOT NULL DEFAULT 'medium',
    title        TEXT    NOT NULL,
    body         TEXT    NOT NULL,
    impact_score REAL    DEFAULT 0.0,
    run_date     TEXT,
    is_done      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_alerts_slug  ON alerts(client_slug, is_read);
CREATE INDEX IF NOT EXISTS idx_recos_slug   ON recommendations(client_slug, is_done);
"""


def init_accounts_db():
    c = conn_accounts()
    c.executescript(ACCOUNTS_SCHEMA)
    c.commit()
    return c


# ─────────────────────────────────────────────
# ACCOUNT HELPERS
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    from flask_bcrypt import generate_password_hash
    return generate_password_hash(password).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    from flask_bcrypt import check_password_hash
    return check_password_hash(hashed, password)


def create_account(email: str, password: str, name: str, plan: str = "trial") -> int:
    c = init_accounts_db()
    api_key = "vxa_" + secrets.token_urlsafe(32)
    c.execute(
        "INSERT INTO accounts (email, password_hash, name, plan, api_key) VALUES (?,?,?,?,?)",
        (email, hash_password(password), name, plan, api_key)
    )
    c.commit()
    row = c.execute("SELECT id FROM accounts WHERE email=?", (email,)).fetchone()
    c.close()
    return row["id"]


def get_account_by_email(email: str):
    c = init_accounts_db()
    row = c.execute(
        "SELECT * FROM accounts WHERE email=? AND is_active=1", (email,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


def get_account_by_id(account_id: int):
    c = init_accounts_db()
    row = c.execute(
        "SELECT * FROM accounts WHERE id=? AND is_active=1", (account_id,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


def get_account_by_api_key(api_key: str):
    c = init_accounts_db()
    row = c.execute(
        "SELECT * FROM accounts WHERE api_key=? AND is_active=1", (api_key,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────
# KPI HELPERS (lecture sur DB existantes)
# ─────────────────────────────────────────────

def get_score(slug: str, language: str = None, run_date: str = None) -> dict:
    """GEO Score composite pour la marque primaire."""
    cfg = CLIENTS_CONFIG[slug]
    c = conn_for(slug)

    q = """
        SELECT AVG(res.geo_score) as avg_score,
               COUNT(DISTINCT r.id) as n_prompts,
               r.run_date
        FROM results res
        JOIN runs r   ON res.run_id = r.id
        JOIN brands b ON res.brand_id = b.id
        WHERE b.is_primary = 1 AND r.is_demo = 0
    """
    params = []
    if run_date:
        q += " AND r.run_date = ?"
        params.append(run_date)
    else:
        q += " AND r.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)"
    if language:
        q += " AND r.language = ?"
        params.append(language)

    row = c.execute(q, params).fetchone()
    c.close()

    if not row or row["avg_score"] is None:
        return {"score": None, "n_prompts": 0, "run_date": None}
    return {
        "score":    round(row["avg_score"]),
        "n_prompts": row["n_prompts"],
        "run_date": row["run_date"],
    }


def get_score_by_market(slug: str) -> list:
    """GEO Score par marché (langue)."""
    c = conn_for(slug)
    rows = c.execute("""
        SELECT r.language,
               AVG(res.geo_score) as avg_score,
               r.run_date
        FROM results res
        JOIN runs r   ON res.run_id = r.id
        JOIN brands b ON res.brand_id = b.id
        WHERE b.is_primary = 1 AND r.is_demo = 0
          AND r.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
        GROUP BY r.language
        ORDER BY avg_score DESC
    """).fetchall()
    c.close()
    return [{"language": r["language"], "score": round(r["avg_score"]),
             "run_date": r["run_date"]} for r in rows]


def get_nss(slug: str, language: str = None) -> int:
    """Net Sentiment Score : (positifs - négatifs) / total × 100."""
    c = conn_for(slug)
    q = """
        SELECT res.sentiment, COUNT(*) as n
        FROM results res
        JOIN runs r   ON res.run_id = r.id
        JOIN brands b ON res.brand_id = b.id
        WHERE b.is_primary = 1 AND r.is_demo = 0
          AND r.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
    """
    params = []
    if language:
        q += " AND r.language = ?"
        params.append(language)
    q += " GROUP BY res.sentiment"
    rows = c.execute(q, params).fetchall()
    c.close()
    counts = {r["sentiment"]: r["n"] for r in rows}
    pos   = counts.get("positive", 0)
    neg   = counts.get("negative", 0)
    total = sum(counts.values()) or 1
    return round((pos - neg) / total * 100)


def get_competitors(slug: str, language: str = None, top: int = 10) -> list:
    """Classement de toutes les marques trackées."""
    c = conn_for(slug)
    q = """
        SELECT b.name, b.is_primary,
               AVG(res.geo_score) as avg_score
        FROM results res
        JOIN runs r   ON res.run_id = r.id
        JOIN brands b ON res.brand_id = b.id
        WHERE r.is_demo = 0
          AND r.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
    """
    params = []
    if language:
        q += " AND r.language = ?"
        params.append(language)
    q += " GROUP BY b.id ORDER BY avg_score DESC"
    rows = c.execute(q, params).fetchall()
    c.close()
    return [{"name": r["name"], "is_primary": bool(r["is_primary"]),
             "score": round(r["avg_score"])} for r in rows[:top]]


def get_history(slug: str, n_weeks: int = 12, language: str = None) -> list:
    """Historique GEO Score semaine par semaine."""
    c = conn_for(slug)
    q = """
        SELECT r.run_date, AVG(res.geo_score) as avg_score
        FROM results res
        JOIN runs r   ON res.run_id = r.id
        JOIN brands b ON res.brand_id = b.id
        WHERE b.is_primary = 1 AND r.is_demo = 0
    """
    params = []
    if language:
        q += " AND r.language = ?"
        params.append(language)
    q += " GROUP BY r.run_date ORDER BY r.run_date DESC LIMIT ?"
    params.append(n_weeks)
    rows = c.execute(q, params).fetchall()
    c.close()
    return [{"date": r["run_date"], "score": round(r["avg_score"])}
            for r in reversed(rows)]


def get_weak_prompts(slug: str, threshold: int = 50, language: str = None) -> list:
    """Prompts sous-performants — base des recommandations."""
    c = conn_for(slug)
    q = """
        SELECT p.text, p.category, p.language,
               AVG(res.geo_score) as avg_score
        FROM prompts p
        JOIN runs r     ON p.client_id = r.prompt_id  -- workaround: join via prompt text
        JOIN results res ON res.run_id = r.id
        JOIN brands b   ON res.brand_id = b.id
        WHERE b.is_primary = 1 AND r.is_demo = 0
          AND r.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
    """
    params = []
    if language:
        q += " AND r.language = ?"
        params.append(language)
    q += " GROUP BY p.id HAVING avg_score < ? ORDER BY avg_score ASC LIMIT 10"
    params.append(threshold)
    rows = c.execute(q, params).fetchall()
    c.close()
    return [{"text": r["text"], "category": r["category"],
             "language": r["language"], "score": round(r["avg_score"])} for r in rows]


def get_all_stats() -> dict:
    """Stats résumées pour tous les clients — utilisé par /health et landing."""
    stats = {}
    for slug, cfg in CLIENTS_CONFIG.items():
        try:
            sd = get_score(slug)
            stats[slug] = {
                "name":     cfg["name"],
                "vertical": cfg["vertical"],
                "score":    sd["score"],
                "run_date": sd["run_date"],
                "markets":  cfg["markets"],
                "dashboard_url": cfg["dashboard_url"],
            }
        except Exception as e:
            stats[slug] = {"name": cfg["name"], "error": str(e)}
    return stats


# ─────────────────────────────────────────────
# ALERTS HELPERS
# ─────────────────────────────────────────────

def get_alerts(slug: str, unread_only: bool = False, limit: int = 20) -> list:
    c = init_accounts_db()
    q = "SELECT * FROM alerts WHERE client_slug=?"
    params = [slug]
    if unread_only:
        q += " AND is_read=0"
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = c.execute(q, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def create_alert(slug: str, alert_type: str, severity: str,
                 title: str, body: str) -> bool:
    """Crée une alerte si elle n'existe pas déjà dans les 24h."""
    c = init_accounts_db()
    existing = c.execute("""
        SELECT id FROM alerts
        WHERE client_slug=? AND type=? AND title=?
        AND created_at > datetime('now', '-24 hours')
    """, (slug, alert_type, title)).fetchone()
    if existing:
        c.close()
        return False
    c.execute(
        "INSERT INTO alerts (client_slug, type, severity, title, body) VALUES (?,?,?,?,?)",
        (slug, alert_type, severity, title, body)
    )
    c.commit()
    c.close()
    return True


def mark_alert_read(alert_id: int):
    c = init_accounts_db()
    c.execute("UPDATE alerts SET is_read=1 WHERE id=?", (alert_id,))
    c.commit()
    c.close()


# ─────────────────────────────────────────────
# RECOMMENDATIONS HELPERS
# ─────────────────────────────────────────────

def get_recommendations(slug: str, done: bool = False, limit: int = 20) -> list:
    c = init_accounts_db()
    rows = c.execute("""
        SELECT * FROM recommendations
        WHERE client_slug=? AND is_done=?
        ORDER BY priority DESC, impact_score DESC
        LIMIT ?
    """, (slug, 1 if done else 0, limit)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def create_recommendation(slug: str, title: str, body: str,
                          category: str, priority: str = "medium",
                          impact_score: float = 10.0,
                          prompt_text: str = None,
                          run_date: str = None) -> int:
    c = init_accounts_db()
    # Éviter les doublons (même titre dans les 7 jours)
    existing = c.execute("""
        SELECT id FROM recommendations
        WHERE client_slug=? AND title=?
        AND created_at > datetime('now', '-7 days')
        AND is_done=0
    """, (slug, title)).fetchone()
    if existing:
        c.close()
        return existing["id"]
    c.execute("""
        INSERT INTO recommendations
        (client_slug, title, body, category, priority, impact_score, prompt_text, run_date)
        VALUES (?,?,?,?,?,?,?,?)
    """, (slug, title, body, category, priority, impact_score,
          prompt_text, run_date or date.today().isoformat()))
    c.commit()
    rid = c.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    c.close()
    return rid


def mark_recommendation_done(rec_id: int):
    c = init_accounts_db()
    c.execute("UPDATE recommendations SET is_done=1 WHERE id=?", (rec_id,))
    c.commit()
    c.close()


# ─────────────────────────────────────────────
# INIT + STATUS
# ─────────────────────────────────────────────

def status() -> dict:
    """Retourne l'état complet — utilisé par /health."""
    c = init_accounts_db()
    n_accounts = c.execute("SELECT COUNT(*) as n FROM accounts").fetchone()["n"]
    n_alerts   = c.execute("SELECT COUNT(*) as n FROM alerts WHERE is_read=0").fetchone()["n"]
    n_recos    = c.execute("SELECT COUNT(*) as n FROM recommendations WHERE is_done=0").fetchone()["n"]
    c.close()
    return {
        "accounts":       n_accounts,
        "unread_alerts":  n_alerts,
        "open_recos":     n_recos,
        "clients":        get_all_stats(),
    }


if __name__ == "__main__":
    print("=== Voxa DB Status ===")
    s = status()
    print(f"Accounts : {s['accounts']}")
    print(f"Alertes non lues : {s['unread_alerts']}")
    print(f"Recommandations ouvertes : {s['open_recos']}")
    for slug, info in s["clients"].items():
        print(f"\n[{slug.upper()}] {info.get('name')} — Score: {info.get('score')}/100 — Run: {info.get('run_date')}")