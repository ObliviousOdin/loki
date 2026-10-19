"""Unit policy tests for Linux/root PATH repair; no native Linux qualification."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hermes_cli import update_cmd, update_cmd_maint


def _policy(monkeypatch, tmp_path, *, owned: bool, resolves: bool = False):
    launcher = tmp_path / "bin" / ("loki" if owned else "hermes")
    launcher.parent.mkdir()
    launcher.write_text("synthetic launcher\n")
    home = tmp_path / "home"
    home.mkdir()
    for name in (".bashrc", ".bash_profile"):
        config = home / name
        config.write_text("# retained user settings\nalias custom='Hermes'\n")
        config.chmod(0o640)

    def paths(value):
        if str(value).startswith("/usr/local/bin/"):
            return launcher.parent / Path(value).name
        return Path(value)

    monkeypatch.setattr(update_cmd, "_m", lambda: SimpleNamespace(sys=SimpleNamespace(platform="linux")))
    monkeypatch.setattr(update_cmd_maint, "Path", paths)
    monkeypatch.setattr(update_cmd_maint.os, "geteuid", lambda: 0)
    monkeypatch.setenv("HOME", str(home))
    probe = Mock(return_value=SimpleNamespace(returncode=0 if resolves else 1))
    monkeypatch.setattr(update_cmd_maint.subprocess, "run", probe)
    return home, probe


def test_foreign_launcher_alone_never_triggers_path_repair(monkeypatch, tmp_path):
    home, probe = _policy(monkeypatch, tmp_path, owned=False)
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    update_cmd_maint._ensure_fhs_path_guard()
    probe.assert_not_called()
    assert {p.name: p.read_bytes() for p in home.iterdir()} == before


@pytest.mark.parametrize("resolves", [False, True])
def test_owned_launcher_probes_loki_and_repairs_only_when_missing(monkeypatch, tmp_path, resolves):
    home, probe = _policy(monkeypatch, tmp_path, owned=True, resolves=resolves)
    before = {p.name: p.read_bytes() for p in home.iterdir()}
    update_cmd_maint._ensure_fhs_path_guard()
    probe.assert_called_once()
    assert probe.call_args.args[0][-1] == "command -v loki"
    assert probe.call_args.kwargs["timeout"] == 10
    for config in home.iterdir():
        assert config.stat().st_mode & 0o777 == 0o640
        assert config.read_bytes().startswith(before[config.name])
        if resolves:
            assert config.read_bytes() == before[config.name]
        else:
            assert "# Loki — ensure /usr/local/bin" in config.read_text()
            assert config.read_text().count('export PATH="/usr/local/bin:$PATH"') == 1
    first = {p.name: p.read_bytes() for p in home.iterdir()}
    update_cmd_maint._ensure_fhs_path_guard()
    assert {p.name: p.read_bytes() for p in home.iterdir()} == first
