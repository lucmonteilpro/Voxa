"""
Voxa — Migration v3 (Multi-agents support)
============================================
Ajoute le support de l'architecture multi-agents en créant la table
`agent_runs` qui logue chaque exécution d'un agent.

Modifications appliquées sur CHAQUE base voxa_*.db :

1. Nouvelle table `agent_runs` :
   - Trace chaque exécution d'un agent (Gap Analyzer, SEO, Content, QC, Orchestrateur)
   - Stocke input/output JSON pour audit complet
   - Permet de chaîner les agents via parent_run_id (FK self)
   - Permet à l'orchestrateur de numéroter les itérations

2. Index pour requêtes dashboard :
   - idx_agent_runs_slug : récupération rapide des runs par client/agent
   - idx_agent_runs_parent : navigation dans la chaîne d'agents

Caractéristiques :
- IDEMPOTENT : peut être lancé plusieurs fois sans risque (skip si déjà migré)
- BACKUP AUTOMATIQUE : copie chaque DB en .backup_v3_AAAAMMJJ_HHMMSS.db
- DRY-RUN : --dry-run pour preview
- RESTORE : --restore <slug> pour revenir au dernier backup

Usage :
    python3 migrate_v3.py                    # migrate toutes les DBs
    python3 migrate_v3.py --dry-run          # preview only
    python3 migrate_v3.py --slug betclic     # migrate une DB spécifique
    python3 migrate_v3.py --restore betclic  # restore depuis backup v3
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()


# ─────────────────────────────────────────────
# Schema agent_runs
# ─────────────────────────────────────────────
CREATE_AGENT_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY,
  agent_name TEXT NOT NULL,
  slug TEXT NOT NULL,
  language TEXT,
  status TEXT NOT NULL,
  input_json TEXT,
  output_json TEXT,
  error_msg TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  iteration INTEGER DEFAULT 1,
  parent_run_id INTEGER,
  FOREIGN KEY (parent_run_id) REFERENCES agent_runs(id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_slug "
    "ON agent_runs(slug, agent_name, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_parent "
    "ON agent_runs(parent_run_id)",
]


# ─────────────────────────────────────────────
# Découverte des DBs (réutilisé de migrate_v2)
# ─────────────────────────────────────────────
def discover_databases() -> dict:
    """Retourne {slug: Path} pour chaque voxa_*.db trouvée."""
    dbs = {}

    # 1) Tente d'utiliser voxa_db.CLIENTS_CONFIG
    try:
        import voxa_db as vdb
        for slug, cfg in vdb.CLIENTS_CONFIG.items():
            db_path = cfg["db"] if isinstance(cfg["db"], Path) else Path(cfg["db"])
            if db_path.exists():
                dbs[slug] = db_path
    except Exception as e:
        print(f"⚠ voxa_db indisponible ({e}), fallback sur scan filesystem")

    # 2) Fallback : scan
    if not dbs:
        for db in BASE_DIR.glob("voxa*.db"):
            slug = db.stem.replace("voxa_", "").replace("voxa", "psg") or "psg"
            dbs[slug] = db

    return dbs


# ─────────────────────────────────────────────
# Diagnostic
# ─────────────────────────────────────────────
def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    return row is not None


def diagnose(db_path: Path) -> dict:
    """Inspecte une DB et retourne ce qui manque."""
    conn = sqlite3.connect(db_path)
    try:
        agent_runs_present = table_exists(conn, "agent_runs")
        return {
            "needs_agent_runs_table": not agent_runs_present,
            "already_migrated": agent_runs_present,
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Backup (réutilisé de migrate_v2 avec suffixe v3)
# ─────────────────────────────────────────────
def backup_database(db_path: Path) -> Path:
    """Copie en .backup_v3_<timestamp>.db. Retourne le chemin du backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.backup_v3_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups_v3(db_path: Path) -> list:
    """Liste les backups v3, du plus récent au plus ancien."""
    pattern = f"{db_path.stem}.backup_v3_*.db"
    return sorted(db_path.parent.glob(pattern), reverse=True)


# ─────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────
def migrate_database(db_path: Path, dry_run: bool = False) -> dict:
    """Applique la migration v3 sur une DB. Retourne stats."""
    diag = diagnose(db_path)

    stats = {
        "db": str(db_path),
        "created_table_agent_runs": False,
        "created_indexes": [],
        "backup": None,
        "skipped": False,
    }

    if diag["already_migrated"]:
        stats["skipped"] = True
        return stats

    if dry_run:
        stats["created_table_agent_runs"] = diag["needs_agent_runs_table"]
        stats["created_indexes"] = ["idx_agent_runs_slug", "idx_agent_runs_parent"]
        return stats

    # Backup avant modification
    backup_path = backup_database(db_path)
    stats["backup"] = str(backup_path)

    conn = sqlite3.connect(db_path)
    try:
        if diag["needs_agent_runs_table"]:
            conn.execute(CREATE_AGENT_RUNS_TABLE)
            stats["created_table_agent_runs"] = True
            for idx_sql in CREATE_INDEXES:
                conn.execute(idx_sql)
                idx_name = idx_sql.split("EXISTS")[1].strip().split(" ")[0]
                stats["created_indexes"].append(idx_name)

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        # Restore depuis backup en cas d'erreur
        shutil.copy2(backup_path, db_path)
        raise RuntimeError(
            f"Migration v3 FAILED on {db_path.name}, restored from backup. "
            f"Error: {e}"
        )
    finally:
        conn.close()

    return stats


def restore_database(db_path: Path) -> Path:
    """Restaure depuis le backup v3 le plus récent."""
    backups = list_backups_v3(db_path)
    if not backups:
        raise FileNotFoundError(f"Aucun backup v3 trouvé pour {db_path}")
    latest = backups[0]
    shutil.copy2(latest, db_path)
    return latest


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voxa Migration v3 — Multi-agents support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, ne touche aucune DB")
    parser.add_argument("--slug",
                        help="Migrer uniquement ce slug")
    parser.add_argument("--restore",
                        help="Restaure depuis le dernier backup v3")
    args = parser.parse_args()

    dbs = discover_databases()

    if not dbs:
        print("✗ Aucune DB trouvée.")
        sys.exit(1)

    if args.slug:
        if args.slug not in dbs:
            print(f"✗ Slug '{args.slug}' introuvable. Disponibles : {list(dbs.keys())}")
            sys.exit(1)
        dbs = {args.slug: dbs[args.slug]}

    # Mode --restore
    if args.restore:
        if args.restore not in dbs:
            print(f"✗ Slug '{args.restore}' introuvable.")
            sys.exit(1)
        db_path = dbs[args.restore]
        try:
            backup_used = restore_database(db_path)
            print(f"✓ Restauré {db_path.name} depuis {backup_used.name}")
        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)
        return

    # Mode migration normal
    mode_label = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode_label}Migration v3 (agent_runs) — {len(dbs)} DB(s) à traiter\n")

    for slug, db_path in dbs.items():
        print(f"── [{slug}] {db_path.name}")
        diag = diagnose(db_path)

        if diag["already_migrated"]:
            print(f"   ✓ Déjà migrée v3, skip.\n")
            continue

        if diag["needs_agent_runs_table"]:
            print(f"   • Table agent_runs à créer (+ 2 index)")

        if args.dry_run:
            print(f"   [DRY-RUN] Aucun changement appliqué.\n")
            continue

        try:
            stats = migrate_database(db_path)
            print(f"   ✓ Backup créé : {Path(stats['backup']).name}")
            if stats["created_table_agent_runs"]:
                print(f"   ✓ Table agent_runs créée")
            if stats["created_indexes"]:
                print(f"   ✓ Index créés : {', '.join(stats['created_indexes'])}")
            print()
        except Exception as e:
            print(f"   ✗ ERREUR : {e}\n")
            sys.exit(1)

    print("✓ Migration v3 terminée.")


if __name__ == "__main__":
    main()