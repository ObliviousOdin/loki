"""Real subprocess output plumbing, without emulating the Windows handoff."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from tests.installation_launcher_fixture import publish_fixture_launcher
from tests.scripts.desktop_update import windows_handoff_support as support
from tests.waiting import wait_until


PRESSURE_CLI = r"""
import os, sys
from pathlib import Path
def main():
    ready = Path(os.environ['HANDOFF_OUTPUT_READY'])
    pending = ready.with_suffix('.pending')
    pending.write_text(str(os.getpid()), encoding='utf-8')
    pending.replace(ready)
    sys.stdout.write('x' * (2 * 1024 * 1024) + '\n')
    sys.stdout.flush()
    return 0
"""


@pytest.mark.parametrize('file_backed', [False, True], ids=['undrained-pipe', 'file-backed'])
def test_handoff_wait_requires_output_that_cannot_backpressure(tmp_path: Path, monkeypatch, file_backed: bool) -> None:
    # Select an inert executable at the command seam. Only Popen's stdout/wait
    # behavior is exercised; no PowerShell, marker, or Windows API is modeled.
    launcher = publish_fixture_launcher(tmp_path / 'checkout', PRESSURE_CLI)
    monkeypatch.setattr(support, 'POWERSHELL', str(launcher))
    home = tmp_path / 'home'
    home.mkdir()
    ready, output = tmp_path / 'ready', tmp_path / 'stdout.log'
    stream = output.open('w', encoding='utf-8') if file_backed else None
    try:
        child = support._script(home, output=stream, HANDOFF_OUTPUT_READY=str(ready))
    finally:
        if stream:
            stream.close()
    try:
        wait_until(lambda: ready.exists() or child.poll() is not None, timeout=10,
                   what='the real output writer to acknowledge startup')
        assert ready.exists() and int(ready.read_text()) > 0
        if file_backed:
            assert child.wait(timeout=10) == 0
            assert output.stat().st_size == 2 * 1024 * 1024 + len(os.linesep)
        else:
            with pytest.raises(subprocess.TimeoutExpired):
                child.wait(timeout=2)
            captured, _ = child.communicate(timeout=10)
            assert child.returncode == 0 and len(captured) == 2 * 1024 * 1024 + 1
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
