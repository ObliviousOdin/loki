"""Inspect an unchanged native ZIP, including wheel contents and baked code objects."""
from __future__ import annotations

import importlib.util
import json
import marshal
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import struct
import stat
import tempfile
from types import CodeType
import zipfile

MAX_MEMBER = 1024 ** 3


def relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not path.parts:
        raise ValueError("Archive metadata must be payload-relative")
    return path.as_posix()


def code_filenames(code: CodeType):
    pending = [code]
    while pending:
        item = pending.pop()
        yield item.co_filename
        pending.extend(value for value in item.co_consts if isinstance(value, CodeType))


def inspect_bytecode(data: bytes) -> None:
    if len(data) < 16 or data[:4] != importlib.util.MAGIC_NUMBER or struct.unpack("<I", data[4:8])[0] != 1:
        raise ValueError("Expected current-interpreter unchecked-hash bytecode")
    code = marshal.loads(data[16:])
    if not isinstance(code, CodeType) or any(not name.startswith("/loki/") for name in code_filenames(code)):
        raise ValueError("Baked code retains a nonportable filename")


def import_roots(archive: zipfile.ZipFile, payload: str, manifest: dict) -> list[str]:
    runtime = manifest["runtime"]
    marker = json.loads(archive.read(payload + "/pm-runtime/pm-runtime.json"))
    python = json.loads(archive.read(payload + "/tools/facts.json"))["packages"]["python"]
    selected = payload + "/tools/" + relative(python["entry"]) + "/"
    minor = ".".join(python["version"].split(".")[:2])
    stdlib = selected + f"lib/python{minor}/"
    roots = [payload + "/" + relative(runtime["repoDir"]) + "/",
             payload + "/" + relative(runtime["sitePackages"]) + "/",
             payload + "/pm-runtime/" + relative(marker["sitePackages"]) + "/", stdlib]
    if len(set(roots)) != 4 or any(not any(name.startswith(root) for name in archive.namelist()) for root in roots):
        raise ValueError("Four distinct packaged import roots are required")
    return roots


def forbidden_member(member: str) -> bool:
    parts = PurePosixPath(member).parts
    return (member.endswith("/hermes-build.json")
            or any(part.startswith("__editable___obliviousodin_loki_agent_") for part in parts)
            or any(part.startswith("obliviousodin_loki_agent-") and part.endswith(".dist-info") for part in parts)
            or ("uv-cache" in parts and (any(part.startswith("interpreter-v") for part in parts)
                or ("editable" in parts and any(part.startswith("sdists-v") for part in parts)))))


def inspect_members(archive: zipfile.ZipFile, *, roots: list[str], patterns: list[bytes],
                    scratch: Path, depth: int = 0) -> dict:
    counts = {"members": 0, "bytes": 0, "bytecode": 0, "nested_wheels": 0}
    if len(archive.namelist()) != len(set(archive.namelist())):
        raise ValueError("Duplicate archive members refused")
    for info in archive.infolist():
        relative(info.filename.rstrip("/"))
        if info.is_dir():
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            target = archive.read(info).decode("utf-8")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(info.filename), target))
            if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
                raise ValueError("Archive symlink escapes its owned root")
        if forbidden_member(info.filename) or any(p in info.filename.encode() for p in patterns):
            raise ValueError("Build metadata or private path in native archive")
        code = not depth and info.filename.endswith(".pyc") and any(info.filename.startswith(r) for r in roots)
        if code and (info.external_attr >> 16) & 0o222:
            raise ValueError("Baked bytecode must be read-only")
        wheel = info.filename.lower().endswith(".whl")
        if (code or wheel) and (info.file_size > MAX_MEMBER or depth >= 4):
            raise ValueError("Native inspection limit exceeded")
        if wheel and shutil.disk_usage(scratch).free < info.file_size + 512 * 1024 ** 2:
            raise ValueError("Insufficient nested-wheel inspection capacity")
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 ** 2, dir=scratch) as collected:
            carry = b""
            with archive.open(info) as stream:
                for block in iter(lambda: stream.read(1024 ** 2), b""):
                    joined = carry + block
                    if any(pattern in joined for pattern in patterns):
                        raise ValueError("Private build path in native content")
                    carry = joined[-max([1, *map(len, patterns)]):]
                    counts["bytes"] += len(block)
                    if code or wheel:
                        collected.write(block)
            collected.seek(0)
            if code:
                inspect_bytecode(collected.read())
                counts["bytecode"] += 1
            if wheel:
                with zipfile.ZipFile(collected) as nested:
                    values = inspect_members(nested, roots=[], patterns=patterns, scratch=scratch, depth=depth + 1)
                for key, value in values.items():
                    counts[key] += value
                counts["nested_wheels"] += 1
        counts["members"] += 1
    return counts


def scan(archive: Path, *, commit: str, build_roots: list[Path], scratch: Path) -> dict:
    patterns = [str(root.resolve()).encode(encoding) for root in build_roots
                for encoding in ("utf-8", "utf-16-le", "utf-16-be")]
    with zipfile.ZipFile(archive) as zipped:
        manifests = [name for name in zipped.namelist() if name.endswith("/agent-payload/manifest.json")]
        if len(manifests) != 1:
            raise ValueError("One packaged payload is required")
        payload = manifests[0].removesuffix("/manifest.json")
        manifest = json.loads(zipped.read(manifests[0]))
        if (manifest["ref"] != commit or manifest.get("external") is True
                or manifest["runtime"]["commands"]["hermes"] != "bin/loki"):
            raise ValueError("Native payload source mismatch")
        roots = import_roots(zipped, payload, manifest)
        if zipped.read(payload + "/.hermes-baked-pycache") != b"unchecked-hash\n":
            raise ValueError("Baked payload marker missing")
        for root in roots:
            if not any(name.startswith(root) and name.endswith(".pyc") for name in zipped.namelist()):
                raise ValueError("A packaged import root has no baked caches")
        names = set(zipped.namelist())
        for name in names:
            if not name.endswith(".py") or not any(name.startswith(root) for root in roots):
                continue
            if importlib.util.cache_from_source(name) in names:
                continue
            try:
                compile(zipped.read(name), name, "exec")
            except SyntaxError:
                continue
            raise ValueError("Parseable packaged source has no default baked bytecode")
        counts = inspect_members(zipped, roots=roots, patterns=patterns, scratch=scratch)
    return {"status": "passed", "scope": "finite build-root bytes, recursive wheels and all four roots' code filenames", **counts}
