"""Nightly Postgres backup: pg_dump to a timestamped file, pruning old dumps.

Usage: python scripts/backup_db.py [--db DB_URL] [--out-dir DIR] [--keep-days N]

Reuses the same DB_URL precedence as every other script in this codebase
(--db flag > .env's DB_URL > sqlite default) via
infrastructure.database.make_engine(), rather than duplicating credential
parsing in a separate script. Only meaningful against a postgresql
DB_URL -- there's nothing to pg_dump for the sqlite default.

Intended to run nightly via a per-user Windows Scheduled Task (no
elevation needed), early enough to finish before the machine's own
general nightly backup (Iperius) runs -- the dump file then gets swept up
by that backup like any other file, no database-aware backup tooling
required from it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from infrastructure.database import make_engine

_DEFAULT_OUT_DIR = Path(r"C:\Backups\examplelab-db")
_DEFAULT_KEEP_DAYS = 7
# Confirmed real path on LAB-SERVER (native postgresql-x64-16 service) --
# override with --pg-dump if pg_dump.exe lives somewhere else.
_PG_DUMP_EXE = r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
# Even a dump of a near-empty database is always at least a few hundred
# bytes of header comments (`-- PostgreSQL database dump`, etc.) -- a
# file smaller than this means pg_dump exited 0 but wrote something
# truncated/broken (e.g. the connection dropped mid-dump), not a real
# backup, and must not be trusted or kept.
_MIN_DUMP_BYTES = 1024


def _prune_old_dumps(out_dir: Path, keep_days: int) -> list[Path]:
    """Delete dumps older than keep_days. Local retention only -- Iperius's
    own nightly backup covers longer-term retention (see module docstring).
    A single locked/in-use file (e.g. Iperius or antivirus scanning it at
    that exact moment) must not abort pruning of the rest -- logged and
    skipped instead."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = []
    for f in out_dir.glob("report_engine_*.sql"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            try:
                f.unlink()
                removed.append(f)
            except OSError as e:
                print(f"Could not prune {f}: {e}", file=sys.stderr)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=str, default=None, help="DB_URL override")
    parser.add_argument(
        "--out-dir", type=Path, default=_DEFAULT_OUT_DIR, help="backup destination folder"
    )
    parser.add_argument(
        "--keep-days", type=int, default=_DEFAULT_KEEP_DAYS,
        help="delete local dumps older than this many days",
    )
    parser.add_argument("--pg-dump", type=str, default=_PG_DUMP_EXE, help="path to pg_dump.exe")
    args = parser.parse_args(argv)

    engine = make_engine(args.db)
    url = engine.url
    if url.get_backend_name() != "postgresql":
        print(f"DB_URL is not postgresql ({url.get_backend_name()}) -- nothing to pg_dump.", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    dump_path = args.out_dir / f"report_engine_{timestamp}.sql"
    # Dump to a temp file and only rename it into place once it's confirmed
    # good -- running this twice in one day (a manual retry) must not let a
    # failed second attempt overwrite a good first backup with a truncated
    # one at the same final path.
    tmp_path = dump_path.with_name(dump_path.name + ".tmp")

    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password  # subprocess-only -- never written to disk

    cmd = [
        args.pg_dump,
        "-h", url.host or "localhost",
        "-p", str(url.port or 5432),
        "-U", url.username,
        "-f", str(tmp_path),
        url.database,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pg_dump failed:\n{result.stderr}", file=sys.stderr)
        tmp_path.unlink(missing_ok=True)
        return 1

    size = tmp_path.stat().st_size
    if size < _MIN_DUMP_BYTES:
        print(
            f"pg_dump exited 0 but wrote only {size} bytes -- treating as a "
            f"failed backup, not overwriting any existing {dump_path.name}.",
            file=sys.stderr,
        )
        tmp_path.unlink(missing_ok=True)
        return 1

    tmp_path.replace(dump_path)
    print(f"Backup written: {dump_path} ({size:,} bytes)")

    for f in _prune_old_dumps(args.out_dir, args.keep_days):
        print(f"Pruned old dump: {f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
