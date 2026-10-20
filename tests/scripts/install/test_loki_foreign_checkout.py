"""The Loki installer must not rewrite an unrelated Fabric/Hermes Git checkout."""
import os
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]


def foreign_repository(tmp_path):
    repo = tmp_path / "foreign-fabric"
    repo.mkdir()
    for args in (("init", "-q"), ("config", "user.name", "Fixture"),
                 ("config", "user.email", "fixture@example.invalid"),
                 ("remote", "add", "origin", "https://example.invalid/existing-fabric.git")):
        subprocess.run(["git", *args], cwd=repo, check=True, timeout=30)
    (repo / "pyproject.toml").write_text('[project]\nname="foreign-fabric"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=30)
    subprocess.run(["git", "commit", "-qm", "unfinished project"], cwd=repo, check=True, timeout=30)
    (repo / "unfinished.txt").write_text("preserve me", encoding="utf-8")
    return repo


def snapshot(repo):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True, encoding="utf-8", timeout=30)
    return git("rev-parse", "HEAD"), git("remote", "-v"), git("status", "--porcelain"), git("show-ref")


@pytest.mark.platforms("posix")
def test_posix_refuses_foreign_checkout_before_mutation(tmp_path):
    repo = foreign_repository(tmp_path)
    before = snapshot(repo)
    script = f'source {shlex.quote(str(ROOT / "scripts/install.sh"))} --manifest\nstage_repository'
    result = subprocess.run(["bash", "-c", script], env={**os.environ,
        "LOKI_HOME": str(tmp_path / "loki-home"), "LOKI_INSTALL_DIR": str(repo),
        "LOKI_REPO_URL": str(tmp_path / "missing-loki-origin")},
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode != 0
    assert "foreign Git checkout" in result.stdout + result.stderr
    assert snapshot(repo) == before
    assert (repo / "unfinished.txt").read_text(encoding="utf-8-sig") == "preserve me"


@pytest.mark.platforms("windows")
def test_windows_refuses_foreign_checkout_before_mutation(tmp_path):
    repo = foreign_repository(tmp_path)
    before = snapshot(repo)
    command = f'. "{ROOT / "scripts/install.ps1"}" -InstallDir "{repo}" -LokiHome "{tmp_path / "loki-home"}"; Stage-Repository'
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
        env={**os.environ, "LOKI_REPO_URL": str(tmp_path / "missing-loki-origin")},
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode != 0
    assert "foreign Git checkout" in result.stdout + result.stderr
    assert snapshot(repo) == before
