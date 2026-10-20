"""Unsigned native delivery admits exact immutable bytes without signed-release exemptions."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import py_compile
import stat
import subprocess
import zipfile
from types import SimpleNamespace

import pytest

from scripts.loki import native_preview as preview
from scripts.loki.native_preview_scan import inspect_members, inspect_bytecode

COMMIT = "a" * 40


def test_draft_admission_and_native_assets_refuse_wrong_identity_or_overwrite(tmp_path):
    release = {"id": 7, "draft": True, "prerelease": True, "tag_name": "v0.1.0-alpha.9",
               "url": f"https://api.github.com/repos/{preview.REPOSITORY}/releases/7", "assets": []}
    tag = {"type": "commit", "sha": COMMIT}
    comparison = {"behind_by": 0, "status": "ahead", "base_commit": {"sha": COMMIT}, "merge_base_commit": {"sha": COMMIT}}
    preview.validate_draft(release, tag, comparison, release_id=7, commit=COMMIT, version="0.1.0-alpha.9")
    for key, value in [("draft", False), ("prerelease", False), ("tag_name", "foreign"), ("url", "https://api.github.com/repos/foreign/loki/releases/7")]:
        changed = {**release, key: value}
        with pytest.raises(ValueError):
            preview.validate_draft(changed, tag, comparison, release_id=7, commit=COMMIT, version="0.1.0-alpha.9")
    for changed in ({**tag, "sha": "b" * 40}, {**tag, "type": "tag"}):
        with pytest.raises(ValueError):
            preview.validate_draft(release, changed, comparison, release_id=7, commit=COMMIT, version="0.1.0-alpha.9")
    with pytest.raises(ValueError):
        preview.validate_draft(release, tag, {**comparison, "behind_by": 1}, release_id=7, commit=COMMIT, version="0.1.0-alpha.9")
    companions = {"assets": {f"source-{n}": {"size": 1, "sha256": "c" * 64} for n in range(9)}}
    release["assets"] = [{"id": n, "name": name, "size": value["size"], "digest": "sha256:" + value["sha256"]}
                         for n, (name, value) in enumerate(companions["assets"].items())]
    asset = tmp_path / "UNSIGNED-PREVIEW-Loki.zip"
    asset.write_bytes(b"native fixture")
    preview.validate_assets(release, companions, [asset])
    changed = deepcopy(release)
    changed["assets"][0]["digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="source companions"):
        preview.validate_assets(changed, companions, [asset])
    release["assets"].append({"name": asset.name})
    with pytest.raises(ValueError, match="overwrite"):
        preview.validate_assets(release, companions, [asset])
    with asset.open("wb") as stream:
        stream.truncate(preview.MAX_ASSET)
    with pytest.raises(ValueError, match="under 2 GiB"):
        preview.validate_assets({**release, "assets": release["assets"][:-1]}, companions, [asset])


def test_scanner_rejects_nested_wheel_paths_and_nonportable_nested_code(tmp_path):
    module = tmp_path / "module.py"
    module.write_text("def outer():\n    return lambda: 1\n", encoding="utf-8")
    cache = Path(importlib.util.cache_from_source(str(module)))
    py_compile.compile(str(module), dfile=str(module), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH, doraise=True)
    with pytest.raises(ValueError, match="nonportable"):
        inspect_bytecode(cache.read_bytes())
    py_compile.compile(str(module), dfile="/loki/app/module.py", invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH, doraise=True)
    inspect_bytecode(cache.read_bytes())
    def archive(content):
        wheel = io.BytesIO()
        with zipfile.ZipFile(wheel, "w") as zipped:
            zipped.writestr("package/metadata.json", content)
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as zipped:
            zipped.writestr("uv-cache/dependency.whl", wheel.getvalue())
        result.seek(0)
        return result
    with zipfile.ZipFile(archive(b"portable metadata")) as zipped:
        result = inspect_members(zipped, roots=[], patterns=[str(tmp_path).encode()], scratch=tmp_path)
    assert result["members"] == 2 and result["nested_wheels"] == 1
    with zipfile.ZipFile(archive(str(tmp_path).encode())) as zipped, pytest.raises(ValueError, match="Private build path"):
        inspect_members(zipped, roots=[], patterns=[str(tmp_path).encode()], scratch=tmp_path)


@pytest.mark.parametrize("target", ["..", "../outside"])
def test_scanner_refuses_symlinks_escaping_the_extraction_root(tmp_path, target):
    archive = tmp_path / "link.zip"
    member = zipfile.ZipInfo("outside")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(member, target)
    with zipfile.ZipFile(archive) as zipped, pytest.raises(ValueError, match="symlink escapes"):
        inspect_members(zipped, roots=[], patterns=[], scratch=tmp_path)


def test_exact_shallow_native_checkout_retains_version_and_snapshot_contract(tmp_path):
    from scripts.bundles.desktop_prepare import BuildRequest
    from scripts.bundles.payload import snapshot
    origin = tmp_path / "origin"
    origin.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=origin, text=True).strip()
    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (origin / "pyproject.toml").write_text('[project]\nname="obliviousodin-loki-agent"\nversion="0.1.0a9"\n', encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "source")
    (origin / "module.py").write_text("VALUE=1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "module")
    commit = git("rev-parse", "HEAD")
    source = tmp_path / "source"
    subprocess.run(["git", "clone", "--depth", "1", "--no-tags", origin.as_uri(), str(source)], check=True, capture_output=True)
    assert (source / ".git/shallow").is_file()
    request = BuildRequest.create(source, tag=None, commit=commit, variant="bundled", work=tmp_path / "work", cache=tmp_path / "cache", bundle_env={})
    assert request.version == "0.1.0-alpha.9" and request.commit == commit
    snapshot(source, commit, tmp_path / "snapshot")
    assert (tmp_path / "snapshot/module.py").read_text() == "VALUE=1\n"


def test_source_staging_only_adds_missing_exact_assets_and_never_replaces(tmp_path, monkeypatch):
    version = "0.1.0-alpha.9"
    pilk = {"source_asset": "pilk.tar.gz", "license_asset": "pilk-LICENSE.txt", "codec_notice_asset": "pilk-NOTICES.txt"}
    metadata = {"commit": COMMIT, "repository": preview.REPOSITORY, "kind": "source-preview",
                "version": version, "third_party_sources": [pilk]}
    files = [f"loki-{version}-source.tar.gz", "install.sh", "install.ps1", "install.cmd", *pilk.values()]
    for name in files:
        (tmp_path / name).write_bytes(b"exact source companion")
    (tmp_path / "LOKI-PREVIEW.json").write_text(json.dumps(metadata), encoding="utf-8")
    paths = [tmp_path / name for name in [*files, "LOKI-PREVIEW.json"]]
    (tmp_path / "SHA256SUMS").write_text("".join(f"{preview.digest(path)}  {path.name}\n" for path in paths), encoding="utf-8")
    sentinel = {"id": 99, "name": "existing-evidence.txt", "size": 7, "digest": "sha256:" + "c" * 64}
    release = {"assets": [sentinel.copy()]}
    posted = []
    monkeypatch.setattr(preview, "source_identity", lambda *_: version)
    monkeypatch.setattr(preview, "draft", lambda *_: deepcopy(release))

    def upload(endpoint, *, upload):
        assert endpoint.startswith(f"repos/{preview.REPOSITORY}/releases/7/assets?name=")
        posted.append(upload.name)
        row = {"id": len(posted), "name": upload.name, "state": "uploaded",
               "size": upload.stat().st_size, "digest": "sha256:" + preview.digest(upload)}
        release["assets"].append(row)
        return row

    monkeypatch.setattr(preview, "api", upload)
    args = SimpleNamespace(source=tmp_path, commit=COMMIT, output=tmp_path, draft_release_id=7)
    preview.stage_source(args)
    assert len(posted) == 9 and release["assets"][0] == sentinel
    preview.stage_source(args)
    assert len(posted) == 9 and release["assets"][0] == sentinel
    release["assets"][1]["digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="refusing overwrite"):
        preview.stage_source(args)
    assert len(posted) == 9 and release["assets"][0] == sentinel
