"""The optional memory provider's owned isolation patch survives remote catalog refreshes."""
from __future__ import annotations

import json

import pytest

import hermes_yaml as yaml
from hermes_cli import plugin_catalog as catalog

OWN_SHA = "a" * 40
REMOTE_SHA = "b" * 40
OWN_REPO = "https://github.com/ObliviousOdin/loki"


def entry(name="honcho", **overrides):
    return {
        "name": name, "repo": OWN_REPO, "sha": OWN_SHA,
        "subdir": "optional-plugins/honcho", "version": "1.0.0-loki.1",
        "description": "Owned memory provider", "maintainer": "ObliviousOdin",
        "tier": "community", "capabilities": {"provides_hooks": ["on_session_end"]},
        **overrides,
    }


@pytest.fixture
def tree(tmp_path, monkeypatch):
    directory = tmp_path / "catalog"
    directory.mkdir()
    (directory / "honcho.yaml").write_text(yaml.safe_dump(entry()))
    monkeypatch.setattr(catalog, "get_catalog_dir", lambda: directory)
    monkeypatch.setattr(catalog, "in_tree_catalog_time", lambda: 0.0)
    return directory


def document(*entries, removed=()):
    return {"entries": list(entries), "generated_at": "2099-01-01T00:00:00Z", "removed": list(removed)}


@pytest.mark.parametrize("include_honcho", [False, True])
def test_newer_remote_cannot_replace_or_omit_owned_memory_provider(tree, monkeypatch, include_honcho):
    remote = [entry("other", sha=REMOTE_SHA, version="9.0.0")]
    if include_honcho:
        remote.append(entry(repo="https://github.com/plastic-labs/honcho", sha=REMOTE_SHA,
                            subdir="hermes-plugin-honcho", version="99.0.0", tier="official"))
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: document(*remote))
    resolved = {item.name: item for item in catalog.load_catalog_live()}
    assert set(resolved) == {"honcho", "other"}
    assert resolved["other"].sha == REMOTE_SHA
    assert resolved["honcho"].to_dict() == catalog.get_catalog_entry("honcho").to_dict()
    assert resolved["honcho"].sha == OWN_SHA
    assert resolved["honcho"].repo == OWN_REPO
    assert resolved["honcho"].tier == "community"


def test_fresh_remote_cache_cannot_repin_owned_provider(tree, tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps(document(entry(sha=REMOTE_SHA), entry("other", sha=REMOTE_SHA))))
    monkeypatch.setattr(catalog, "_live_cache_path", lambda: cache)
    import httpx

    def no_network(*_args, **_kwargs):
        pytest.fail("A fresh cache must not trigger network access")

    monkeypatch.setattr(httpx, "get", no_network)
    resolved = {item.name: item for item in catalog.load_catalog_live()}
    assert resolved["honcho"].sha == OWN_SHA
    assert resolved["other"].sha == REMOTE_SHA


@pytest.mark.parametrize("bad_tree", [
    None, "malformed-yaml", {"sha": "not-a-pin"},
    {"repo": "https://github.com/plastic-labs/honcho"},
    {"repo": "https://github.com/ObliviousOdin/loki-other"},
    {"repo": "https://token@github.com/ObliviousOdin/loki"},
    {"subdir": "hermes-plugin-honcho"},
])
def test_missing_invalid_or_foreign_tree_pin_never_adopts_remote_honcho(tree, monkeypatch, bad_tree):
    path = tree / "honcho.yaml"
    if bad_tree is None:
        path.unlink()
    elif bad_tree == "malformed-yaml":
        path.write_text("{ invalid: [")
    else:
        path.write_text(yaml.safe_dump(entry(**bad_tree)))
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: document(entry(sha=REMOTE_SHA), entry("other")))
    assert catalog.get_catalog_entry("honcho") is None
    assert [item.name for item in catalog.load_catalog_live()] == ["other"]


def test_offline_fallback_and_remote_kill_list_stay_effective(tree, monkeypatch):
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: None)
    assert catalog.get_live_catalog_entry("honcho").sha == OWN_SHA
    (tree / "removed.yaml").write_text(yaml.safe_dump({"removed": [{"name": "tree-blocked", "reason": "local"}]}))
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: document(
        entry(sha=REMOTE_SHA), removed=[{"name": "honcho", "reason": "remote security removal"}]))
    assert catalog.find_removed("tree-blocked").reason == "local"
    assert catalog.find_removed("honcho").reason == "remote security removal"
    assert catalog.get_live_catalog_entry("honcho").sha == OWN_SHA


def test_remote_duplicates_cannot_duplicate_or_change_owned_provider(tree, monkeypatch):
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: document(entry(sha=REMOTE_SHA), entry(sha="c" * 40)))
    resolved = catalog.load_catalog_live()
    assert len(resolved) == 1
    assert resolved[0].sha == OWN_SHA
