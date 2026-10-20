"""Profile renames may migrate Loki Honcho blocks without adopting foreign hosts."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hermes_cli import profiles, profiles_honcho


@pytest.fixture
def honcho_paths(tmp_path, monkeypatch):
    user = tmp_path / "operator"
    root = user / ".loki"
    profile = root / "profiles" / "renamed"
    profile.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: user)
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setattr(profiles, "_get_default_hermes_home", lambda: root)
    return {"profile": profile / "honcho.json", "root": root / "honcho.json",
            "global": user / ".honcho" / "config.json"}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=3) + "\n", encoding="utf-8")
    return path.read_bytes()


@pytest.mark.parametrize("location", ["profile", "root", "global"])
def test_foreign_only_honcho_hosts_remain_byte_identical(honcho_paths, monkeypatch, location):
    path = honcho_paths[location]
    hosts = {name: {"workspace": name, "aiPeer": "retained peer"} for name in
             ("hermes_old", "hermes.old", "fabric_old", "fabric.old")}
    before = _write(path, {"defaultHost": "hermes_old", "hosts": hosts})
    monkeypatch.setattr(profiles_honcho, "_atomic_write_json", lambda *_a: pytest.fail("foreign config was rewritten"))

    profiles_honcho.migrate_honcho_profile_host("old", "renamed", honcho_paths["profile"].parent)

    assert path.read_bytes() == before


@pytest.mark.parametrize("old_host", ["loki_old", "loki.old"])
def test_owned_honcho_host_rename_preserves_explicit_backend_and_foreign_blocks(honcho_paths, old_host):
    path = honcho_paths["root"]
    foreign = {"hermes_old": {"workspace": "Hermes workspace"}, "fabric_old": {"workspace": "Fabric workspace"}}
    own = {"workspace": "my configured workspace", "aiPeer": "Hermes user peer", "enabled": True,
           "peerName": "configured-user", "saveMessages": True}
    _write(path, {"hosts": {**deepcopy(foreign), old_host: deepcopy(own)}})

    profiles_honcho.migrate_honcho_profile_host("old", "renamed", honcho_paths["profile"].parent)

    hosts = json.loads(path.read_text(encoding="utf-8"))["hosts"]
    assert hosts == {**foreign, "loki_renamed": own}


def test_owned_honcho_host_without_ai_peer_keeps_original_profile_identity(honcho_paths):
    path = honcho_paths["root"]
    _write(path, {"hosts": {"loki_old": {"workspace": "hermes", "saveMessages": True}}})

    profiles_honcho.migrate_honcho_profile_host("old", "renamed", honcho_paths["profile"].parent)

    assert json.loads(path.read_text(encoding="utf-8"))["hosts"] == {
        "loki_renamed": {"workspace": "hermes", "saveMessages": True, "aiPeer": "loki_old"}}


def test_conflicting_owned_honcho_host_is_not_overwritten(honcho_paths, capsys):
    path = honcho_paths["root"]
    before = _write(path, {"hosts": {"loki_old": {"workspace": "original"},
                                    "loki_renamed": {"workspace": "existing"},
                                    "hermes_old": {"workspace": "foreign"}}})

    profiles_honcho.migrate_honcho_profile_host("old", "renamed", honcho_paths["profile"].parent)

    assert path.read_bytes() == before
    assert "loki_renamed already exists" in capsys.readouterr().out


def test_global_honcho_is_not_read_even_when_it_contains_loki_hosts(honcho_paths, monkeypatch):
    path = honcho_paths["global"]
    before = _write(path, {"hosts": {"loki_old": {"workspace": "explicit foreign file"}}})
    original = Path.read_text

    def guarded(candidate, *args, **kwargs):
        if candidate == path:
            pytest.fail("profile rename must not read shared global Honcho state")
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    profiles_honcho.migrate_honcho_profile_host("old", "renamed", honcho_paths["profile"].parent)
    assert path.read_bytes() == before
