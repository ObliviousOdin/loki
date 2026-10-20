"""Admit and publish the actual optional provider through the normal offline installer."""
from pathlib import Path
import shutil

from tests.hermes_cli.plugin_worker_support import (
    git,
    isolated_python as isolated_python,  # noqa: PLC0414 -- exports the fixture under its canonical name
    plugin_world as plugin_world,  # noqa: PLC0414 -- exports the fixture under its canonical name
)


def test_actual_honcho_tree_uses_normal_exact_pin_scan_and_publication(tmp_path, monkeypatch, plugin_world):
    from hermes_cli import plugins_cmd, plugins_cmd_catalog, plugin_catalog
    from pm.plugin_declarations import read_python_declaration

    # Existing offline PM fixture retains the actual resolver/worker/atomic publication.
    # No plugin is active; dependency activation and real SDK access are separate operations.
    (plugin_world.home / "config.yaml").unlink()
    source = Path(__file__).resolve().parents[2] / "optional-plugins/honcho"
    repo = tmp_path / "own-source"
    shutil.copytree(source, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "reviewed fixture source")
    pin = git(repo, "rev-parse", "HEAD")
    entry = plugin_catalog.PluginCatalogEntry(
        name="honcho", repo=repo.as_uri(), sha=pin, description="Loki compatibility provider", maintainer="fixture")
    monkeypatch.setattr(plugin_catalog, "fetch_live_catalog", lambda **_: None)
    monkeypatch.setattr(plugin_catalog, "load_removed_list", lambda *_: [])
    target, manifest, name = plugins_cmd_catalog.install_catalog_entry(entry, force=False)
    assert name == manifest["name"] == "honcho"
    assert manifest["version"] == "0.1.0a1"
    assert (target / "LICENSE").read_bytes() == (source / "LICENSE").read_bytes()
    assert (target / "client.py").read_bytes() == (source / "client.py").read_bytes()
    record = plugins_cmd._read_install_metadata()[name]
    assert record["revision"] == pin and record["source"] == repo.as_uri()
    assert record["pinned"] is True and record["catalog"]["pin"] == pin
    assert plugins_cmd_catalog.read_catalog_sidecar(target)["sha"] == pin
    requirements = read_python_declaration(target).install_requirements
    assert "honcho-ai>=2.2.0,<3" in requirements and "httpx>=0.27,<1" in requirements
