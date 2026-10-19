"""Browser cleanup is confined to its owned temporary root."""
import os
import stat
import socket
import uuid
from pathlib import Path

import pytest


def _isolate_root(monkeypatch, tmp_path):
    import hermes_constants
    monkeypatch.setattr(hermes_constants, "socket_safe_tmpdir", lambda: str(tmp_path))
    monkeypatch.setattr(hermes_constants, "SOCKET_TMPDIR_MAX_LEN", 4096)


def test_reaper_preserves_foreign_sessions_outside_the_owned_root(tmp_path, monkeypatch):
    from tools import browser_tool as browser
    from tools import browser_tool_lifecycle as lifecycle
    _isolate_root(monkeypatch, tmp_path)
    foreign = tmp_path / "agent-browser-h_foreign"
    foreign.mkdir()
    sentinel = foreign / "preserve.txt"
    sentinel.write_text("upstream", encoding="utf-8")
    owned = Path(browser._socket_safe_tmpdir())
    own_stale = owned / "agent-browser-h_stale"
    own_stale.mkdir()
    monkeypatch.setattr(lifecycle, "_socket_dir_idle_seconds", lambda _: 10_000)
    lifecycle._reap_orphaned_browser_sessions()
    assert sentinel.read_text(encoding="utf-8") == "upstream"
    assert not own_stale.exists()
    assert owned.parent == tmp_path
    assert owned.name.startswith("loki-browser")
    if os.name != "nt":
        assert stat.S_IMODE(owned.stat().st_mode) == 0o700


@pytest.mark.platforms("posix")
def test_socket_root_refuses_a_symlink_to_foreign_state(tmp_path, monkeypatch):
    from tools import browser_tool as browser
    _isolate_root(monkeypatch, tmp_path)
    foreign = tmp_path / "foreign-hermes"
    foreign.mkdir()
    sentinel = foreign / "preserve.txt"
    sentinel.write_text("upstream", encoding="utf-8")
    (tmp_path / f"loki-browser-{os.getuid()}").symlink_to(foreign, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Refusing unowned"):
        browser._socket_safe_tmpdir()
    assert sentinel.read_text(encoding="utf-8") == "upstream"
    assert list(foreign.iterdir()) == [sentinel]


@pytest.mark.platforms("posix")
def test_deep_tmpdir_falls_back_to_a_short_owned_root_that_binds_a_socket(tmp_path, monkeypatch):
    import hermes_constants
    from tools import browser_tool as browser
    monkeypatch.setattr(hermes_constants, "socket_safe_tmpdir", lambda: str(tmp_path / ("deep" * 20)))
    root = Path(browser._socket_safe_tmpdir())
    assert len(str(root)) <= hermes_constants.SOCKET_TMPDIR_MAX_LEN
    assert root.name.startswith("loki-browser-")
    endpoint = root / ("test-" + uuid.uuid4().hex + ".sock")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(endpoint))
    finally:
        endpoint.unlink(missing_ok=True)
