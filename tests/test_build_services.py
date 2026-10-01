"""build_services() constructs one Session and hands it to all 5 services,
each of which does a one-time read to build its cache. Reads never need a
live session/engine again after that -- but writes do (see
ReportEngineServices' own docstring for the full 2026-09-24 reasoning: a
real live stress test found sharing that one session across concurrent
writes crashes with SQLAlchemy's own reentrancy guard), which is why
build_services() also keeps the `engine` it builds and passes it to every
write-capable service (see test_build_services_passes_engine_to_write_
capable_services below).

Separately: nothing used to end the startup read's own transaction, so it
sat open ("idle in transaction") for the rest of the server's life --
confirmed for real via a live Postgres session found idle-in-transaction
for ~16 hours, which then blocked an unrelated schema migration.
build_services() now commits once right after construction; this pins
that down as a real regression test rather than relying on it being
noticed again in production.
"""

from pathlib import Path

from sqlalchemy import create_engine

from infrastructure.database import Base
from slim_report_engine.cli import build_services


def test_build_services_does_not_leave_an_open_transaction(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    # Create the schema up front via a throwaway engine/connection --
    # build_services() itself just opens a session against an
    # already-migrated DB, same as it would against the real Postgres.
    Base.metadata.create_all(create_engine(db_url))

    services = build_services(db_url)

    # Any of the 5 services' repos share the same underlying session.
    session = services.customer_svc._repo._session
    assert session.in_transaction() is False


def test_build_services_translates_a_mapped_drive_in_report_folder_test_root(tmp_path, monkeypatch):
    """REPORT_FOLDER_TEST_ROOT is routinely a real S:\\ path now (e.g.
    Quality's Macro Validation folder) -- confirmed the hard way that a
    Windows Service can't see a drive-letter mapping regardless of which
    account runs it, the exact same failure mode TESTING_REQUESTS_ROOT
    already had on the input side. build_services() must apply the same
    resolve_mapped_drive() translation here, not just there."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    Base.metadata.create_all(create_engine(db_url))

    monkeypatch.setenv("REPORT_FOLDER_TEST_ROOT", r"Q:\Quality_Items\Macro Validation")
    monkeypatch.setenv("MAPPED_DRIVE_Q_UNC", r"\\LAB-SERVER\LabShare")

    services = build_services(db_url)

    assert services.report_folder_svc.test_root == Path(
        r"\\LAB-SERVER\LabShare\Quality_Items\Macro Validation"
    )


def test_build_services_passes_engine_to_write_capable_services(tmp_path):
    """Confirmed real gap (2026-09-24 doc/test-quality review): the 0.11.0
    fix -- build_services() keeping the engine it builds and threading it
    into every write-capable service, closing the shared-session
    concurrency bug -- had no test of its own, only the underlying
    repository-level behavior (test_concurrent_writes.py, slim-domain) and
    a CHANGELOG entry. A future refactor could silently drop `engine=`
    from one of these constructor calls and nothing would catch it. Reads
    (element_svc, specification_svc) never take an engine at all -- see
    their own service classes -- so they're deliberately not checked here."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    Base.metadata.create_all(create_engine(db_url))

    services = build_services(db_url)

    engine = services.customer_svc._repo._engine
    assert engine is not None
    assert services.chemical_svc._repo._engine is engine
    assert services.analysis_svc._repo._engine is engine
    assert services.report_folder_svc._repo._engine is engine
    assert services.report_log_svc._repo._engine is engine
