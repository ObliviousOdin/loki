"""Discover real Loki package layouts without borrowing a Hermes desktop app."""

import sys
from pathlib import Path

import pytest

from hermes_cli.main_desktop import _desktop_packaged_executable_in


def _entry(root: Path, name: str) -> Path:
    if sys.platform == "darwin":
        return root / "mac-arm64" / f"{name}.app" / "Contents" / "MacOS" / name
    if sys.platform == "win32":
        return root / "win-unpacked" / f"{name}.exe"
    return root / "linux-unpacked" / name


@pytest.mark.parametrize("name", ["Loki", "Loki Source", "Loki Light", "Loki Source abcdef0", "Loki Canary", "loki-abcdef0"])
def test_own_primary_and_variant_packages_are_discovered(tmp_path, name):
    if sys.platform == "darwin" and name.startswith("loki-"):
        name = "Loki abcdef0"
    executable = _entry(tmp_path, name)
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture executable")
    foreign = _entry(tmp_path, "Hermes")
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(b"foreign fixture executable")
    assert _desktop_packaged_executable_in(tmp_path) == executable


def test_foreign_hermes_package_is_never_selected(tmp_path):
    executable = _entry(tmp_path, "Hermes")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"foreign fixture executable")
    assert _desktop_packaged_executable_in(tmp_path) is None
