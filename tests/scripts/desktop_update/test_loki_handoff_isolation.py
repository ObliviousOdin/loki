"""Actual handoffs bind their own home and clean only Loki scratch entries."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.scripts.test_desktop_update_target import _run_handoff


@pytest.mark.platforms("posix")
def test_fresh_handoff_ignores_foreign_home_and_leaves_upstream_scratch(tmp_path):
    foreign = tmp_path / "foreign-hermes"
    foreign.mkdir()
    sentinel = foreign / "preserve.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    upstream_scratch = tmp_path / "hermes-update-status.99999999"
    upstream_scratch.write_text("foreign scratch", encoding="utf-8")
    own_scratch = tmp_path / "loki-update-status.99999999"
    own_scratch.write_text("dead Loki scratch", encoding="utf-8")
    result, calls, home, install = _run_handoff(tmp_path, [], modern=True, foreign_home=foreign)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls and all(call["home"] == str(home) and call["install_root"] == str(install) for call in calls)
    receipt = json.loads((home / ".hermes-update-result.json").read_text(encoding="utf-8-sig"))
    assert receipt["ok"]
    assert list(foreign.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8-sig") == "unchanged"
    assert upstream_scratch.read_text(encoding="utf-8-sig") == "foreign scratch"
    assert not own_scratch.exists()


@pytest.mark.platforms("windows")
def test_windows_binder_handles_mixed_case_selectors_and_preserves_foreign_home(tmp_path):
    shell = shutil.which("powershell.exe")
    assert shell, "native Windows acceptance requires PowerShell"
    home, foreign = tmp_path / "loki-home", tmp_path / "foreign-hermes"
    home.mkdir()
    foreign.mkdir()
    sentinel = foreign / "preserve.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    script = Path(__file__).resolve().parents[3] / "scripts/desktop-update/windows.ps1"
    command = (
        "$env:hermes_home = $env:FOREIGN_FIXTURE; $env:loki_home = $env:LOKI_FIXTURE; "
        "Remove-Item Env:__LOKI_ENV_BOUND -ErrorAction SilentlyContinue; "
        "& $env:HANDOFF_SCRIPT -InstallRoot $env:LOKI_FIXTURE -NoUi -SelfTestMarker"
    )
    result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                            env={**os.environ, "FOREIGN_FIXTURE": str(foreign), "LOKI_FIXTURE": str(home),
                                 "HANDOFF_SCRIPT": str(script)}, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".hermes-update-result.json").is_file()
    assert list(foreign.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8-sig") == "unchanged"
