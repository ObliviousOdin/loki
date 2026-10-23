"""Actual Windows cancellation must settle the original owned process handles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.platforms("windows")
@pytest.mark.parametrize("completed_child", [False, True])
def test_job_cancellation_settles_original_process_handles(tmp_path: Path, completed_child: bool) -> None:
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system / "System32/WindowsPowerShell/v1.0/powershell.exe"
    assert powershell.is_file(), "The native Windows PowerShell contract requires its host interpreter"
    home = tmp_path / "home with spaces"
    home.mkdir()
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    }
    for key in ("HOME", "USERPROFILE", "TEMP", "TMP"):
        env[key] = str(home)
    for key, name in (("APPDATA", "Roaming"), ("LOCALAPPDATA", "Local")):
        directory = home / "AppData" / name
        directory.mkdir(parents=True)
        env[key] = str(directory)
    work = tmp_path / "job probe with spaces"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive",
         "-File", str(ROOT / "scripts/tests/test-update-job-termination.ps1"),
         "-RepoRoot", str(ROOT), "-Work", str(work),
         *(["-CompletedChild"] if completed_child else [])],
        cwd=ROOT, env=env, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=90, check=False,
    )
    (tmp_path / "probe.stdout.log").write_text(result.stdout, encoding="utf-8")
    (tmp_path / "probe.stderr.log").write_text(result.stderr, encoding="utf-8")
    receipt = work / "receipt.json"
    assert receipt.is_file(), result.stdout[-4000:] + result.stderr[-4000:]
    report = json.loads(receipt.read_text(encoding="utf-8-sig"))
    print("WINDOWS_JOB_PROBE=" + json.dumps(report, sort_keys=True))
    assert result.returncode == 0, json.dumps(report, sort_keys=True)
    assert report["status"] == "passed", report
    assert report["helper_returned_safe"] is True, report
    assert report["retired_job_refusals"] == 4, report
    assert not report["cleanup_errors"], report
    assert {"root", "child"} <= {row["role"] for row in report["observations"]}
    assert {row["pid"] for row in report["observations"]} == set(report["before"]["members"])
    assert all(row["wait_state"] == 0 and row["has_exited"] for row in report["observations"]), report
    if completed_child:
        assert report["history"]["before_wait_state"] == 258, report
        assert report["history"]["after_wait_state"] == 0, report
        assert report["history"]["completed_before_cancellation"] is True, report
        assert report["before"]["total"] > len(report["before"]["members"]), report
