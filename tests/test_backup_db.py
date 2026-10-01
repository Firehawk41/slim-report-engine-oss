"""Covers the 2026-09-24 ops-review fixes to scripts/backup_db.py: a
suspiciously small (but exit-0) pg_dump output must not overwrite a good
existing backup, a genuinely failed pg_dump must not leave a stray temp
file lying around either, and a locked file during pruning must not abort
pruning the rest. dump_path/tmp_path is real filesystem I/O (tmp_path
fixture), but pg_dump itself is faked via monkeypatching subprocess.run --
there is no real Postgres in this test environment, and there doesn't need
to be: this is testing backup_db.py's own logic, not pg_dump.
"""

import subprocess
from types import SimpleNamespace

from scripts import backup_db


def _fake_run_writing(content: bytes, returncode: int = 0):
    """Build a subprocess.run stand-in that writes `content` to the -f path
    it's given (mimicking what a real pg_dump does) and returns `returncode`."""

    def _run(cmd, env=None, capture_output=True, text=True):
        out_path = cmd[cmd.index("-f") + 1]
        with open(out_path, "wb") as f:
            f.write(content)
        return SimpleNamespace(returncode=returncode, stdout="", stderr="simulated failure")

    return _run


def test_successful_dump_is_renamed_into_place(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run_writing(b"-- fake pg_dump\n" * 100))

    rc = backup_db.main(["--db", "postgresql://u:p@localhost/db", "--out-dir", str(tmp_path)])

    assert rc == 0
    dumps = list(tmp_path.glob("report_engine_*.sql"))
    assert len(dumps) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_suspiciously_small_dump_does_not_overwrite_existing_backup(tmp_path, monkeypatch):
    # Same filename backup_db.py would generate for today -- simulates a
    # manual same-day retry landing on top of an already-good backup.
    import datetime as real_datetime

    today = real_datetime.datetime.now().strftime("%Y-%m-%d")
    existing = tmp_path / f"report_engine_{today}.sql"
    existing.write_bytes(b"-- a real prior backup\n" * 100)

    monkeypatch.setattr(subprocess, "run", _fake_run_writing(b"truncated"))

    rc = backup_db.main(["--db", "postgresql://u:p@localhost/db", "--out-dir", str(tmp_path)])

    assert rc == 1
    assert existing.read_bytes() == b"-- a real prior backup\n" * 100
    assert not list(tmp_path.glob("*.tmp"))


def test_pg_dump_failure_leaves_no_stray_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run_writing(b"partial", returncode=1))

    rc = backup_db.main(["--db", "postgresql://u:p@localhost/db", "--out-dir", str(tmp_path)])

    assert rc == 1
    assert not list(tmp_path.glob("*"))


def test_prune_skips_a_locked_file_but_removes_the_rest(tmp_path, monkeypatch):
    import datetime as real_datetime

    old_time = (real_datetime.datetime.now() - real_datetime.timedelta(days=30)).timestamp()
    locked = tmp_path / "report_engine_2026-01-01.sql"
    removable = tmp_path / "report_engine_2026-01-02.sql"
    locked.write_bytes(b"x")
    removable.write_bytes(b"x")
    import os
    os.utime(locked, (old_time, old_time))
    os.utime(removable, (old_time, old_time))

    real_unlink = type(locked).unlink

    def _unlink(self, *a, **kw):
        if self == locked:
            raise PermissionError("simulated lock")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(type(locked), "unlink", _unlink)

    removed = backup_db._prune_old_dumps(tmp_path, keep_days=7)

    assert removed == [removable]
    assert locked.exists()
    assert not removable.exists()
