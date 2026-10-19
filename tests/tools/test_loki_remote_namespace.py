"""Exercise remote sync's real shell/tar boundary in a disposable local transport.

This proves the filesystem protocol, not an authenticated SSH server or cloud service.
"""
import subprocess
import tarfile
from unittest.mock import Mock

import pytest

from tools.environments.ssh import SSHEnvironment


@pytest.fixture
def remote(tmp_path):
    home = tmp_path.resolve() / "remote home"
    foreign = home / ".hermes" / "skills" / "foreign.txt"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"preserve upstream state")
    env = SSHEnvironment.__new__(SSHEnvironment)
    env._remote_home = str(home)
    env.host = "disposable-local-transport"
    env._build_ssh_command = lambda: ["bash", "-c"]
    env._run_ssh = lambda command, timeout: subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, timeout=timeout, check=False)
    return env, home, foreign


@pytest.mark.platforms("linux")
def test_sync_upload_download_never_includes_foreign_hermes_state(remote, tmp_path):
    # The inherited SSH transport requires GNU tar's --no-overwrite-dir on
    # its remote host. This local transport exercises that Linux contract.
    env, home, foreign = remote
    original = foreign.stat()
    env._ensure_remote_dirs()
    assert (home / ".loki" / "skills").is_dir()
    source = tmp_path / "own.txt"
    source.write_bytes(b"Loki-owned skill")
    destination = home / ".loki" / "skills" / "own.txt"
    env._ssh_bulk_upload([(str(source), str(destination))])
    assert destination.read_bytes() == b"Loki-owned skill"
    archive = tmp_path / "download.tar"
    env._ssh_bulk_download(archive)
    with tarfile.open(archive) as downloaded:
        members = downloaded.getnames()
        assert all("/.hermes" not in name for name in members)
        own = next(item for item in downloaded.getmembers() if item.name.endswith("/.loki/skills/own.txt"))
        assert downloaded.extractfile(own).read() == b"Loki-owned skill"
    assert foreign.read_bytes() == b"preserve upstream state"
    assert foreign.stat().st_mtime_ns == original.st_mtime_ns


@pytest.mark.platforms("posix")
def test_stale_foreign_upload_path_is_refused_before_remote_mkdir(remote, tmp_path):
    env, home, foreign = remote
    source = tmp_path / "own.txt"
    source.write_bytes(b"own")
    destination = home / ".hermes" / "new directory" / "own.txt"
    with pytest.raises(RuntimeError, match="escapes sync base"):
        env._ssh_bulk_upload([(str(source), str(destination))])
    assert not destination.parent.exists()
    assert foreign.read_bytes() == b"preserve upstream state"


def test_local_master_cleanup_never_exits_or_unlinks_foreign_hermes_socket(tmp_path, monkeypatch):
    from tools.environments import ssh
    monkeypatch.setattr(ssh.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(ssh, "_ensure_ssh_available", lambda: None)
    monkeypatch.setattr(SSHEnvironment, "_establish_connection", lambda self: None)
    env = SSHEnvironment("fixture-host", "fixture-user", probe_only=True)
    foreign = tmp_path / "hermes-ssh" / env.control_socket.name
    foreign.parent.mkdir()
    foreign.write_text("foreign master", encoding="utf-8")
    env.control_socket.write_text("owned master", encoding="utf-8")
    run = Mock()
    monkeypatch.setattr(ssh.subprocess, "run", run)
    env.cleanup()
    assert not env.control_socket.exists()
    assert env.control_dir.name == "loki-ssh"
    assert foreign.read_text(encoding="utf-8") == "foreign master"
    assert run.call_count == 1
    assert f"ControlPath={env.control_socket}" in run.call_args.args[0]
    assert str(foreign) not in " ".join(run.call_args.args[0])


@pytest.mark.platforms("posix")
def test_ssh_control_root_cannot_link_to_foreign_master_directory(tmp_path, monkeypatch):
    from tools.environments import ssh
    from tools.environments.base import EnvironmentConnectionError
    foreign = tmp_path / "hermes-ssh"
    foreign.mkdir()
    sentinel = foreign / "master.sock"
    sentinel.write_text("foreign", encoding="utf-8")
    (tmp_path / "loki-ssh").symlink_to(foreign, target_is_directory=True)
    monkeypatch.setattr(ssh.tempfile, "gettempdir", lambda: str(tmp_path))
    connect = Mock()
    monkeypatch.setattr(SSHEnvironment, "_establish_connection", connect)
    with pytest.raises(EnvironmentConnectionError, match="Refusing unowned"):
        SSHEnvironment("fixture-host", "fixture-user", probe_only=True)
    connect.assert_not_called()
    assert sentinel.read_text(encoding="utf-8") == "foreign"


def test_shared_hpc_scratch_uses_a_loki_leaf(tmp_path, monkeypatch):
    from pathlib import Path
    from tools.environments import singularity
    shared = tmp_path / "scratch"
    foreign = shared / "fixture-user" / "hermes-agent" / "preserve.txt"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("foreign", encoding="utf-8")
    real_path = Path
    monkeypatch.setattr(singularity, "Path", lambda value: shared if value == "/scratch" else real_path(value))
    monkeypatch.setenv("USER", "fixture-user")
    monkeypatch.delenv("TERMINAL_SCRATCH_DIR", raising=False)
    own = singularity._get_scratch_dir()
    assert own == shared / "fixture-user" / "loki-agent"
    assert own.is_dir()
    assert foreign.read_text(encoding="utf-8") == "foreign"
