"""Observe live handoff logs without turning Windows sharing into readiness."""
from pathlib import Path
import subprocess

import pytest

from tests.scripts.desktop_update.windows_handoff_support import POWERSHELL, _log_contains
from tests.waiting import wait_until


NEEDLE = 'keeping the update marker'
DENY_READ = """
param([string]$LogPath, [string]$ReadyPath)
$ErrorActionPreference = 'Stop'
$stream = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
try {
    [System.IO.File]::WriteAllText("$ReadyPath.pending", [string]$PID)
    [System.IO.File]::Move("$ReadyPath.pending", $ReadyPath)
    if ([Console]::ReadLine() -ne 'release') { throw 'missing controller release' }
} finally {
    $stream.Dispose()
}
"""


def test_log_readiness_requires_existing_matching_text(tmp_path: Path) -> None:
    assert not _log_contains(tmp_path, NEEDLE)
    log = tmp_path / 'logs/desktop-update-handoff.log'
    log.parent.mkdir()
    log.write_text('keeping the update', encoding='utf-8-sig')
    assert not _log_contains(tmp_path, NEEDLE)
    log.write_text(NEEDLE + '\n', encoding='utf-8-sig')
    assert _log_contains(tmp_path, NEEDLE)
    assert not _log_contains(tmp_path, 'a different phase')


@pytest.mark.platforms('windows')
def test_log_readiness_is_false_while_windows_denies_reads_then_recovers(tmp_path: Path) -> None:
    log = tmp_path / 'logs/desktop-update-handoff.log'
    log.parent.mkdir()
    content = 'a process still holds the checkout update lock; ' + NEEDLE + ' until it exits\n'
    log.write_text(content, encoding='utf-8-sig')
    script = tmp_path / 'deny-log-read.ps1'
    script.write_text(DENY_READ, encoding='utf-8-sig')
    ready = tmp_path / 'writer.ready'
    child = subprocess.Popen(
        [POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script),
         '-LogPath', str(log), '-ReadyPath', str(ready)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8')
    try:
        wait_until(lambda: ready.exists() or child.poll() is not None, timeout=10,
                   what='the real Windows file handle to deny reads')
        assert ready.exists() and child.poll() is None, child.communicate(timeout=10)
        assert int(ready.read_text(encoding='utf-8-sig')) == child.pid
        # Calibrate the same primitive that failed at C0, using the actual host.
        with pytest.raises(PermissionError):
            log.read_text(encoding='utf-8-sig')

        def waiting_on_live_writer() -> bool:
            assert child.poll() is None, 'writer exited before controller release'
            return _log_contains(tmp_path, NEEDLE)

        assert not waiting_on_live_writer()
        with pytest.raises(AssertionError, match='waiting for R6 readiness under a denied read'):
            wait_until(waiting_on_live_writer, timeout=2,
                       what='R6 readiness under a denied read')
        assert child.poll() is None, 'denial must not release the writer or make readiness pass'
        output, _ = child.communicate(input='release\n', timeout=10)
        assert child.returncode == 0, output
        assert log.read_text(encoding='utf-8-sig') == content
        assert _log_contains(tmp_path, NEEDLE)
        assert not _log_contains(tmp_path, 'a different phase')
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
        child.wait(timeout=10)
