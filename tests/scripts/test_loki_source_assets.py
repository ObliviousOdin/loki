"""Release companions retain the exact locked codec source and notices."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from scripts.loki import package_preview, source_assets


@pytest.fixture
def source_fixture(tmp_path):
    license_bytes = b"Pilk GPLv3 license fixture\n"
    notice = b"Pilk codec notices\n\n/* Codec redistribution conditions. */\n"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, contents in {
            "pilk-0.2.4/LICENSE": license_bytes,
            "pilk-0.2.4/src/interface/SKP_Silk_SDK_API.h": b"/* Codec redistribution conditions. */ \t\r\n",
            "pilk-0.2.4/setup.py": b"raise RuntimeError('source must never execute')\n",
        }.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(contents)
            archive.addfile(entry, io.BytesIO(contents))
    data = stream.getvalue()
    path = tmp_path / source_assets.ARCHIVE
    path.write_bytes(data)
    lock = ("[[package]]\nname='pilk'\nversion='0.2.4'\n"
            "sdist={url='https://files.pythonhosted.org/packages/fixture/pilk-0.2.4.tar.gz',"
            f"hash='sha256:{hashlib.sha256(data).hexdigest()}',size={len(data)}}}\n").encode()
    return path, lock, license_bytes, notice


def test_exact_source_and_notices_are_copied_without_execution(tmp_path, source_fixture):
    path, lock, license_bytes, notice = source_fixture
    out = tmp_path / "release with spaces"
    out.mkdir()
    pin = source_assets.stage_pilk_source(
        out, lock=lock, license_bytes=license_bytes, codec_notice=notice, source=path,
    )
    assert (out / pin["source_asset"]).read_bytes() == path.read_bytes()
    assert (out / pin["license_asset"]).read_bytes() == license_bytes
    assert (out / pin["codec_notice_asset"]).read_bytes() == notice
    assert pin["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        source_assets.stage_pilk_source(
            out, lock=lock, license_bytes=license_bytes, codec_notice=notice, source=path,
        )


def test_download_uses_declared_https_pin_and_is_bounded(tmp_path, source_fixture, monkeypatch):
    path, lock, license_bytes, notice = source_fixture
    calls = []

    def download(url, *, timeout):
        calls.append((url, timeout))
        return io.BytesIO(path.read_bytes())

    monkeypatch.setattr(source_assets, "urlopen", download)
    out = tmp_path / "download"
    out.mkdir()
    pin = source_assets.stage_pilk_source(out, lock=lock, license_bytes=license_bytes, codec_notice=notice)
    assert calls == [(pin["url"], 60)]
    assert (out / pin["source_asset"]).read_bytes() == path.read_bytes()


@pytest.mark.parametrize("kind", ["tampered", "truncated", "license", "notice"])
def test_invalid_source_or_notice_publishes_no_companions(tmp_path, source_fixture, kind):
    path, lock, license_bytes, notice = source_fixture
    if kind == "tampered":
        path.write_bytes(b"x" + path.read_bytes()[1:])
    elif kind == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    elif kind == "license":
        license_bytes += b"changed"
    else:
        notice += b"changed"
    out = tmp_path / "rejected"
    out.mkdir()
    with pytest.raises(ValueError, match="Pilk"):
        source_assets.stage_pilk_source(
            out, lock=lock, license_bytes=license_bytes, codec_notice=notice, source=path,
        )
    assert not list(out.iterdir())


@pytest.mark.parametrize("before,after", [
    (b"name='pilk'", b"name='unrelated'"),
    (b"0.2.4", b"0.2.5"),
    (b"https://files.pythonhosted.org", b"http://files.pythonhosted.org"),
    (b"https://files.pythonhosted.org", b"https://unowned.invalid"),
    (b"sha256:", b"sha512:"),
])
def test_changed_version_or_unapproved_pin_requires_review(source_fixture, before, after):
    with pytest.raises(ValueError):
        source_assets.pilk_pin(source_fixture[1].replace(before, after))


def _git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def test_source_preview_contains_exact_recipes_and_required_native_companions(tmp_path, source_fixture, monkeypatch):
    source, lock, license_bytes, notice = source_fixture
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=Loki Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-qm", "fixture baseline")
    baseline = _git(repo, "rev-parse", "HEAD")
    files = {
        "pyproject.toml": b'[project]\nname="obliviousodin-loki-agent"\nversion="0.1.0a1"\n',
        "uv.lock": lock,
        "docs/loki/UPSTREAM.json": json.dumps({"commit": baseline}).encode(),
        "notices/pilk-0.2.4/LICENSE": license_bytes,
        "notices/pilk-0.2.4/SILK-NOTICES.txt": notice,
        "LICENSE": b"Project MIT attribution fixture\n",
        "NOTICE": b"Required upstream attribution fixture\n",
        "scripts/bundles/desktop.py": b"# Exact native build recipe fixture\n",
        "scripts/build/agent.py": b"# Exact assembly recipe fixture\n",
        **{f"scripts/{name}": name.encode() for name in ["install.sh", "install.ps1", "install.cmd"]},
    }
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Loki Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "fixture release")
    monkeypatch.setattr(package_preview, "ROOT", repo)
    monkeypatch.setattr(package_preview, "BASELINE", baseline)
    out = tmp_path / "release"
    metadata = package_preview.package(out, "HEAD", pilk_source=source)
    assert metadata["commit"] == _git(repo, "rev-parse", "HEAD")
    assert set(metadata["required_native_companion_assets"]) <= {p.name for p in out.iterdir()}
    assert metadata["third_party_sources"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    for line in (out / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    with gzip.open(out / f"loki-{package_preview.VERSION}-source.tar.gz", "rb") as stream:
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            for name, data in files.items():
                assert archive.extractfile(f"loki-{package_preview.VERSION}/{name}").read() == data
