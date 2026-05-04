"""
Smoke test — action_pack DB init.

Vérifie que l'import de `action_pack` crée bien `voxa_accounts.db` avec les
tables `action_packs` et `action_items` via l'effet de bord du
`_init_pack_tables()` appelé au top-level (action_pack.py:85).

Usage : python3 test_action_pack_smoke.py
Exit 0 si OK, 1 si échec.
"""
import sys

SLUG = "__smoke_test__"


def main() -> int:
    try:
        import action_pack  # noqa: F401  — déclenche _init_pack_tables()
        import voxa_db as vdb

        c = vdb.conn_accounts()
        try:
            # Cleanup défensif : supprime un éventuel pack de test orphelin
            c.execute(
                "DELETE FROM action_items WHERE pack_id IN "
                "(SELECT id FROM action_packs WHERE client_slug=?)", (SLUG,))
            c.execute("DELETE FROM action_packs WHERE client_slug=?", (SLUG,))
            c.commit()

            tables = {r["name"] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('action_packs','action_items')").fetchall()}
            assert tables == {"action_packs", "action_items"}, \
                f"tables manquantes : {tables}"

            c.execute("INSERT INTO action_packs (client_slug, week) VALUES (?,?)",
                      (SLUG, "SMOKE"))
            pack_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            c.execute(
                "INSERT INTO action_items (pack_id, prompt_text, content) "
                "VALUES (?,?,?)",
                (pack_id, "smoke prompt", "smoke content"),
            )
            c.commit()

            n = c.execute(
                "SELECT COUNT(*) AS n FROM action_items WHERE pack_id=?",
                (pack_id,)).fetchone()["n"]
            assert n == 1, f"attendu 1 item, trouvé {n}"
        finally:
            try:
                c.execute(
                    "DELETE FROM action_items WHERE pack_id IN "
                    "(SELECT id FROM action_packs WHERE client_slug=?)", (SLUG,))
                c.execute("DELETE FROM action_packs WHERE client_slug=?", (SLUG,))
                c.commit()
            except Exception:
                pass
            c.close()
    except Exception as e:
        print(f"✗ smoke test failed: {e}")
        return 1

    print("✓ smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
