"""Shared helpers for the real-process Windows hand-off protocol tests (not collected)."""
from __future__ import annotations

import os
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import TextIO

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT = ROOT / 'scripts/desktop-update/windows.ps1'
MARKER_PS1 = ROOT / 'scripts/desktop-update/marker.ps1'
MARKER = '.hermes-update-in-progress'
POWERSHELL = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                          'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
HOLD_CLI = """
import os, sys, time
from pathlib import Path
def main():
    if '--version' in sys.argv:
        print('Install directory: ' + str(Path(__file__).resolve().parents[1])); return 0
    if '--help' in sys.argv:
        if os.environ.get('HANDOFF_HELP_READY'):
            ready = Path(os.environ['HANDOFF_HELP_READY'])
            pending = ready.with_suffix('.pending')
            pending.write_text(str(os.getpid()), encoding='utf-8')
            pending.replace(ready)
            release = Path(os.environ['HANDOFF_HELP_RELEASE'])
            while not release.exists():
                time.sleep(0.05)
        print('--keep-stash'); return 0
    if sys.argv[1:2] == ['update']:   # the update's first act: say so, then wait to be released
        hold = Path(os.environ['HANDOFF_HOLD'])
        Path(str(hold) + '.pid').write_text(str(os.getpid()), encoding='utf-8')
        while not hold.exists():
            time.sleep(0.05)
    return 0
if __name__ == '__main__':
    sys.exit(main())
"""


def _ps(command: str, timeout: int = 60) -> str:
    return subprocess.run([POWERSHELL, '-NoProfile', '-Command', command],
                          capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()


def _creation_time(pid: int) -> str:
    out = _ps(f"$c = (Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CreationDate; "
              "[DateTimeOffset]::new($c.ToUniversalTime()).ToUnixTimeMilliseconds().ToString()")
    return f'{int(out) / 1000:.3f}'


def _alive(pid: int) -> bool:
    return str(pid) in subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                                      capture_output=True, text=True, check=False).stdout


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait()
    return proc.pid


def _env(home: Path, **extra: str) -> dict[str, str]:
    return {**os.environ, 'LOKI_HOME': str(home), 'LOKI_RUNTIME_DIR': str(home / 'empty-store'), **extra}


def _script(home: Path, *args: str, install: Path | None = None,
            output: TextIO | None = None, **env: str) -> subprocess.Popen:
    return subprocess.Popen(
        [POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
         '-InstallRoot', str(install or home / 'hermes-agent'), '-NoUi', *args],
        cwd=home, env=_env(home, **env), stdout=output if output is not None else subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)


def _diagnostic_tail(path: Path, home: Path) -> dict:
    try:
        with path.open('rb') as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 16384))
            text = stream.read().decode('utf-8-sig', errors='replace')
    except OSError as error:
        return {'read_error': type(error).__name__}
    for root, label in ((home.parent, '<fixture>'), (ROOT, '<source>'),
                        (Path(sys.prefix), '<python>'), (Path(sys.base_prefix), '<base-python>')):
        text = text.replace(str(root), label)
    return {'bytes': size, 'tail': text}


def _marker_diagnostics(home: Path, proc: subprocess.Popen, output: Path) -> dict:
    """Only this live handoff's direct children; never inventory unrelated processes."""
    state = {'script_pid': proc.pid, 'script_exit': proc.poll(),
             'files': {name: _diagnostic_tail(home / name, home) for name in (
                 MARKER, '.hermes-update-result.json', 'logs/desktop-update-handoff.log')},
             'output': _diagnostic_tail(output, home)}
    if state['script_exit'] is None:
        command = (f"$ErrorActionPreference='Stop';$owner=Get-Process -Id {proc.pid};"
                   f"@(Get-CimInstance Win32_Process -Filter 'ParentProcessId={proc.pid}' | "
                   "Where-Object { $_.CreationDate -ge $owner.StartTime } | "
                   "Select-Object ProcessId,ParentProcessId,Name,CreationDate) | ConvertTo-Json -Compress")
        try:
            children = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Command', command],
                                      capture_output=True, text=True, timeout=5, check=False)
            state['children'] = {'query_exit': children.returncode,
                                 'rows': json.loads(children.stdout) if children.stdout.strip() else []}
        except (subprocess.TimeoutExpired, OSError, ValueError) as error:
            state['children'] = {'query_error': type(error).__name__}
    return state


def _stop_handoff(proc: subprocess.Popen) -> None:
    """Bound failure cleanup even if taskkill or an inherited output handle stalls."""
    if proc.poll() is not None:
        return
    try:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                       capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _finish(proc: subprocess.Popen, timeout: int = 120) -> tuple[int, str]:
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True, check=False)
        out, _ = proc.communicate()
        pytest.fail(f'hand-off did not finish within {timeout}s: {out}')
    return proc.returncode, out


def _op(home: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
         '-InstallRoot', str(home / 'hermes-agent'), *args],
        cwd=home, env=_env(home), capture_output=True, text=True, timeout=120, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _log(home: Path) -> str:
    """The hand-off log so far. windows.ps1 appends with Add-Content, which holds the file without
    read sharing for the length of each write: a read landing in that window is a sharing
    violation (PermissionError), not a missing line, so it is retried."""
    path = home / 'logs/desktop-update-handoff.log'
    for _ in range(50):
        try:
            return path.read_text(encoding='utf-8-sig') if path.exists() else ''
        except PermissionError:
            time.sleep(0.1)
    return path.read_text(encoding='utf-8-sig')


def _custodian(home: Path, handoff: int) -> str:
    """The pid windows.ps1 names on line 1 before any update work starts: its custodian, which
    outlives the hand-off so an old Desktop never reads a dead owner ('' until it is named)."""
    found = re.search(rf'names its custodian pid (\d+) \(hand-off pid {handoff}\)', _log(home))
    return found.group(1) if found else ''


class _HeldLock:
    """Hold the A7 sidecar lock from another process (this one): an open handle
    conflicts with the script's FileShare.None open."""

    def __init__(self, home: Path) -> None:
        deadline = time.monotonic() + 30
        while True:
            try:
                self._f = open(home / (MARKER + '.lock'), 'a+b')   # windows-footgun: ok — binary mode
                return
            except PermissionError:   # the script holds it right now
                assert time.monotonic() < deadline, 'never got the marker lock'
                time.sleep(0.02)

    def release(self) -> None:
        self._f.close()


def _wait_for_log(home: Path, needle: str, timeout: int = 90) -> str:
    deadline = time.monotonic() + timeout
    while needle not in _log(home):
        assert time.monotonic() < deadline, f'{needle!r} never logged: {_log(home)}'
        time.sleep(0.1)
    return _log(home)
