#!/usr/bin/env python3
"""Reject profile export archives before publication.

``.gitignore`` and ``.dockerignore`` are useful first-line filters, but both
can be bypassed (for example with ``git add -f`` or a non-standard build
context).  This check is the blocking, executable policy at the CI and image
publication boundaries.  It intentionally checks the filesystem rather than
Git's index so a generated archive cannot enter a build after checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

_PROFILE_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz")
# Only these reviewed source artifacts are admitted; a profile at the same path
# must still fail. Regeneration requires a new version and a reviewed digest.
_REVIEWED_SOURCE_ARCHIVES = {
    "vendor/braces/braces-3.0.3-loki.2.tgz":
        "fa863313fd527bceb3810f7fb07d0852c67fb80458d4b9404dd374ade693ccbc",
    "vendor/htmlparser2/htmlparser2-12.0.0-loki.3.tgz":
        "ddbe8b87a6f6decd49e599bdcd1ecf907db1f660664fa20c224732733e95943a",
    "vendor/browser-harness/browser_harness-0.1.13.tar.gz":
        "284dc547a042c309feafd9a9f4a74b2a8651b7963ea3ac6cb2f2d64889f6a8f3",
    "vendor/browser-harness/browser_harness-0.1.13+loki.1.tar.gz":
        "d2b49644f0e78841ab13712ce30a633ebcb1ec16d59f82ca59f80d19195e13de",
}


def _is_reviewed_source_archive(path: Path, relative: Path) -> bool:
    expected = _REVIEWED_SOURCE_ARCHIVES.get(relative.as_posix())
    if expected is None or path.is_symlink() or not path.is_file():
        return False
    if path.stat().st_size > 1024 * 1024:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == expected


def find_forbidden_profile_archives(root: Path) -> list[Path]:
    """Return profile archive paths anywhere in the checkout."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")

    offenders: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", ".venv", "venv", "node_modules", "__pycache__"}
        ]
        for name in (*dirnames, *filenames):
            if name.casefold().endswith(_PROFILE_ARCHIVE_SUFFIXES):
                path = Path(directory) / name
                relative = path.relative_to(root)
                if not _is_reviewed_source_archive(path, relative):
                    offenders.append(relative)

    return sorted(offenders, key=lambda path: path.as_posix().casefold())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject profile export archives in the checkout."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to inspect (default: current directory)",
    )
    args = parser.parse_args(argv)

    try:
        offenders = find_forbidden_profile_archives(args.root)
    except ValueError as exc:
        parser.error(str(exc))

    if not offenders:
        print("No profile export archives detected in the checkout.")
        return 0

    print(
        "::error::profile export archives are forbidden "
        "in source and Docker build contexts"
    )
    for path in offenders:
        print(f"  {path.as_posix()}")
    print(
        "Move the archive outside the checkout or pass an explicit external "
        "output path to the profile export command."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
