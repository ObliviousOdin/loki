"""Tests for hermes backup retention (--keep) and the session-store import round trip."""

from argparse import Namespace
import os
from pathlib import Path
import zipfile

import pytest

import hermes_cli.gateway_setup_service as service_setup
from tests.hermes_cli.test_backup import _make_hermes_tree


@pytest.fixture(autouse=True)
def _no_real_gateway_service(monkeypatch):
    """run_import() may start an existing gateway service post-restore; tests must
    never touch the host's systemd/launchd."""
    import hermes_cli.gateway as gateway_mod

    monkeypatch.setattr(service_setup, "ensure_gateway_service", lambda **kw: False)
    monkeypatch.setattr(gateway_mod, "_is_service_running", lambda: False)


@pytest.mark.parametrize("directory_output", [False, True])
def test_run_backup_prunes_older_default_named_zips_but_not_others(tmp_path, monkeypatch, capsys, directory_output):
    """Hourly `hermes backup` callers accumulated 150+ zips; --keep bounds the default-named
    ones and leaves custom-named or foreign zips alone (#81317)."""
    from argparse import Namespace
    from hermes_cli import backup as backup_mod

    home = tmp_path / ".loki"
    home.mkdir()
    (home / "config.yaml").write_text("model: x\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    output_dir = tmp_path / "archives" if directory_output else home / "backups"
    output_dir.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        (output_dir / f"loki-backup-2026-01-0{i + 1}-000000.zip").write_bytes(b"old")
    foreign = {
        "hermes-backup-2000-01-01-000000.zip": b"Hermes archive",
        "hermes-backup-2099-01-01-000000.zip": b"Newer Hermes archive",
        "fabric-backup-2000-01-01-000000.zip": b"Fabric archive",
        "my-archive.zip": b"mine",
    }
    for directory in (tmp_path, output_dir):
        for name, data in foreign.items():
            (directory / name).write_bytes(data)

    assert backup_mod.run_backup(Namespace(output=str(output_dir) if directory_output else None, keep=2)) is True

    for directory in (tmp_path, output_dir):
        for name, data in foreign.items():
            assert (directory / name).read_bytes() == data
    kept = sorted(p.name for p in output_dir.glob("loki-backup-*.zip"))
    assert len(kept) == 2 and kept[0] == "loki-backup-2026-01-04-000000.zip"
    with zipfile.ZipFile(output_dir / kept[-1]) as archive:
        assert "config.yaml" in archive.namelist()
        assert all("backups" not in Path(name).parts for name in archive.namelist())
    from hermes_cli.backup_restore import _restore_command
    assert f"Restore with: {_restore_command(output_dir / kept[-1], powershell=os.name == 'nt')}" in capsys.readouterr().out


def test_default_backup_is_owned_by_active_profile_and_excludes_all_backups(tmp_path, monkeypatch):
    from hermes_cli.backup import run_backup

    root = tmp_path / ".loki"
    profile = root / "profiles" / "work"
    profile.mkdir(parents=True)
    (root / "config.yaml").write_text("model: root-model\n")
    (profile / "config.yaml").write_text("model: work-model\n")
    for home in (root, profile):
        (home / "backups").mkdir()
        (home / "backups" / "keep-user-archive.zip").write_bytes(b"User archive")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(profile))

    assert run_backup(Namespace(output=None, keep=1)) is True

    archives = list((profile / "backups").glob("loki-backup-*.zip"))
    assert len(archives) == 1
    assert list((root / "backups").glob("loki-backup-*.zip")) == []
    assert list(tmp_path.glob("*-backup-*.zip")) == []
    with zipfile.ZipFile(archives[0]) as archive:
        assert "config.yaml" in archive.namelist()
        assert "profiles/work/config.yaml" in archive.namelist()
        assert all("backups" not in Path(name).parts for name in archive.namelist())
    for home in (root, profile):
        assert (home / "backups" / "keep-user-archive.zip").read_bytes() == b"User archive"


def test_explicit_legacy_hermes_archive_restores_into_loki_home(tmp_path, monkeypatch):
    from hermes_cli.backup import run_import

    target = tmp_path / ".loki"
    monkeypatch.setenv("HERMES_HOME", str(target))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    archive = tmp_path / "hermes-backup-2025-01-01-000000.zip"
    config = b"model: {provider: custom, default: legacy-model}\n"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(".hermes/config.yaml", config)
        handle.writestr(".hermes/notes.txt", "Preserve legacy backup compatibility.\n")
    original_archive = archive.read_bytes()

    assert run_import(Namespace(zipfile=str(archive), force=True)) is None

    assert (target / "config.yaml").read_bytes() == config
    assert (target / "notes.txt").read_text() == "Preserve legacy backup compatibility.\n"
    assert not (tmp_path / ".hermes").exists()
    assert archive.read_bytes() == original_archive


def test_import_restores_the_session_store_with_its_message_uids(tmp_path, monkeypatch):
    """A backup ships state.db as a SQLite snapshot and an import puts it back byte-for-byte: the durable
    message ids come back with the rows."""
    from hermes_state import SessionDB

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _make_hermes_tree(hermes_home)
    db = SessionDB(db_path=hermes_home / "state.db")
    try:
        db.create_session("s", "cli", model="m")
        db.append_message(session_id="s", role="user", content="q")
        db.append_message(session_id="s", role="assistant", content="a")
        uids = [m["message_uid"] for m in db.get_messages_as_conversation("s")]
    finally:
        db.close()
    assert len(uids) == 2 and all(len(u) == 32 for u in uids)

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from hermes_cli.backup import run_backup, run_import

    out_zip = tmp_path / "backup.zip"
    run_backup(Namespace(output=str(out_zip)))
    for name in ("state.db", "state.db-wal", "state.db-shm"):
        (hermes_home / name).unlink(missing_ok=True)
    assert run_import(Namespace(zipfile=str(out_zip), force=True)) is None

    restored = SessionDB(db_path=hermes_home / "state.db")
    try:
        assert [m["message_uid"] for m in restored.get_messages_as_conversation("s")] == uids
    finally:
        restored.close()
