"""Remove build-machine provenance only from fresh sealed dependency outputs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import urlsplit


def _regular_owned(root: Path, path: Path) -> None:
    if (path.is_symlink() or not stat.S_ISREG(path.stat().st_mode)
            or not path.resolve().is_relative_to(root)):
        raise ValueError(f"sealed dependency metadata is not an owned regular file: {path}")


def _without_record_row(content: bytes, selected: str) -> bytes:
    """Preserve the physical bytes of every unrelated CSV row, including quoting."""
    lines = content.decode("utf-8").splitlines(keepends=True)
    reader = csv.reader(lines, strict=True)
    kept = []
    start = removed = 0
    for row in reader:
        end = reader.line_num
        if row and row[0] == selected:
            if len(row) != 3:
                raise ValueError("invalid selected provenance RECORD row")
            removed += 1
        else:
            kept.extend(lines[start:end])
        start = end
    if removed != 1:
        raise ValueError("sealed provenance needs exactly one matching RECORD row")
    return "".join(kept).encode("utf-8")


def prune_local_direct_urls(environment: Path) -> int:
    """Local archive URLs name the build host; source/lock retain their provenance."""
    root = environment.resolve()
    sites = [*root.glob("lib/python*/site-packages"), *root.glob("Lib/site-packages")]
    removed = 0
    for site in sites:
        for direct in site.glob("*.dist-info/direct_url.json"):
            _regular_owned(root, direct)
            metadata = json.loads(direct.read_bytes())
            if not isinstance(metadata, dict) or not isinstance(metadata.get("url"), str):
                raise ValueError(f"invalid dependency direct URL metadata: {direct}")
            if urlsplit(metadata["url"]).scheme.lower() != "file":
                continue
            record = direct.with_name("RECORD")
            _regular_owned(root, record)
            content = _without_record_row(record.read_bytes(), direct.relative_to(site).as_posix())
            # uv may hardlink metadata from its reusable cache. Replace only
            # this fresh output's RECORD inode before unlinking its provenance.
            with tempfile.NamedTemporaryFile(dir=record.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
            try:
                temporary.chmod(stat.S_IMODE(record.stat().st_mode))
                os.replace(temporary, record)
            finally:
                temporary.unlink(missing_ok=True)
            direct.unlink()
            removed += 1
    return removed
