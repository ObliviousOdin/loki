"""Exact-to-lock pruning for uv caches.

The lock is the contract for anything downstream consumes wholesale: a
shipped bundle payload and a rolling CI cache snapshot both must not carry
wheels the project's uv.lock cannot resolve. Rolling caches accumulate
entries for superseded pins (prefix restores across dependency changes);
pruning to the lock keeps every consumer exact without discarding wheels
the current lock still needs (unlike ``uv cache prune --ci``).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path


def lock_package_names(source_repo: Path) -> set[str]:
    """Dist names the lock can resolve; the exactness contract for a cache."""
    import tomllib

    data = tomllib.loads((source_repo / "uv.lock").read_text(encoding="utf-8"))
    return {entry["name"].lower().replace("_", "-") for entry in data["package"]}


def project_package_name(source_repo: Path) -> str:
    """The source project is assembled separately in a native distribution."""
    from pm.environment import _project_name

    return _project_name(source_repo).lower().replace("_", "-")


def archive_package_name(bucket: Path) -> str | None:
    """Identify an extracted wheel without importing its installed code."""
    for marker_file in bucket.glob("*.dist-info"):
        match = re.fullmatch(r"([A-Za-z0-9_.]+?)-\d[^-]*\.dist-info", marker_file.name)
        if match:
            return match.group(1).lower().replace("_", "-")
    return None


def prune_uv_cache_to_lock(cache: Path, source_repo: Path, *, exclude_project: bool = False) -> int:
    """Delete cache entries for dists the lock cannot resolve.

    Unidentifiable buckets (no dist-info) survive — pruning fails open for
    unknown layouts, never for identifiable stale pins. Returns the pruned
    entry count for the build log.
    """
    keep = lock_package_names(source_repo)
    if exclude_project:
        keep.discard(project_package_name(source_repo))

    pruned = 0
    archive = cache / "archive-v0"
    if archive.is_dir():
        for bucket in archive.iterdir():
            if not bucket.is_dir():
                continue
            name = archive_package_name(bucket)
            if name is not None and name not in keep:
                shutil.rmtree(bucket, ignore_errors=True)
                pruned += 1
    for family_dir in (*cache.glob("wheels-v*/pypi"), *cache.glob("sdists-v*/pypi")):
        if not family_dir.is_dir():
            continue
        for entry in family_dir.iterdir():
            if entry.is_dir() and entry.name.lower().replace("_", "-") not in keep:
                shutil.rmtree(entry, ignore_errors=True)
                pruned += 1
    return pruned
