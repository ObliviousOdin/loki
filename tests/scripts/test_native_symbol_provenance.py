"""Real macOS linker/loader coverage for pre-seal debug provenance normalization."""
from __future__ import annotations

import base64
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

from scripts.bundles.native_symbols import strip_macho_debug_symbols


@pytest.fixture
def native_wheel(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("requires the actual macOS linker and Mach-O loader")
    compiler = shutil.which("clang")
    assert compiler, "Native macOS qualification requires the installed compiler toolchain"
    private_build = tmp_path / "PRIVATE_FIXTURE_BUILD_ROOT"
    private_build.mkdir()
    source = private_build / "probe.c"
    source.write_text("int loki_probe(void) { return 42; }\n")
    original = tmp_path / "original-public-cache"
    site = original / "site-packages"
    library = site / "pilk" / "_pilk.test.so"
    library.parent.mkdir(parents=True)
    # Wheels link debug-bearing objects without shipping a separate dSYM bundle.
    obj = private_build / "probe.o"
    subprocess.run([compiler, "-g", "-c", str(source), "-o", str(obj)],
                   check=True, capture_output=True)
    subprocess.run([compiler, "-dynamiclib", str(obj), "-o", str(library)],
                   check=True, capture_output=True)
    assert b"PRIVATE_FIXTURE_BUILD_ROOT" in library.read_bytes(), "fixture must contain real compiler provenance"
    metadata = site / "pilk-1.0.dist-info"
    metadata.mkdir()
    record = metadata / "RECORD"
    record.write_text("pilk/_pilk.test.so,,\npilk-1.0.dist-info/RECORD,,\n", encoding="utf-8")
    return original, library, record


def _load(library):
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(library)],
                   check=True, capture_output=True)
    code = "import ctypes,sys; assert ctypes.CDLL(sys.argv[1]).loki_probe() == 42"
    subprocess.run([sys.executable, "-I", "-B", "-c", code, str(library)], check=True, capture_output=True)


@pytest.mark.platforms("macos")
def test_staged_active_and_offline_cache_libraries_are_private_path_free_and_loadable(native_wheel, tmp_path):
    original, library, record = native_wheel
    original_bytes, record_bytes = library.read_bytes(), record.read_bytes()
    payload = tmp_path / "payload"
    for location in ("venv/lib/python/site-packages", "uv-cache/archive-v0/wheel"):
        dest = payload / location
        shutil.copytree(original / "site-packages", dest, copy_function=os.link)
    assert library.stat().st_nlink == 3
    _load(library)

    assert strip_macho_debug_symbols(payload) == {"libraries": 2, "wheels": 0}

    for staged in payload.rglob("_pilk.test.so"):
        assert b"PRIVATE_FIXTURE_BUILD_ROOT" not in staged.read_bytes()
        assert staged.stat().st_ino != library.stat().st_ino
        _load(staged)
        staged_record = staged.parent.parent / "pilk-1.0.dist-info/RECORD"
        assert staged_record.stat().st_ino != record.stat().st_ino
        rows = list(csv.reader(staged_record.read_text().splitlines()))
        digest = base64.urlsafe_b64encode(hashlib.sha256(staged.read_bytes()).digest()).rstrip(b"=").decode()
        assert rows[0] == ["pilk/_pilk.test.so", "sha256=" + digest, str(staged.stat().st_size)]
        assert rows[1] == ["pilk-1.0.dist-info/RECORD", "", ""]
    assert library.read_bytes() == original_bytes and record.read_bytes() == record_bytes
    before = {p: p.read_bytes() for p in payload.rglob("*") if p.is_file()}
    assert strip_macho_debug_symbols(payload) == {"libraries": 0, "wheels": 0}
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.platforms("macos")
def test_foreign_symlink_is_refused_without_touching_its_target(native_wheel, tmp_path):
    _original, library, _record = native_wheel
    before = library.read_bytes()
    linked = tmp_path / "payload/pilk/_pilk.test.so"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(library)
    with pytest.raises(ValueError, match="contained in the staged payload"):
        strip_macho_debug_symbols(linked.parents[1])
    assert library.read_bytes() == before


@pytest.mark.platforms("macos")
def test_missing_wheel_record_refuses_before_replacing_library(native_wheel, tmp_path):
    original, _library, _record = native_wheel
    payload = tmp_path / "payload"
    shutil.copytree(original / "site-packages", payload)
    record = payload / "pilk-1.0.dist-info/RECORD"
    record.unlink()
    library = payload / "pilk/_pilk.test.so"
    before = library.read_bytes()
    with pytest.raises(ValueError, match="exactly one regular wheel RECORD"):
        strip_macho_debug_symbols(payload)
    assert library.read_bytes() == before


@pytest.mark.platforms("macos")
def test_cached_wheel_keeps_members_and_metadata_with_loadable_normalized_binary(native_wheel, tmp_path):
    original, library, record = native_wheel
    cached = tmp_path / "original.whl"
    with zipfile.ZipFile(cached, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (original / "site-packages").rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(original / "site-packages"))
        archive.writestr("pilk-1.0.dist-info/LICENSE", b"retained test license\n")
        archive.comment = b"retained wheel comment"
    before = cached.read_bytes()
    payload = tmp_path / "payload"
    payload.mkdir()
    wheel = payload / "pilk-1.0-cp314-cp314-macosx_11_0_arm64.whl"
    os.link(cached, wheel)

    assert strip_macho_debug_symbols(payload) == {"libraries": 0, "wheels": 1}

    with zipfile.ZipFile(cached) as source, zipfile.ZipFile(wheel) as staged:
        assert staged.namelist() == source.namelist()
        assert staged.comment == source.comment
        for old, new in zip(source.infolist(), staged.infolist()):
            assert (new.filename, new.date_time, new.external_attr, new.compress_type) == (
                old.filename, old.date_time, old.external_attr, old.compress_type)
            if old.filename not in ("pilk/_pilk.test.so", "pilk-1.0.dist-info/RECORD"):
                assert staged.read(new) == source.read(old)
        data = staged.read("pilk/_pilk.test.so")
        assert b"PRIVATE_FIXTURE_BUILD_ROOT" not in data
        library = tmp_path / "relocated.so"
        library.write_bytes(data)
        _load(library)
        rows = list(csv.reader(staged.read("pilk-1.0.dist-info/RECORD").decode().splitlines()))
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        assert rows[0] == ["pilk/_pilk.test.so", "sha256=" + digest, str(len(data))]
    assert wheel.stat().st_ino != cached.stat().st_ino and cached.read_bytes() == before
    assert record.read_bytes() == b"pilk/_pilk.test.so,,\npilk-1.0.dist-info/RECORD,,\n"
    sealed = wheel.read_bytes()
    assert strip_macho_debug_symbols(payload) == {"libraries": 0, "wheels": 0}
    assert wheel.read_bytes() == sealed
