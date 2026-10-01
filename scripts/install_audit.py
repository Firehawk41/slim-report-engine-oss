"""Installs (or re-installs) the database change log -- see slim-domain's
infrastructure/audit.py. Idempotent. Re-run after any new table is added
(a new module's tables); tests/coverage/test_audit_log.py fails until then.

Usage: python scripts/install_audit.py [--db DB_URL]
"""

from __future__ import annotations

import argparse

from infrastructure import audit
from infrastructure.database import make_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    with make_engine(args.db).begin() as conn:
        tables = audit.install(conn)
    print(f"Change log installed. Audited ({len(tables)}): {', '.join(tables)}")
    print(f"Locked: {', '.join(audit.LOG_TABLES)}")


if __name__ == "__main__":
    main()
