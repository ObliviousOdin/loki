"""Published unsigned previews retain exact source, wire bytes and notice provenance."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile

import pytest

from scripts.loki import native_preview as preview
from scripts.loki import native_public_acceptance as public
from scripts.loki import public_source_acceptance as source_public

COMMIT = "a" * 40
VERSION = "0.1.0-alpha.9"


def test_published_source_and_native_companions_admit_only_exact_public_bytes(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "docs/loki").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nname="obliviousodin-loki-agent"\nversion="0.1.0a9"\n', encoding="utf-8")
    (source / "docs/loki/UPSTREAM.json").write_text(json.dumps({"commit": "b" * 40}), encoding="utf-8")
    pilk = {"source_asset": "pilk.tar.gz", "license_asset": "pilk-LICENSE.txt", "codec_notice_asset": "pilk-NOTICES.txt"}
    metadata = {"product": "Loki", "version": VERSION, "commit": COMMIT, "repository": preview.REPOSITORY,
                "kind": "source-preview", "signed": False, "upstream_commit": "b" * 40, "third_party_sources": [pilk]}
    files = {name: b"source companion" for name in [f"loki-{VERSION}-source.tar.gz", "install.sh", "install.ps1", "install.cmd", *pilk.values()]}
    files["LOKI-PREVIEW.json"] = json.dumps(metadata).encode()
    def hashed(value):
        import hashlib
        return hashlib.sha256(value).hexdigest()
    files["SHA256SUMS"] = "".join(f"{hashed(value)}  {name}\n" for name, value in files.items()).encode()
    files["UNSIGNED-PREVIEW-Loki.zip"] = b"unchanged native archive"
    files["UNSIGNED-PREVIEW-Loki.zip.blockmap"] = b"blockmap"
    proof = {"commit": COMMIT, "version": VERSION, "architecture": "arm64", "signed": False,
             "installed_cli_and_loopback_mock": "passed", "privacy": {"status": "passed"},
             "native_zip_sha256": hashed(files["UNSIGNED-PREVIEW-Loki.zip"]), "notices": {"npm/react/LICENSE": "c" * 64}}
    files["NATIVE-PREVIEW.json"] = json.dumps(proof).encode()
    native_names = ["UNSIGNED-PREVIEW-Loki.zip", "UNSIGNED-PREVIEW-Loki.zip.blockmap", "NATIVE-PREVIEW.json"]
    files["NATIVE-SHA256SUMS"] = "".join(f"{hashed(files[name])}  {name}\n" for name in native_names).encode()
    base = f"https://github.com/{preview.REPOSITORY}/releases/download/v{VERSION}/"
    release = {"id": 7, "url": public.API + "/releases/7", "tag_name": "v" + VERSION, "draft": False, "prerelease": True,
               "assets": [{"id": index, "name": name, "size": len(value), "digest": "sha256:" + hashed(value),
                           "browser_download_url": base + name} for index, (name, value) in enumerate(files.items())]}
    requests = []
    def fetch(url, destination, *, max_bytes=8 * 1024 ** 2):
        requests.append(url)
        if url == public.API + "/releases/7":
            value = json.dumps(release).encode()
        elif "/git/ref/tags/" in url:
            value = json.dumps({"object": {"type": "commit", "sha": COMMIT}}).encode()
        elif "/compare/" in url:
            value = json.dumps({"status": "ahead", "behind_by": 0, "base_commit": {"sha": COMMIT}, "merge_base_commit": {"sha": COMMIT}}).encode()
        else:
            assert url.startswith(base)
            value = files[url.removeprefix(base)]
        assert len(value) <= max_bytes
        with destination.open("xb") as stream:
            stream.write(value)
    monkeypatch.setattr(public, "fetch", fetch)
    output = tmp_path / "output"
    output.mkdir()
    admitted = public.public_release(output, release_id=7, commit=COMMIT, version=VERSION)
    companions = public.acquire_source(admitted, output / "source-assets", source=source, commit=COMMIT, version=VERSION)
    assert len(companions["assets"]) == 9
    archive, observed = public.acquire_native(admitted, output / "native-assets", commit=COMMIT, version=VERSION, expected_proof=hashed(files["NATIVE-PREVIEW.json"]))
    assert archive.read_bytes() == files[archive.name] and observed == proof
    assert len([url for url in requests if url.startswith(base)]) == 13
    for key, value in [("digest", None), ("size", True), ("browser_download_url", "https://foreign.invalid/archive")]:
        changed = deepcopy(admitted)
        changed["assets"][0][key] = value
        count = len(requests)
        with pytest.raises(ValueError, match="mandatory API"):
            public.download_asset(changed, changed["assets"][0]["name"], output)
        assert len(requests) == count
    with pytest.raises(ValueError, match="basename|checksum"):
        public.download_asset(admitted, "../outside", output)
    files["UNSIGNED-PREVIEW-Loki.zip"] = b"changed native archive!!"
    altered = tmp_path / "altered"
    altered.mkdir()
    with pytest.raises(ValueError, match="release API"):
        public.download_asset(admitted, "UNSIGNED-PREVIEW-Loki.zip", altered)
    release["draft"] = True
    refused = tmp_path / "refused"
    refused.mkdir()
    with pytest.raises(ValueError, match="published owned"):
        public.public_release(refused, release_id=7, commit=COMMIT, version=VERSION)


def test_builder_notice_map_binds_all_npm_bytes_and_published_copy_needs_no_builder(tmp_path):
    source, resources = tmp_path / "source", tmp_path / "resources"
    for target, original in preview.SOURCE_NOTICES.items():
        (source / original).parent.mkdir(parents=True, exist_ok=True)
        (source / original).write_bytes(original.encode())
        (resources / "licenses" / target).parent.mkdir(parents=True, exist_ok=True)
        (resources / "licenses" / target).write_bytes(original.encode())
    vendor = tmp_path / "electron.zip"
    with zipfile.ZipFile(vendor, "w") as zipped:
        for name in ("LICENSE", "LICENSES.chromium.html"):
            zipped.writestr(name, name)
            path = resources / "licenses/electron" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
    for name in ("react/LICENSE", "other/NOTICE"):
        for root in (source / "node_modules", resources / "licenses/npm"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
    import hashlib
    prefix = json.dumps(["", vendor.stat().st_mode & 0o777], separators=(",", ":"))
    prepared = source / ".build/desktop-job/packager/prepared.json"
    prepared.parent.mkdir(parents=True)
    prepared.write_text(json.dumps({"electron": str(vendor), "files": [{"path": str(vendor), "digest": hashlib.sha256((prefix + preview.digest(vendor)).encode()).hexdigest()}]}), encoding="utf-8")
    measured = preview.notices(source, resources)
    assert {"npm/react/LICENSE", "npm/other/NOTICE"} <= measured.keys()
    prepared.unlink()
    vendor.unlink()
    assert preview.published_notices(source, resources, measured) == measured
    omitted = {key: value for key, value in measured.items() if key != "npm/other/NOTICE"}
    with pytest.raises(ValueError, match="notice set or bytes"):
        preview.published_notices(source, resources, omitted)
    (resources / "licenses/npm/other/NOTICE").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="notice set or bytes"):
        preview.published_notices(source, resources, measured)


@pytest.mark.platforms("posix")
def test_native_notice_inventory_refuses_actual_symlinks(tmp_path):
    resources = tmp_path / "resources"
    (resources / "licenses/npm").mkdir(parents=True)
    original = tmp_path / "notice"
    original.write_bytes(b"notice")
    (resources / "licenses/npm/link").symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        preview.notice_inventory(resources)


def test_shared_anonymous_fetch_retains_small_default_and_explicit_asset_bound(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        url = "https://github.com/ObliviousOdin/loki/releases/download/v0.1.0-alpha.9/fixture.zip"
    class Opener:
        def open(self, request, *, timeout):
            assert "Authorization" not in request.headers and timeout == 60
            return Response(b"x" * 65)
    monkeypatch.setattr(source_public, "build_opener", lambda *_: Opener())
    with pytest.raises(ValueError, match="bounded size"):
        source_public.fetch(Response.url, tmp_path / "too-large", max_bytes=64)
    source_public.fetch(Response.url, tmp_path / "exact", max_bytes=65)
    assert (tmp_path / "exact").read_bytes() == b"x" * 65
    with pytest.raises(FileExistsError):
        source_public.fetch(Response.url, tmp_path / "exact", max_bytes=65)
