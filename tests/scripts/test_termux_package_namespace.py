"""Exercise shell ownership decisions with disposable package-manager doubles.

These are host shell/protocol tests, not Android binary installation tests.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "obliviousodin-loki-agent"


def _tool(path: Path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nset -eu\n" + script, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def package_prefix(tmp_path):
    prefix = tmp_path / "prefix with spaces"
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True)
    legacy = prefix / "lib/hermes-agent/bin/hermes"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"foreign installed Hermes")
    (bin_dir / "hermes").symlink_to("../lib/hermes-agent/bin/hermes")
    calls = tmp_path / "calls"
    log = 'printf "%s\\n" "$(basename "$0")" "$@" >> "$CALL_LOG"\n'
    _tool(bin_dir / "dpkg-deb", log + 'cat "$2"\n')
    _tool(bin_dir / "dpkg", log + '''
if [ "${1:-}" != --compare-versions ] && [ ! -L "$PREFIX/bin/loki" ]; then
    ln -s ../lib/loki-agent/bin/loki "$PREFIX/bin/loki"
fi
''')
    _tool(bin_dir / "apt-get", log)
    _tool(bin_dir / "dpkg-query", log + '''
if [ -f "$PREFIX/query-once" ]; then
    printf 2.0.0
else
    touch "$PREFIX/query-once"
    printf 1.0.0
fi
''')
    _tool(prefix / "lib/loki-agent/venv/bin/python", log + '''
if [ "${EXPECT_SENTINEL:-}" = 1 ]; then
    [ -f "$LOKI_HOME/sentinel" ]
fi
''')
    env = {**os.environ, "PREFIX": str(prefix), "CALL_LOG": str(calls)}
    return prefix, calls, legacy, env


def _invoke(script, args, env):
    return subprocess.run(
        [shutil.which("bash"), str(ROOT / "scripts/termux" / script), *map(str, args)],
        env=env, capture_output=True, text=True, check=False, timeout=15,
    )


def _foreign_unchanged(prefix, legacy):
    assert legacy.read_bytes() == b"foreign installed Hermes"
    assert os.readlink(prefix / "bin/hermes") == "../lib/hermes-agent/bin/hermes"


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("script", ["check_deb.sh", "check_apt.sh"])
@pytest.mark.parametrize("foreign", ["hermes-agent", "foreign-fabric"])
def test_checks_refuse_foreign_deb_before_any_installer(tmp_path, package_prefix, script, foreign):
    prefix, calls, legacy, env = package_prefix
    archive = tmp_path / "previous package.deb"
    archive.write_text(foreign, encoding="utf-8")
    args = [archive] if script == "check_deb.sh" else ["loki-stable", "2.0.0", "file:/owned", archive]
    result = _invoke(script, args, env)
    assert result.returncode != 0 and "Refusing to install a foreign package" in result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["dpkg-deb", "--field", str(archive), "Package"]
    assert not (prefix / "bin/loki").is_symlink()
    _foreign_unchanged(prefix, legacy)


@pytest.mark.platforms("posix")
def test_deb_reinstall_uses_only_owned_package_and_layout(tmp_path, package_prefix):
    prefix, calls, legacy, env = package_prefix
    archive = tmp_path / "owned package.deb"
    archive.write_text(PACKAGE, encoding="utf-8")
    result = _invoke("check_deb.sh", [archive], env)
    assert result.returncode == 0, result.stdout + result.stderr
    records = calls.read_text(encoding="utf-8").splitlines()
    assert records.count("dpkg") == 2
    assert records.count(str(archive)) == 3
    assert records.count("python") == 1
    assert "DEB_INSTALL_AND_REINSTALL_OK" in result.stdout
    assert os.readlink(prefix / "bin/loki") == "../lib/loki-agent/bin/loki"
    _foreign_unchanged(prefix, legacy)


@pytest.mark.platforms("posix")
def test_apt_upgrade_queries_and_installs_only_owned_package(tmp_path, package_prefix):
    prefix, calls, legacy, env = package_prefix
    env["EXPECT_SENTINEL"] = "1"
    archive = tmp_path / "previous Loki.deb"
    archive.write_text(PACKAGE, encoding="utf-8")
    result = _invoke("check_apt.sh", ["loki-stable", "2.0.0", "file:/owned", archive], env)
    assert result.returncode == 0, result.stdout + result.stderr
    records = calls.read_text(encoding="utf-8").splitlines()
    assert records.count(PACKAGE) == 3
    assert "hermes-agent" not in records and "foreign-fabric" not in records
    assert records.count("dpkg-query") == 2 and records.count("apt-get") == 2
    assert "SIGNED_APT_UPGRADE_OK 1.0.0 -> 2.0.0" in result.stdout
    assert not list((prefix / "tmp").iterdir()), "owned proof scratch should be cleaned"
    _foreign_unchanged(prefix, legacy)
