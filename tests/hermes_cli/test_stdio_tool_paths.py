"""Native Windows startup discovers Loki's tools without adopting Hermes tools."""

import os

import pytest

from hermes_cli.stdio import _augment_path_with_known_tools


@pytest.mark.platforms("windows")
def test_owned_tools_are_added_and_foreign_tools_are_ignored(tmp_path, monkeypatch):
    local = tmp_path / "AppData"
    owned = tmp_path / "dedicated-loki"
    relative = ("git/cmd", "git/bin", "git/usr/bin", "hermes-agent/venv/Scripts")
    for root in (owned, local / "hermes"):
        for leaf in relative:
            (root / leaf).mkdir(parents=True)
    shared = local / "Microsoft" / "WinGet" / "Links"
    shared.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("HERMES_HOME", str(owned))
    monkeypatch.setenv("PATH", "C:\\existing")

    _augment_path_with_known_tools()
    entries = os.environ["PATH"].split(os.pathsep)
    assert entries == [*(str(owned / leaf) for leaf in relative), str(shared), "C:\\existing"]
    assert all(str(local / "hermes").lower() not in entry.lower() for entry in entries)
    _augment_path_with_known_tools()
    assert os.environ["PATH"].split(os.pathsep) == entries


@pytest.mark.platforms("windows")
def test_named_profile_uses_its_own_root_tools(tmp_path, monkeypatch):
    root = tmp_path / ".loki"
    profile = root / "profiles" / "work"
    profile.mkdir(parents=True)
    (root / "config.yaml").write_text("", encoding="utf-8")
    tools = root / "git" / "bin"
    tools.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setenv("PATH", "C:\\existing")
    _augment_path_with_known_tools()
    assert os.environ["PATH"].split(os.pathsep) == [str(tools), "C:\\existing"]


@pytest.mark.platforms("posix")
def test_posix_startup_does_not_modify_path(monkeypatch):
    monkeypatch.setenv("PATH", "/existing")
    _augment_path_with_known_tools()
    assert os.environ["PATH"] == "/existing"
