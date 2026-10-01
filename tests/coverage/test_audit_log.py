"""The database change log (slim-domain infrastructure/audit.py).

Behaviour tests run inside a transaction that is always rolled back, so
they leave nothing behind in the real database. The coverage tests read
the catalog only. All skip when the real PostgreSQL database isn't
reachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from infrastructure import audit
from infrastructure.database import make_engine


@pytest.fixture
def conn():
    try:
        engine = make_engine(None)
        if engine.dialect.name != "postgresql":
            pytest.skip("the change log is PostgreSQL-only")
        connection = engine.connect()
    except Exception as exc:  # pragma: no cover -- environment-dependent
        pytest.skip(f"could not reach the real DB in this environment: {exc}")
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def _triggers(conn) -> set[tuple[str, str]]:
    return {
        (r[0], r[1])
        for r in conn.execute(text(
            "SELECT event_object_table, trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema = 'public'"
        ))
    }


def _rejects(conn, sql: str) -> bool:
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql))
    except DBAPIError as exc:
        savepoint.rollback()
        return "not allowed" in str(exc)
    savepoint.rollback()
    return False


# --- coverage (catalog only) -------------------------------------------------

def test_every_table_is_audited_and_both_logs_are_locked(conn):
    """Fails while any table -- including one a future module adds -- has
    no change-log trigger: re-run scripts/install_audit.py."""
    triggers = _triggers(conn)
    missing = [t for t in audit.audited_tables(conn) if (t, "zz_audit") not in triggers]
    unlocked = [t for t in audit.LOG_TABLES if (t, "zz_lock_rows") not in triggers]
    assert not missing and not unlocked, f"not audited: {missing}; not locked: {unlocked}"


def test_change_log_chain_is_intact(conn):
    assert audit.verify_chain(conn) == []


# --- behaviour (rolled back) -------------------------------------------------

def test_changes_are_logged_with_who_and_why(conn):
    audit.install(conn)
    conn.execute(text("CREATE TEMP TABLE audit_probe (id int PRIMARY KEY, v text, secret text)"))
    conn.execute(text(
        "CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON audit_probe "
        "FOR EACH ROW EXECUTE FUNCTION audit_row('secret')"
    ))
    audit.set_change_context(conn, "JT", "probe test")
    conn.execute(text("INSERT INTO audit_probe VALUES (1, 'a', 'card')"))
    conn.execute(text("UPDATE audit_probe SET v = 'b' WHERE id = 1"))
    conn.execute(text("UPDATE audit_probe SET v = 'b' WHERE id = 1"))  # no visible change: not logged
    conn.execute(text("DELETE FROM audit_probe WHERE id = 1"))

    rows = conn.execute(text(
        "SELECT operation, old_row, new_row, changed_by, reason FROM audit_log "
        "WHERE table_name = 'audit_probe' ORDER BY id"
    )).fetchall()
    assert [r.operation for r in rows] == ["INSERT", "UPDATE", "DELETE"]
    assert rows[1].old_row == {"id": 1, "v": "a"} and rows[1].new_row == {"id": 1, "v": "b"}
    assert all(r.changed_by == "JT" and r.reason == "probe test" for r in rows)
    assert all("secret" not in (r.old_row or {}) and "secret" not in (r.new_row or {}) for r in rows)
    assert audit.verify_chain(conn) == []


def test_both_logs_refuse_edits_deletes_and_truncate(conn):
    audit.install(conn)
    audit.append_entry(conn, "audit_probe", "NOTE", None, {"x": 1}, "JT", "lock test")
    for table in audit.LOG_TABLES:
        assert _rejects(conn, f"UPDATE {table} SET {'reason' if table == 'audit_log' else 'customer_name'} = 'x'")
        assert _rejects(conn, f"DELETE FROM {table}")
        assert _rejects(conn, f"TRUNCATE {table}")


def test_audited_tables_refuse_truncate(conn):
    audit.install(conn)
    assert _rejects(conn, "TRUNCATE specifications")


def test_tampering_breaks_the_chain(conn):
    audit.install(conn)
    first = audit.append_entry(conn, "audit_probe", "NOTE", None, {"x": 1}, "JT", "chain test")
    audit.append_entry(conn, "audit_probe", "NOTE", None, {"x": 2}, "JT", "chain test")
    conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER zz_lock_rows"))  # what an owner could do
    conn.execute(text("UPDATE audit_log SET reason = 'altered' WHERE id = :i"), {"i": first})
    assert first in audit.verify_chain(conn)


def test_a_real_table_with_no_excluded_columns_is_logged(conn):
    """Regression (2026-10-01): with no excluded columns Postgres passes
    TG_ARGV as NULL, which made every write to an audited table fail for a
    few minutes after install. Exercises a real table, rolled back."""
    audit.install(conn)
    audit.set_change_context(conn, "JT", "regression test")
    conn.execute(text("UPDATE customers SET city = city || ' (test)' WHERE \"ID\" = 15"))
    entry = conn.execute(text(
        "SELECT operation, changed_by FROM audit_log WHERE table_name = 'customers' ORDER BY id DESC LIMIT 1"
    )).one()
    assert tuple(entry) == ("UPDATE", "JT")
