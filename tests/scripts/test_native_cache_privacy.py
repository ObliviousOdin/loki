"""Distribution cache copies retain offline dependency inputs without machine/project state."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from scripts.bundles import native


@pytest.mark.parametrize("private", ["interpreter-v4/probe/hash.msgpack", "sdists-v9/editable/source/revision/metadata.msgpack"])
def test_staged_cache_never_copies_machine_or_editable_source_state(tmp_path, private):
    source = tmp_path / "shared build cache"
    leaked = source / private
    leaked.parent.mkdir(parents=True)
    leaked.write_bytes(b"private build host identity")
    wheel = source / "sdists-v9/pypi/pilk/revision/build/pilk-1.0-cp314-cp314-macosx_11_0_arm64.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(b"required built wheel input")
    destination = tmp_path / "payload/uv-cache"

    native.stage_uv_cache(source, destination)

    assert not (destination / private).exists()
    assert leaked.read_bytes() == b"private build host identity"
    assert (destination / wheel.relative_to(source)).read_bytes() == b"required built wheel input"
    assert wheel.read_bytes() == b"required built wheel input"


def test_native_cache_excludes_only_root_distribution_and_preserves_dependency_archives(tmp_path, monkeypatch):
    project = tmp_path / "source"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="loki-fixture"\nversion="1.0"\n')
    (project / "uv.lock").write_text('[[package]]\nname="loki-fixture"\nversion="1.0"\n'
                                   'source={editable="."}\n[[package]]\nname="pilk"\nversion="1.0"\n')
    cache = tmp_path / "shared-cache"
    root = cache / "archive-v0/root/loki_fixture-1.0.dist-info"
    root.mkdir(parents=True)
    (root / "direct_url.json").write_bytes(b"private editable source")
    (root.parent / "__editable___loki_fixture_finder.py").write_bytes(b"private editable mapping")
    dependency = cache / "archive-v0/dependency/pilk-1.0.dist-info"
    dependency.mkdir(parents=True)
    (dependency / "METADATA").write_bytes(b"Name: pilk\nVersion: 1.0\n")
    (dependency.parent / "_pilk.so").write_bytes(b"dependency binary")
    before = {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
    shipped = tmp_path / "payload/uv-cache"

    copyfile = shutil.copyfile

    def copy_dependency(source, destination, **kwargs):
        assert not Path(source).is_relative_to(root.parent), "root project bytes must never enter the payload copy"
        return copyfile(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "copyfile", copy_dependency)
        native.stage_uv_cache(cache, shipped, source_repo=project)
    native.prune_uv_cache_to_lock(shipped, project, exclude_project=True)

    assert not (shipped / "archive-v0/root").exists()
    assert (shipped / dependency.relative_to(cache) / "METADATA").read_bytes() == b"Name: pilk\nVersion: 1.0\n"
    assert (shipped / dependency.parent.relative_to(cache) / "_pilk.so").read_bytes() == b"dependency binary"
    assert before == {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
