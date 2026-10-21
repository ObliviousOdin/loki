"""Declared dependency artifacts needed by an isolated core build snapshot."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from pm.package import InstallError


def _relative_archive_path(name: str) -> Path:
    """Archive declarations are portable relative paths, including on Windows."""
    relative = Path(name)
    windows = PureWindowsPath(name)
    if relative.anchor or windows.anchor or ".." in relative.parts or ".." in windows.parts:
        raise InstallError("venv", "local dependency archive must stay inside the core source")
    return relative


def local_archive_inputs(source: Path, metadata: dict) -> set[str]:
    """Keep relative, source-owned archive declarations usable after snapshotting."""
    sources = metadata.get("tool", {}).get("uv", {}).get("sources", {})
    files = set()
    for alternatives in sources.values():
        for spec in alternatives if isinstance(alternatives, list) else [alternatives]:
            if not isinstance(spec, dict) or "path" not in spec:
                continue
            name = spec["path"]
            if not isinstance(name, str) or not name:
                raise InstallError("venv", "local dependency archive requires a relative file path")
            entry = source / name
            if entry.is_dir():
                # Directory sources keep the existing package-tree snapshot behavior.
                continue
            _relative_archive_path(name)
            if (entry.is_symlink() or not entry.is_file()
                    or not entry.resolve().is_relative_to(source.resolve())):
                raise InstallError("venv", "local dependency archive must be a source-owned regular file")
            files.add(name)
    return files
