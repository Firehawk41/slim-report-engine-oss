"""The way to change data directly in the database: every statement runs
in one transaction tagged with who made the change and why, so the change
log (audit_log) records both alongside the old and new values. Refuses to
run without --by and --reason.

Usage:
  python scripts/db_edit.py --by JT --reason "why" --sql "UPDATE ..." [--sql "..."] [--dry-run]
  python scripts/db_edit.py --by JT --reason "why" --file change.sql [--dry-run]

--dry-run runs everything, shows what would change, then rolls back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure import audit  # noqa: E402
from infrastructure.database import make_engine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--by", required=True, help="initials of the person responsible")
    parser.add_argument("--reason", required=True, help="why the change is being made")
    parser.add_argument("--sql", action="append", default=[], help="a statement to run (repeatable)")
    parser.add_argument("--file", type=Path, help="a .sql file of statements separated by ';'")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    if not args.by.strip() or not args.reason.strip():
        parser.error("--by and --reason must not be blank")
    statements = list(args.sql)
    if args.file:
        statements += [s.strip() for s in args.file.read_text(encoding="utf-8").split(";") if s.strip()]
    if not statements:
        parser.error("give at least one --sql or a --file")

    with make_engine(args.db).connect() as conn:
        trans = conn.begin()
        audit.set_change_context(conn, args.by.strip(), args.reason.strip())
        start = conn.execute(text("SELECT coalesce(max(id), 0) FROM audit_log")).scalar()
        for sql in statements:
            result = conn.execute(text(sql))
            print(f"{result.rowcount:>5} row(s): {sql}")
        logged = conn.execute(text(
            "SELECT table_name, operation, count(*) FROM audit_log WHERE id > :s GROUP BY 1, 2 ORDER BY 1, 2"
        ), {"s": start}).fetchall()
        print("change log:", ", ".join(f"{t} {op} x{n}" for t, op, n in logged) or "nothing changed")
        if args.dry_run:
            trans.rollback()
            print("DRY RUN -- rolled back, nothing saved")
        else:
            trans.commit()
            print(f"committed as {args.by} -- {args.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
