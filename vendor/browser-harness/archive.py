"""Verify Loki's browser source archive and its exact metadata-only patch."""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import importlib.metadata
import io
import json
from os import stat_result
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tomllib

HERE = Path(__file__).resolve().parent
VERSION = "0.1.13+loki.1"
ARCHIVE = f"browser_harness-{VERSION}.tar.gz"
UPSTREAM_ARCHIVE = "browser_harness-0.1.13.tar.gz"
UPSTREAM_SHA256 = "284dc547a042c309feafd9a9f4a74b2a8651b7963ea3ac6cb2f2d64889f6a8f3"
PREFIX = f"browser_harness-{VERSION}"
SOURCE_SPEC = f"vendor/browser-harness/{ARCHIVE}"
METADATA_FILES = {
    "pyproject.toml",
    "PKG-INFO",
    "src/browser_harness.egg-info/PKG-INFO",
    "src/browser_harness.egg-info/requires.txt",
}


def redirected(info: stat_result) -> bool:
    """A Windows junction redirects source just as a symbolic link does."""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def regular(root: Path, name: str, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    """Reject inputs that redirect artifact verification outside the caller root."""
    relative = PurePosixPath(name)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError(f"Invalid package input: {name}")
    if redirected(root.lstat()):
        raise ValueError("Symlink package root")
    path = root
    for component in relative.parts:
        path /= component
        info = path.lstat()
        if redirected(info):
            raise ValueError(f"Symlink package input: {name}")
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise ValueError(f"Nonregular or oversized package input: {name}")
    return path.read_bytes()


def source_members(data: bytes, prefix: str) -> dict[str, bytes]:
    """Read regular source members without extracting or executing supplier code."""
    files = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name:
                raise ValueError("Unsafe source archive path")
            if not path.parts or path.parts[0] != prefix or str(path) in seen:
                raise ValueError("Unexpected or duplicate archive member")
            seen.add(str(path))
            if len(seen) > 64:
                raise ValueError("Unexpected source archive member count")
            if member.isdir():
                continue
            if not member.isfile() or member.size > 1024 * 1024 or len(path.parts) < 2:
                raise ValueError("Nonregular or oversized source member")
            content = archive.extractfile(member)
            if content is None:
                raise ValueError("Missing source member content")
            files[str(PurePosixPath(*path.parts[1:]))] = content.read()
            if len(files) > 28:
                raise ValueError("Unexpected source member count")
    if len(files) != 28:
        raise ValueError("Incomplete supplier source archive")
    return files


def patch_metadata(name: str, data: bytes) -> bytes:
    """Only the reviewed private version and exact Pillow requirement may differ."""
    text = data.decode()
    replacements = [("pillow==12.3.0", "pillow==13.0.0")]
    if name == "pyproject.toml":
        replacements.append(('version = "0.1.13"', f'version = "{VERSION}"'))
    elif name.endswith("PKG-INFO"):
        replacements.append(("Version: 0.1.13\n", f"Version: {VERSION}\n"))
    for upstream, patched in replacements:
        if text.count(upstream) != 1:
            raise ValueError(f"Unexpected supplier metadata: {name}")
        text = text.replace(upstream, patched)
    return text.encode()


def package_files(root: Path) -> dict[str, bytes]:
    """Join official source, the seven-hunk patch and every proposed member hash."""
    data = regular(root, UPSTREAM_ARCHIVE)
    if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Supplier source differs from admitted official archive")
    before = source_members(data, "browser_harness-0.1.13")
    provenance = json.loads(regular(root, "UPSTREAM.json"))
    identity = {"package": "browser-harness", "upstream_version": "0.1.13", "private_version": VERSION}
    if any(provenance[key] != value for key, value in identity.items()):
        raise ValueError("Unexpected supplier or private package identity")
    if provenance["upstream_source_archive"]["sha256"] != UPSTREAM_SHA256:
        raise ValueError("Supplier source provenance differs")
    if set(before) != set(provenance["upstream_file_sha256"]):
        raise ValueError("Unexpected supplier file set")
    if set(provenance["patch_file_sha256"]) != METADATA_FILES:
        raise ValueError("Unexpected metadata patch file set")
    after = {}
    patches = []
    for name, content in before.items():
        if hashlib.sha256(content).hexdigest() != provenance["upstream_file_sha256"][name]:
            raise ValueError(f"Supplier member digest differs: {name}")
        patched = patch_metadata(name, content) if name in METADATA_FILES else content
        if name in METADATA_FILES:
            if hashlib.sha256(patched).hexdigest() != provenance["patch_file_sha256"][name]:
                raise ValueError(f"Unexpected patched metadata: {name}")
            patches.append("".join(difflib.unified_diff(content.decode().splitlines(keepends=True), patched.decode().splitlines(keepends=True), fromfile="upstream/" + name, tofile="proposed/" + name)))
        after[name] = patched
    if "".join(patches).encode() != regular(root, "PATCH.diff"):
        raise ValueError("Reviewable metadata patch differs")
    if regular(root, "LICENSE") != before["LICENSE"]:
        raise ValueError("Supplier license differs")
    return dict(sorted(after.items()))


def build_archive(root: Path = HERE) -> bytes:
    """Use sorted USTAR files and a fixed, nameless gzip envelope."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as output:
        for name, data in package_files(root).items():
            entry = tarfile.TarInfo(f"{PREFIX}/{name}")
            entry.size = len(data)
            entry.mode = 0o644
            entry.uid = entry.gid = entry.mtime = 0
            entry.uname = entry.gname = ""
            output.addfile(entry, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0, compresslevel=9) as output:
        output.write(buffer.getvalue())
    return compressed.getvalue()


def check_archive(root: Path = HERE, repository: Path | None = None) -> dict:
    """Verify the artifact and its exact selected root manifest/lock binding."""
    actual = regular(root, ARCHIVE)
    if actual != build_archive(root):
        raise ValueError("Archive differs from deterministic corresponding source")
    digest = hashlib.sha256(actual).hexdigest()
    provenance = json.loads(regular(root, "UPSTREAM.json"))["archive"]
    if provenance["filename"] != ARCHIVE or provenance["bytes"] != len(actual):
        raise ValueError("Private artifact identity or size differs")
    if digest != provenance["sha256"]:
        raise ValueError("Archive differs from reviewed private artifact")
    repo = repository or root.parent.parent
    manifest = tomllib.loads(regular(repo, "pyproject.toml").decode())
    if manifest["tool"]["uv"]["sources"]["browser-harness"] != {"path": SOURCE_SPEC}:
        raise ValueError("Root local source mapping differs")
    requirements = manifest["project"]["dependencies"]
    if f"browser-harness=={VERSION}; python_version >= '3.14'" not in requirements:
        raise ValueError("Root browser package pin differs")
    if "Pillow==13.0.0; python_version >= '3.14'" not in requirements:
        raise ValueError("Root Pillow pin needs requalification")
    lock = tomllib.loads(regular(repo, "uv.lock").decode())
    selected = [item for item in lock["package"] if item["name"] == "browser-harness"]
    if len(selected) != 1 or selected[0]["version"] != VERSION:
        raise ValueError("Root lock private package identity differs")
    node = selected[0]
    if node["source"] != {"path": SOURCE_SPEC} or node["sdist"] != {"hash": "sha256:" + digest}:
        raise ValueError("Root lock archive path or digest differs")
    return {"status": "verified", "package": "browser-harness", "version": VERSION, "bytes": len(actual), "sha256": digest}


def check_installed(root: Path = HERE) -> dict:
    """Check selected installed source bytes without importing supplier code."""
    result = check_archive(root)
    distribution = importlib.metadata.distribution("browser-harness")
    if distribution.version != VERSION:
        raise ValueError("Installed private package version differs")
    for name, data in package_files(root).items():
        if not name.startswith("src/") or ".egg-info/" in name:
            continue
        path = name.removeprefix("src/")
        installed = Path(distribution.locate_file(path))
        if installed.is_symlink() or installed.read_bytes() != data:
            raise ValueError(f"Installed supplier source differs: {path}")
    return {**result, "installed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--check-installed", action="store_true")
    modes.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        data = build_archive()
        with (HERE / ARCHIVE).open("xb") as output:
            output.write(data)
        result = {"status": "created", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    else:
        result = check_installed() if args.check_installed else check_archive()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
