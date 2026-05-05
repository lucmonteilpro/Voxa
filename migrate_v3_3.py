"""
Voxa — Migration v3.3 (Orchestrateur hybride — colonnes orchestrator_*)
========================================================================
Ajoute les 3 colonnes nécessaires à l'orchestrateur Phase 2F sur la table
`action_items` dans `voxa_accounts.db` UNIQUEMENT.

Pourquoi voxa_accounts.db only :
- Architecture centralisée du module Pack (cf. action_pack.py:38).
- `action_items` n'existe que dans voxa_accounts.db (DT-2 closed 04/05/2026).
- Les autres DBs (voxa.db, voxa_betclic.db, etc.) sont skippées avec log
  explicite — c'est *par design*, pas un oubli.

Colonnes ajoutées sur action_items :
- orchestrator_iterations    INTEGER  (nb d'itérations effectuées)
- orchestrator_history_json  TEXT     (JSON liste des tentatives)
- orchestrator_run_id        INTEGER  (FK vers agent_runs.id)

Patterns (identiques à migrate_v3_2.py) :
- BACKUP : shutil.copy2 + timestamp ISO-safe macOS (`%Y-%m-%dT%H-%M-%S`)
- IDEMPOTENCE : PRAGMA table_info + check par colonne
- SMOKE TEST post-migration : 3 invariants
    1. n_colonnes_avant + n_added == n_colonnes_après
    2. COUNT(action_items) inchangé
    3. valeurs legacy + qc_v2_* inchangées sur les lignes existantes
- RESTORE : --restore depuis backup le plus récent

En cas d'échec à n'importe quelle étape : restore depuis backup + exit 1.

Usage :
    python3 migrate_v3_3.py            # migration normale
    python3 migrate_v3_3.py --dry-run  # preview, ne touche rien
    python3 migrate_v3_3.py --restore  # restore depuis dernier backup v3_3
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
ACCOUNTS_DB = BASE_DIR / "voxa_accounts.db"
TARGET_TABLE = "action_items"

ORCHESTRATOR_COLUMNS = [
    ("orchestrator_iterations",   "INTEGER"),
    ("orchestrator_history_json", "TEXT"),
    ("orchestrator_run_id",       "INTEGER"),
]

# Colonnes existantes (v1 legacy + v2 qc_v2_*) à vérifier intactes après migration
LEGACY_COLUMNS_TO_PRESERVE = (
    "status", "score_real", "measured_at",
    "qc_v2_status", "qc_v2_score_baseline", "qc_v2_score_test_median",
    "qc_v2_delta", "qc_v2_verdicts_json", "qc_v2_run_id", "qc_v2_validated_at",
)


# ─────────────────────────────────────────────
# Helpers DB
# ─────────────────────────────────────────────
def _existing_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _snapshot_legacy_rows(conn: sqlite3.Connection) -> list:
    """Snapshot (id, status, score_real, measured_at, qc_v2_*) pour comparaison."""
    cols = ", ".join(LEGACY_COLUMNS_TO_PRESERVE)
    rows = conn.execute(
        f"SELECT id, {cols} FROM {TARGET_TABLE} ORDER BY id ASC"
    ).fetchall()
    return [tuple(r) for r in rows]


def _count_rows(conn: sqlite3.Connection) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {TARGET_TABLE}").fetchone()[0]


# ─────────────────────────────────────────────
# Backup / Restore
# ─────────────────────────────────────────────
def _backup_path() -> Path:
    """Format ISO-safe macOS : YYYY-MM-DDTHH-MM-SS."""
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return ACCOUNTS_DB.parent / f"{ACCOUNTS_DB.stem}.backup_v3_3_{ts}.db"


def _list_backups_v3_3() -> list:
    pattern = f"{ACCOUNTS_DB.stem}.backup_v3_3_*.db"
    return sorted(ACCOUNTS_DB.parent.glob(pattern), reverse=True)


def _restore_latest() -> Path:
    backups = _list_backups_v3_3()
    if not backups:
        raise FileNotFoundError(f"Aucun backup v3_3 trouvé pour {ACCOUNTS_DB}")
    latest = backups[0]
    shutil.copy2(latest, ACCOUNTS_DB)
    return latest


# ─────────────────────────────────────────────
# Skip log
# ─────────────────────────────────────────────
def _log_skips() -> None:
    other_dbs = sorted(
        p for p in BASE_DIR.glob("voxa*.db")
        if p.name != ACCOUNTS_DB.name
        and ".backup_" not in p.name
        and ".backup-" not in p.name
    )
    for db in other_dbs:
        try:
            c = sqlite3.connect(db)
            try:
                has_table = _table_exists(c, TARGET_TABLE)
            finally:
                c.close()
        except Exception as e:
            print(f"[{db.name}] SKIP — erreur d'ouverture : {e}")
            continue

        if has_table:
            print(
                f"[{db.name}] SKIP — table {TARGET_TABLE} présente "
                f"mais migration ciblée voxa_accounts.db only "
                f"(cf. archi DT-2 closed)"
            )
        else:
            print(
                f"[{db.name}] SKIP — table {TARGET_TABLE} absente "
                f"(architecture centralisée, voir action_pack.py:38)"
            )


# ─────────────────────────────────────────────
# Diagnostic / Migration
# ─────────────────────────────────────────────
def _diagnose() -> dict:
    if not ACCOUNTS_DB.exists():
        return {"error": f"DB introuvable : {ACCOUNTS_DB}"}

    conn = sqlite3.connect(ACCOUNTS_DB)
    try:
        if not _table_exists(conn, TARGET_TABLE):
            return {"error": f"Table {TARGET_TABLE} absente de {ACCOUNTS_DB.name}"}

        existing = _existing_columns(conn, TARGET_TABLE)
        missing = [(name, sql_type) for name, sql_type in ORCHESTRATOR_COLUMNS
                   if name not in existing]
        return {
            "n_columns_before": len(existing),
            "missing_columns": missing,
            "row_count": _count_rows(conn),
            "already_migrated": len(missing) == 0,
        }
    finally:
        conn.close()


def _migrate(dry_run: bool = False) -> dict:
    diag = _diagnose()
    if "error" in diag:
        raise RuntimeError(diag["error"])

    stats = {
        "db": str(ACCOUNTS_DB),
        "n_columns_before": diag["n_columns_before"],
        "row_count_before": diag["row_count"],
        "missing_columns": [c[0] for c in diag["missing_columns"]],
        "added_columns": [],
        "backup": None,
        "skipped": diag["already_migrated"],
    }

    if diag["already_migrated"]:
        return stats

    if dry_run:
        stats["added_columns"] = [c[0] for c in diag["missing_columns"]]
        return stats

    backup = _backup_path()
    shutil.copy2(ACCOUNTS_DB, backup)
    stats["backup"] = str(backup)

    conn = sqlite3.connect(ACCOUNTS_DB)
    try:
        snapshot_before = _snapshot_legacy_rows(conn)
        n_before = len(_existing_columns(conn, TARGET_TABLE))
        count_before = _count_rows(conn)

        for name, sql_type in diag["missing_columns"]:
            conn.execute(
                f"ALTER TABLE {TARGET_TABLE} ADD COLUMN {name} {sql_type}"
            )
            stats["added_columns"].append(name)
        conn.commit()

        n_after = len(_existing_columns(conn, TARGET_TABLE))
        count_after = _count_rows(conn)
        snapshot_after = _snapshot_legacy_rows(conn)

        n_added = len(stats["added_columns"])
        if n_after != n_before + n_added:
            raise RuntimeError(
                f"smoke fail (colonnes) : attendu={n_before + n_added}, "
                f"observé={n_after}"
            )
        if count_after != count_before:
            raise RuntimeError(
                f"smoke fail (lignes) : avant={count_before}, "
                f"après={count_after}"
            )
        if snapshot_after != snapshot_before:
            raise RuntimeError(
                "smoke fail (legacy + qc_v2) : valeurs existantes modifiées "
                "par la migration"
            )

        stats["n_columns_after"] = n_after
        stats["row_count_after"] = count_after
        stats["smoke_test_passed"] = True

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        shutil.copy2(backup, ACCOUNTS_DB)
        raise RuntimeError(
            f"Migration v3.3 FAILED, restored from {backup.name}. Error: {e}"
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return stats


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voxa Migration v3.3 — colonnes orchestrator_* sur action_items",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, ne touche aucune DB")
    parser.add_argument("--restore", action="store_true",
                        help="Restaure voxa_accounts.db depuis le dernier backup v3_3")
    args = parser.parse_args()

    if args.restore:
        try:
            backup_used = _restore_latest()
            print(f"✓ Restauré {ACCOUNTS_DB.name} depuis {backup_used.name}")
        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)
        return

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode}Migration v3.3 (orchestrator_* sur action_items)\n")

    _log_skips()
    print()

    try:
        stats = _migrate(dry_run=args.dry_run)
    except Exception as e:
        print(f"[{ACCOUNTS_DB.name}] ✗ ERREUR : {e}")
        sys.exit(1)

    if stats["skipped"]:
        print(
            f"[{ACCOUNTS_DB.name}] SKIP — déjà migré "
            f"(toutes les colonnes orchestrator_* sont présentes, "
            f"{stats['row_count_before']} lignes, "
            f"{stats['n_columns_before']} colonnes)"
        )
        return

    if args.dry_run:
        print(
            f"[{ACCOUNTS_DB.name}] [DRY-RUN] colonnes à ajouter : "
            f"{', '.join(stats['added_columns'])} "
            f"({stats['row_count_before']} lignes existantes seraient préservées)"
        )
        return

    backup_name = Path(stats["backup"]).name
    print(
        f"[{ACCOUNTS_DB.name}] MIGRATE — table {TARGET_TABLE} présente, "
        f"{stats['row_count_before']} lignes existantes, "
        f"backup créé : {backup_name}"
    )
    print(f"   ✓ Colonnes ajoutées : {', '.join(stats['added_columns'])}")
    print(
        f"   ✓ Smoke test OK : "
        f"{stats['n_columns_before']} → {stats['n_columns_after']} colonnes, "
        f"{stats['row_count_before']} lignes préservées, "
        f"valeurs legacy + qc_v2 intactes"
    )


if __name__ == "__main__":
    main()
