"""
Voxa — Migration v2 (UI crawling support)
==========================================
Ajoute le support du crawling via UI des LLMs (vs API only) en enrichissant
le schéma DB existant.

Modifications appliquées sur CHAQUE base voxa_*.db :

1. Table `runs` — 3 colonnes ajoutées (toutes nullable, valeur par défaut NULL) :
   - screenshot_path     : chemin local du screenshot capturé (UI runs uniquement)
   - crawl_duration_ms   : temps de crawl en millisecondes (monitoring)
   - crawl_method        : 'api' | 'ui' | 'manual' — distingue les sources

2. Nouvelle table `sources` — citations URL extraites des réponses LLM :
   - run_id, url, title, domain, position, snippet
   - foreign key vers runs(id) avec ON DELETE CASCADE
   - index sur run_id et domain

Caractéristiques :
- IDEMPOTENT : peut être lancé plusieurs fois sans risque (skip si déjà migré)
- BACKUP AUTOMATIQUE : copie chaque DB en .backup_AAAAMMJJ_HHMMSS.db avant migration
- DRY-RUN : --dry-run pour voir ce qui serait fait sans toucher la DB
- VERBOSE : affiche chaque étape pour audit

Usage :
    python3 migrate_v2.py                    # migrate toutes les DBs
    python3 migrate_v2.py --dry-run          # preview only, no changes
    python3 migrate_v2.py --slug betclic     # migrate une DB spécifique
    python3 migrate_v2.py --restore betclic  # restore depuis le dernier backup
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()


# ─────────────────────────────────────────────
# Découverte des DBs à migrer
# ─────────────────────────────────────────────
def discover_databases() -> dict:
    """Retourne {slug: Path} pour chaque voxa_*.db trouvée."""
    dbs = {}

    # 1) Tente d'utiliser voxa_db.CLIENTS_CONFIG (source de vérité)
    try:
        import voxa_db as vdb
        for slug, cfg in vdb.CLIENTS_CONFIG.items():
            db_path = cfg["db"] if isinstance(cfg["db"], Path) else Path(cfg["db"])
            if db_path.exists():
                dbs[slug] = db_path
    except Exception as e:
        print(f"⚠ voxa_db indisponible ({e}), fallback sur scan filesystem")

    # 2) Fallback : scan tous les voxa_*.db dans BASE_DIR
    if not dbs:
        for db in BASE_DIR.glob("voxa*.db"):
            slug = db.stem.replace("voxa_", "").replace("voxa", "psg") or "psg"
            dbs[slug] = db

    return dbs


# ─────────────────────────────────────────────
# Inspection — quelles modifications à faire
# ─────────────────────────────────────────────
NEW_RUNS_COLUMNS = [
    ("screenshot_path", "TEXT"),
    ("crawl_duration_ms", "INTEGER"),
    ("crawl_method", "TEXT"),
]

CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  domain TEXT,
  position INTEGER,
  snippet TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sources_run ON sources(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain)",
]


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    """Retourne l'ensemble des noms de colonnes d'une table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    return row is not None


def diagnose(db_path: Path) -> dict:
    """Inspecte une DB et retourne ce qui manque pour la migrer."""
    conn = sqlite3.connect(db_path)
    try:
        runs_cols = get_existing_columns(conn, "runs")
        missing_cols = [(name, typ) for name, typ in NEW_RUNS_COLUMNS
                        if name not in runs_cols]
        sources_present = table_exists(conn, "sources")
        return {
            "missing_runs_columns": missing_cols,
            "needs_sources_table": not sources_present,
            "already_migrated": (not missing_cols) and sources_present,
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────
def backup_database(db_path: Path) -> Path:
    """Copie la DB en .backup_<timestamp>.db. Retourne le chemin du backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups(db_path: Path) -> list:
    """Liste les backups existants pour cette DB, du plus récent au plus ancien."""
    pattern = f"{db_path.stem}.backup_*.db"
    return sorted(db_path.parent.glob(pattern), reverse=True)


# ─────────────────────────────────────────────
# Migration effective
# ─────────────────────────────────────────────
def migrate_database(db_path: Path, dry_run: bool = False) -> dict:
    """Applique la migration sur une DB. Retourne un dict de stats."""
    diag = diagnose(db_path)

    stats = {
        "db": str(db_path),
        "added_columns": [],
        "created_table_sources": False,
        "created_indexes": [],
        "backup": None,
        "skipped": False,
    }

    if diag["already_migrated"]:
        stats["skipped"] = True
        return stats

    if dry_run:
        # En dry-run, on remplit les stats sans toucher la DB
        stats["added_columns"] = [c for c, _ in diag["missing_runs_columns"]]
        stats["created_table_sources"] = diag["needs_sources_table"]
        stats["created_indexes"] = ["idx_sources_run", "idx_sources_domain"] \
            if diag["needs_sources_table"] else []
        return stats

    # Backup AVANT toute modification
    backup_path = backup_database(db_path)
    stats["backup"] = str(backup_path)

    conn = sqlite3.connect(db_path)
    try:
        # 1) Ajouter les colonnes manquantes à `runs`
        for col_name, col_type in diag["missing_runs_columns"]:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col_name} {col_type}")
            stats["added_columns"].append(col_name)

        # 2) Créer la table sources si absente
        if diag["needs_sources_table"]:
            conn.execute(CREATE_SOURCES_TABLE)
            stats["created_table_sources"] = True
            for idx_sql in CREATE_INDEXES:
                conn.execute(idx_sql)
                # Extrait le nom de l'index pour les stats
                idx_name = idx_sql.split("EXISTS")[1].strip().split(" ")[0]
                stats["created_indexes"].append(idx_name)

        conn.commit()
    except Exception as e:
        conn.rollback()
        # En cas d'erreur, on restaure depuis le backup
        conn.close()
        shutil.copy2(backup_path, db_path)
        raise RuntimeError(
            f"Migration FAILED on {db_path.name}, restored from backup. "
            f"Error: {e}"
        )
    finally:
        conn.close()

    return stats


def restore_database(db_path: Path) -> Path:
    """Restaure depuis le backup le plus récent. Retourne le chemin du backup utilisé."""
    backups = list_backups(db_path)
    if not backups:
        raise FileNotFoundError(f"Aucun backup trouvé pour {db_path}")
    latest = backups[0]
    shutil.copy2(latest, db_path)
    return latest


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voxa Migration v2 — UI crawling support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, ne touche aucune DB")
    parser.add_argument("--slug",
                        help="Migrer uniquement ce slug (ex: betclic). "
                             "Sinon migre toutes les DBs trouvées.")
    parser.add_argument("--restore",
                        help="Restaure le slug spécifié depuis son dernier backup")
    args = parser.parse_args()

    dbs = discover_databases()

    if not dbs:
        print("✗ Aucune DB trouvée. Vérifie ton répertoire de travail.")
        sys.exit(1)

    # Filtrage par --slug si demandé
    if args.slug:
        if args.slug not in dbs:
            print(f"✗ Slug '{args.slug}' introuvable. Disponibles : {list(dbs.keys())}")
            sys.exit(1)
        dbs = {args.slug: dbs[args.slug]}

    # Mode --restore
    if args.restore:
        if args.restore not in dbs:
            print(f"✗ Slug '{args.restore}' introuvable. Disponibles : {list(dbs.keys())}")
            sys.exit(1)
        db_path = dbs[args.restore]
        try:
            backup_used = restore_database(db_path)
            print(f"✓ Restauré {db_path.name} depuis {backup_used.name}")
        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)
        return

    # Mode migration normal ou dry-run
    mode_label = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode_label}Migration v2 — {len(dbs)} DB(s) à traiter\n")

    for slug, db_path in dbs.items():
        print(f"── [{slug}] {db_path.name}")
        diag = diagnose(db_path)

        if diag["already_migrated"]:
            print(f"   ✓ Déjà migrée, skip.\n")
            continue

        if diag["missing_runs_columns"]:
            cols = ", ".join(c for c, _ in diag["missing_runs_columns"])
            print(f"   • Colonnes à ajouter sur runs : {cols}")
        if diag["needs_sources_table"]:
            print(f"   • Table sources à créer (+ 2 index)")

        if args.dry_run:
            print(f"   [DRY-RUN] Aucun changement appliqué.\n")
            continue

        try:
            stats = migrate_database(db_path)
            print(f"   ✓ Backup créé : {Path(stats['backup']).name}")
            if stats["added_columns"]:
                print(f"   ✓ Colonnes ajoutées : {', '.join(stats['added_columns'])}")
            if stats["created_table_sources"]:
                print(f"   ✓ Table sources créée")
            if stats["created_indexes"]:
                print(f"   ✓ Index créés : {', '.join(stats['created_indexes'])}")
            print()
        except Exception as e:
            print(f"   ✗ ERREUR : {e}\n")
            sys.exit(1)

    print("✓ Migration terminée.")


if __name__ == "__main__":
    main()