"""Smart-home catalog discovery retains the product's reviewed scope/confirmation implementation."""

import pytest
import hermes_yaml as yaml

from hermes_cli import plugin_catalog as catalog


@pytest.mark.parametrize("local_valid", [True, False])
def test_remote_catalog_cannot_replace_smart_home_scope(tmp_path, monkeypatch, local_valid):
    tree = tmp_path / "catalog"
    tree.mkdir()
    owned = {"name": "smart-home", "repo": "https://github.com/ObliviousOdin/loki", "sha": "a" * 40,
             "subdir": "optional-plugins/smart-home", "description": "Scoped lights and switches",
             "maintainer": "ObliviousOdin", "tier": "community"}
    if local_valid:
        (tree / "smart-home.yaml").write_text(yaml.safe_dump(owned), encoding="utf-8")
    remote = {**owned, "repo": "https://github.com/foreign/unrestricted", "sha": "b" * 40}
    monkeypatch.setattr(catalog, "get_catalog_dir", lambda: tree)
    monkeypatch.setattr(catalog, "in_tree_catalog_time", lambda: 0.0)
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: {
        "entries": [remote], "generated_at": "2099-01-01T00:00:00Z", "removed": []})
    result = catalog.get_live_catalog_entry("smart-home")
    if local_valid:
        assert result.sha == owned["sha"] and result.repo == owned["repo"]
    else:
        assert result is None
