"""Weekly review report: what got added to the customer/chemical catalog
and what form text got mapped to what, recently.

Usage: python scripts/recent_mappings_report.py [--db DB_URL] [--days N]

The point isn't to review every catalog addition -- it's to catch the
specific, real failure mode found on 2026-09-22: a customer's vague form
text ("RAW MATERIALS", used generically for several different real
chemicals) got permanently mapped to one specific chemical, globally,
with the technician trusted to make the right call under time pressure.
Nothing here adds friction to that decision -- it's a five-minute,
after-the-fact scan, not a gate. The "new mappings" section is the one
actually worth reading closely: a specific, unambiguous term mapping to
one thing is obviously fine; a generic-sounding term newly mapped to one
specific target is exactly what should catch a reviewer's eye.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from infrastructure.database import make_engine
from sqlalchemy import text

_DEFAULT_DAYS = 7


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print rows as simple space-padded, column-aligned text -- readable
    in a monospace font (the default for plain-text email bodies), with
    no external table library needed for four small, ad hoc sections."""
    if not rows:
        print("  (none)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    print("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=str, default=None, help="DB_URL override")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS, help="how many days back to review")
    args = parser.parse_args(argv)

    cutoff = datetime.now() - timedelta(days=args.days)
    engine = make_engine(args.db)

    with engine.connect() as conn:
        print(f"=== Recent mappings report -- last {args.days} day(s), since {cutoff:%Y-%m-%d %H:%M} ===\n")

        print("--- New customers created ---")
        rows = conn.execute(
            text(
                'SELECT customer_name, created_by, created_at FROM customers '
                'WHERE created_at >= :cutoff ORDER BY created_at DESC'
            ),
            {"cutoff": cutoff},
        ).fetchall()
        _print_table(
            ["Customer", "By", "At"],
            [[r.customer_name, r.created_by or "(unknown)", f"{r.created_at:%Y-%m-%d %H:%M}"] for r in rows],
        )

        print("\n--- New chemicals created ---")
        rows = conn.execute(
            text(
                'SELECT chemical_name, created_by, database_entry_date FROM chemicals '
                'WHERE database_entry_date >= :cutoff ORDER BY database_entry_date DESC'
            ),
            {"cutoff": cutoff},
        ).fetchall()
        _print_table(
            ["Chemical", "By", "At"],
            [[r.chemical_name, r.created_by or "(unknown)", f"{r.database_entry_date:%Y-%m-%d %H:%M}"] for r in rows],
        )

        print("\n--- New customer form-text mappings (existing OR new customer) ---")
        rows = conn.execute(
            text(
                'SELECT fc.form_customer, fc.form_address, c.customer_name, fc.created_by, fc.created_at '
                'FROM form_customers fc JOIN customers c ON c."ID" = fc.customer_id '
                'WHERE fc.created_at >= :cutoff ORDER BY fc.created_at DESC'
            ),
            {"cutoff": cutoff},
        ).fetchall()
        _print_table(
            ["Form text", "Form address", "-> Customer", "By", "At"],
            [
                [r.form_customer, r.form_address, r.customer_name, r.created_by or "(unknown)", f"{r.created_at:%Y-%m-%d %H:%M}"]
                for r in rows
            ],
        )

        print("\n--- New chemical form-text mappings (existing OR new chemical) ---")
        print("    *** This is the section that would have caught the RAW MATERIALS incident. ***")
        rows = conn.execute(
            text(
                'SELECT fc.form_name, c.chemical_name, fc.created_by, fc.created_at '
                'FROM form_chemicals fc JOIN chemicals c ON c."ID" = fc.chemical_id '
                'WHERE fc.created_at >= :cutoff ORDER BY fc.created_at DESC'
            ),
            {"cutoff": cutoff},
        ).fetchall()
        _print_table(
            ["Form text", "-> Chemical", "By", "At"],
            [[r.form_name, r.chemical_name, r.created_by or "(unknown)", f"{r.created_at:%Y-%m-%d %H:%M}"] for r in rows],
        )

        _print_change_log(conn, cutoff)

    return 0


# Above this many rows, one change (same table, operation, who, why,
# transaction) is summarised as a count instead of listed row by row --
# e.g. a migration touching 734 spec rows.
_LIST_LIMIT = 10
_KEY_FIELDS = ("customer_name_raw", "customer_name", "chemical_name_raw", "chemical_name", "form_customer",
               "form_name", "location", "kind", "element_symbol", "ID", "id", "customer_id", "chemical_id")


def _describe_row(row: dict) -> str:
    parts = [str(row[k]) for k in _KEY_FIELDS if row.get(k) not in (None, "")]
    return " / ".join(dict.fromkeys(parts)) or ", ".join(f"{k}={v}" for k, v in row.items())


def _field_changes(old: dict | None, new: dict | None) -> str:
    if old is None:
        return "added"
    if new is None:
        return "deleted"
    changed = [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
    return ", ".join(f"{k}: {old.get(k)!r} -> {new.get(k)!r}" for k in changed)


def _print_change_log(conn, cutoff) -> None:
    """Every change the database recorded in audit_log since cutoff --
    the change-control review for data that has no created_by/created_at
    of its own (limits, settings, edits and deletes anywhere)."""
    print("\n--- Database changes (change log) ---")
    try:
        rows = conn.execute(text(
            "SELECT changed_at, table_name, operation, old_row, new_row, changed_by, reason "
            "FROM audit_log WHERE changed_at >= :cutoff ORDER BY id"
        ), {"cutoff": cutoff}).fetchall()
    except Exception as exc:  # pragma: no cover -- change log not installed
        print(f"  (change log unavailable: {exc.__class__.__name__})")
        return
    if not rows:
        print("  (none)")
        return
    groups: dict[tuple, list] = {}
    for r in rows:
        key = (r.changed_at, r.table_name, r.operation, r.changed_by, r.reason)
        groups.setdefault(key, []).append(r)
    for (at, table, op, by, why), items in groups.items():
        who = by or "(no initials)"
        print(f"  {at:%Y-%m-%d %H:%M}  {table} {op} x{len(items)}  by {who}")
        print(f"      why: {why or '(no reason given)'}")
        if len(items) > _LIST_LIMIT:
            print(f"      {len(items)} rows -- e.g. {_describe_row(items[0].new_row or items[0].old_row)}: "
                  f"{_field_changes(items[0].old_row, items[0].new_row)}")
            continue
        for r in items:
            print(f"      {_describe_row(r.new_row or r.old_row or {})}: {_field_changes(r.old_row, r.new_row)}")


if __name__ == "__main__":
    raise SystemExit(main())
