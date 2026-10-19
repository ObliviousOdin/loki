"""Sealed bytecode keeps build paths private and remains warm after relocation."""

import hashlib
import json
import marshal
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
from types import CodeType

import pytest

from scripts.bundles import bytecode


def _payload(root):
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    sources = {
        "hermes-agent/agent_probe.py": "agent_probe",
        f"venv/lib/{version}/site-packages/dependency_probe.py": "dependency_probe",
        f"pm-runtime/lib/{version}/site-packages/manager_probe.py": "manager_probe",
    }
    for relative, name in sources.items():
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            f"VALUE = {name!r}\n"
            "def outer():\n"
            "    def inner():\n"
            "        raise RuntimeError('synthetic relocation probe')\n"
            "    return inner()\n"
        )
    return [root / relative for relative in sources]


def _code_filenames(code):
    yield code.co_filename
    for value in code.co_consts:
        if isinstance(value, CodeType):
            yield from _code_filenames(value)


def _cache(source, optimization=None):
    from importlib.util import cache_from_source

    return Path(cache_from_source(source, optimization=optimization))


def test_bake_replaces_old_unchecked_filenames_and_is_reproducible(tmp_path):
    first = tmp_path / "private builder one"
    second = tmp_path / "different builder two"
    sources = _payload(first)
    for root, entries in [(first, sources), (second, _payload(second))]:
        for source in entries:
            for optimize in range(3):
                py_compile.compile(
                    str(source), dfile=str(root / "old source" / source.name), doraise=True,
                    invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                    optimize=optimize,
                )
                _cache(source, str(optimize) if optimize else "").chmod(0o444)
    before = {root: {path.relative_to(root) for path in root.rglob("*.pyc")}
              for root in (first, second)}

    bytecode.bake_bytecode(first, Path(sys.executable))
    bytecode.bake_bytecode(second, Path(sys.executable))
    for root in (first, second):
        assert {path.relative_to(root) for path in root.rglob("*.pyc")} == before[root]

    for source in sources:
        relative = source.relative_to(first)
        for optimization in ["", "1", "2"]:
            cache = _cache(source, optimization)
            cached = cache.read_bytes()
            assert cached[4:8] == b"\x01\x00\x00\x00"
            assert bytes(first) not in cached and bytes(second) not in cached
            code = marshal.loads(cached[16:])
            assert set(_code_filenames(code)) == {str(Path("/loki") / relative)}
            assert cached == _cache(second / relative, optimization).read_bytes()
            assert cache.stat().st_mode & 0o222 == 0


def test_relocated_payload_uses_all_warm_roots_without_builder_files(tmp_path, monkeypatch):
    builder = tmp_path / "private builder"
    sources = _payload(builder)
    stdlib = builder / "tools" / "python-fixture" / "lib" / "python-fixture"
    stdlib.mkdir(parents=True)
    source = stdlib / "stdlib_probe.py"
    source.write_text("VALUE = 'stdlib_probe'\n")
    sources.append(source)
    monkeypatch.setattr(bytecode, "_staged_stdlib", lambda root, python: stdlib, raising=False)
    bytecode.bake_bytecode(builder, Path(sys.executable))
    for source in sources:
        assert _cache(source).is_file()
        assert bytes(builder) not in _cache(source).read_bytes()

    installed = tmp_path / "installed Loki with spaces"
    shutil.copytree(builder, installed)
    builder.rename(tmp_path / "unavailable retired builder")
    relocated = [installed / source.relative_to(builder) for source in sources]
    for source in relocated:
        stat = source.stat()
        os.utime(source, (stat.st_atime, stat.st_mtime + 3600))
    caches = [_cache(source) for source in relocated]
    before = [(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in caches]
    script = """
import importlib, json, pathlib, sys, traceback
sources = [pathlib.Path(p) for p in json.loads(sys.argv[1])]
sys.path[:0] = [str(p.parent) for p in sources]
assert not sys.dont_write_bytecode and sys.pycache_prefix is None
for source in sources:
    module = importlib.import_module(source.stem)
    assert pathlib.Path(module.__file__) == source
    assert pathlib.Path(module.__cached__).is_file()
    assert module.VALUE == source.stem
    if hasattr(module, 'outer'):
        try:
            module.outer()
        except RuntimeError:
            frames = traceback.extract_tb(sys.exc_info()[2])
            assert frames[-1].filename == str(source)
        else:
            raise AssertionError('nested error did not run')
print('all relocated module origins and nested tracebacks verified')
"""
    child = subprocess.run(
        [sys.executable, "-I", "-c", script, json.dumps([str(p) for p in relocated])],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert "all relocated module origins" in child.stdout
    after = [(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in caches]
    assert after == before


def test_external_interpreter_never_selects_its_stdlib(tmp_path, monkeypatch):
    def unexpected_query(*args, **kwargs):
        raise AssertionError("external interpreter's standard library was queried")

    monkeypatch.setattr(subprocess, "check_output", unexpected_query)
    assert bytecode._staged_stdlib(tmp_path, Path(sys.executable).resolve()) is None


@pytest.mark.parametrize("escape", [False, True])
def test_staged_interpreter_requires_its_actual_stdlib_inside_payload(tmp_path, monkeypatch, escape):
    payload = tmp_path / "payload"
    python = payload / "tools" / "python-fixture" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    stdlib = (tmp_path if escape else python.parent.parent) / "stdlib"
    stdlib.mkdir()
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: str(stdlib) + "\n")
    if escape:
        with pytest.raises(ValueError, match="standard library.*outside"):
            bytecode._staged_stdlib(payload, python)
    else:
        assert bytecode._staged_stdlib(payload, python) == stdlib
