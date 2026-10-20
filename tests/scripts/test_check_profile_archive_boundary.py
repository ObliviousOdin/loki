"""Behavioral tests for the profile archive CI guard."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "check_profile_archive_boundary.py"
)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_root_passes(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == 0
    assert "No profile export archives" in result.stdout


def test_root_profile_archive_fails_without_printing_contents(tmp_path):
    default_archive = tmp_path / "default.tar.gz"
    alternate_archive = tmp_path / "backup.TGZ"
    default_archive.write_bytes(b"profile webhook secret must never be printed")
    alternate_archive.write_bytes(b"another archive")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "default.tar.gz" in result.stdout
    assert "backup.TGZ" in result.stdout
    assert "profile webhook secret" not in result.stdout
    assert "another archive" not in result.stdout


def test_nested_profile_archive_is_also_rejected(tmp_path):
    nested = tmp_path / "fixtures"
    nested.mkdir()
    (nested / "fixture.tar.gz").write_bytes(b"test fixture")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "fixtures/fixture.tar.gz" in result.stdout


def test_reviewed_dependency_archive_requires_exact_path_and_bytes(tmp_path):
    source = SCRIPT.parents[2] / "vendor/braces/braces-3.0.3-loki.2.tgz"
    admitted = tmp_path / "vendor/braces" / source.name
    admitted.parent.mkdir(parents=True)
    shutil.copyfile(source, admitted)
    assert _run(tmp_path).returncode == 0

    other = admitted.with_name("profile.tgz")
    shutil.copyfile(source, other)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "vendor/braces/profile.tgz" in result.stdout
    assert admitted.relative_to(tmp_path).as_posix() not in result.stdout

    admitted.write_bytes(b"profile secret replacing the reviewed archive")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert admitted.relative_to(tmp_path).as_posix() in result.stdout
    assert "profile secret replacing" not in result.stdout


@pytest.mark.platforms("posix")
def test_reviewed_dependency_archive_does_not_admit_symlinks(tmp_path):
    source = SCRIPT.parents[2] / "vendor/braces/braces-3.0.3-loki.2.tgz"
    link = tmp_path / "vendor/braces" / source.name
    link.parent.mkdir(parents=True)
    link.symlink_to(source)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert link.relative_to(tmp_path).as_posix() in result.stdout
