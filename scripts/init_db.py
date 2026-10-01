"""Creates the slim-domain schema (Customer/Chemical/Analysis/Element/
Specification/ReportGenerationLog + their Form* mapping tables) in
whatever database DB_URL points at.

Usage: python scripts/init_db.py [--db DB_URL]

Safe to re-run: create_all only creates tables that don't already exist.
"""

from __future__ import annotations

import argparse

from infrastructure.database import Base, make_engine

# Import every repository module so its Row classes register on Base.metadata
# before create_all runs -- side-effect imports, not otherwise used here.
from slim_domain.domain.analysis import analysis_repository  # noqa: F401
from slim_domain.domain.chemical import chemical_repository  # noqa: F401
from slim_domain.domain.customer import customer_repository  # noqa: F401
from slim_domain.domain.element import element_repository  # noqa: F401
from slim_domain.domain.report_folder import report_folder_repository  # noqa: F401
from slim_domain.domain.report_log import report_log_repository  # noqa: F401
from slim_domain.domain.specification import specification_repository  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=str, default=None, help="DB_URL override")
    args = parser.parse_args()

    engine = make_engine(args.db)
    Base.metadata.create_all(engine)

    print("Schema created (or already present) at:", engine.url)
    print("Tables:", sorted(Base.metadata.tables.keys()))


if __name__ == "__main__":
    main()
