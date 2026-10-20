"""A7 on the real Windows hand-off script: every marker mutation happens inside one
hold of the kernel lock on ``<marker>.lock`` and the update child is the marker's
delegate before it runs a single instruction.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from tests.installation_launcher_fixture import publish_fixture_launcher
from tests.scripts.desktop_update.windows_handoff_support import (
    MARKER,
    POWERSHELL,
    HOLD_CLI,
    _creation_time,
    _alive,
    _dead_pid,
    _script,
    _finish,
    _op,
    _HeldLock,
    _HelpGate,
    _custodian,
    _marker_diagnostics,
    _stop_handoff,
)


@pytest.fixture
def sleeper():
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
    yield proc
    proc.kill()
    proc.wait()


# -- A7 ---------------------------------------------------------------------

@pytest.mark.platforms('windows')
def test_a7_claim_is_decided_inside_the_marker_lock(tmp_path: Path, sleeper: subprocess.Popen) -> None:
    """While another process holds <marker>.lock the claimant must not touch a dead marker;
    once the holder (which replaced it with a live claim meanwhile) lets go, it judges THAT."""
    dead = f'{_dead_pid()}\n{int(time.time())}\nct:5.000\n'.encode()
    marker = tmp_path / MARKER
    marker.write_bytes(dead)
    lock = _HeldLock(tmp_path)
    try:
        claimant = _script(tmp_path, '-SelfTestMarker', '-NoMarkerCleanup')
        time.sleep(5)   # PowerShell start-up plus a few lock retries
        assert claimant.poll() is None, 'claimant did not wait for the marker lock'
        assert marker.read_bytes() == dead, 'a dead marker was mutated outside the marker lock'
        live = f'{sleeper.pid}\n{int(time.time())}\nct:{_creation_time(sleeper.pid)}\n'.encode()
        marker.write_bytes(live)   # the lock holder's own decision: a new live claim
    finally:
        lock.release()
    code, out = _finish(claimant)
    assert code == 2, out
    assert marker.read_bytes() == live


def _finish_claimants(home: Path, claimants: list[subprocess.Popen], outputs: list[Path]) -> None:
    timed_out = []
    for claimant, output in zip(claimants, outputs):
        try:
            claimant.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out.append(_marker_diagnostics(home, claimant, output))
    assert not timed_out, json.dumps({'claimants_did_not_finish': timed_out}, ensure_ascii=True)


@pytest.mark.platforms('windows')
@pytest.mark.parametrize('output_bytes', [0, 256 * 1024], ids=['ordinary', 'stdout-pressure'])
def test_a7_concurrent_claimants_over_a_dead_marker_yield_one_owner(tmp_path: Path, output_bytes: int) -> None:
    install = tmp_path / 'checkout'
    publish_fixture_launcher(install, HOLD_CLI)
    home = tmp_path / 'home'; home.mkdir()
    marker = home / MARKER
    marker.write_bytes(f'{_dead_pid()}\n{int(time.time())}\nct:5.000\n'.encode())
    hold = tmp_path / 'release-update'
    lock = _HeldLock(home)   # line every claimant up behind the lock, then let them race
    outputs = [tmp_path / f'claimant-{index}.stdout.log' for index in range(4)]
    claimants = []
    with ExitStack() as streams:
        try:
            for output in outputs:
                # No reader runs while we wait for the competing owners. A pipe
                # here can block the real script before it exits or cleans up.
                stream = streams.enter_context(output.open('w', encoding='utf-8'))
                claimants.append(_script(home, install=install, output=stream,
                                         HANDOFF_HOLD=str(hold), HANDOFF_OUTPUT_BYTES=str(output_bytes)))
                streams.callback(_stop_handoff, claimants[-1])
            time.sleep(6)
            lock.release()
            deadline = time.monotonic() + 120
            while not Path(str(hold) + '.pid').exists():
                assert time.monotonic() < deadline, 'no claimant reached the update'
                time.sleep(0.05)
            while sum(c.poll() is not None for c in claimants) < 3:
                assert time.monotonic() < deadline, [c.poll() for c in claimants]
                time.sleep(0.1)
            refused = [c for c in claimants if c.poll() == 2]
            running = [c for c in claimants if c.poll() is None]
            assert len(running) == 1 and len(refused) == 3, [c.returncode for c in claimants]
            assert marker.read_bytes().decode().split('\n')[0] == _custodian(home, running[0].pid)
        except BaseException as error:
            snapshots = [_marker_diagnostics(home, child, output) for child, output in zip(claimants, outputs)]
            error.add_note(json.dumps({'claimants': snapshots}, ensure_ascii=True))
            raise
        finally:
            lock.release()
            hold.touch()
            _finish_claimants(home, claimants, outputs)
    assert running[0].returncode == 0
    assert not marker.exists()
    if output_bytes:
        assert any(output.stat().st_size >= output_bytes for output in outputs)


# -- the update child is the delegate before it runs anything ------------------

FIND_UPDATE_CHILD = r"""
param([int]$Parent, [int]$Seconds)
$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
    $row = Get-CimInstance Win32_Process -Filter "ParentProcessId=$Parent" |
        Where-Object { $_.CommandLine -match '--yes' } | Select-Object -First 1
    if ($row) { [Console]::Out.Write($row.ProcessId); exit 0 }
    Start-Sleep -Milliseconds 100
}
exit 1
"""


@pytest.mark.platforms('windows')
def test_script_killed_before_publishing_the_delegate_runs_no_update(tmp_path: Path) -> None:
    """Kill cell at the pre-publication boundary: windows.ps1 has created its `hermes update`
    child but has not published it as the marker delegate (the marker lock is held elsewhere).
    Killed there, no update instruction may have run, and the custodian line 1 names releases
    the marker (nothing holds the checkout)."""
    install = tmp_path / 'checkout'
    publish_fixture_launcher(install, HOLD_CLI)
    home = tmp_path / 'home'; home.mkdir()
    hold = tmp_path / 'release-update'
    ran = Path(str(hold) + '.pid')
    marker = home / MARKER
    finder = tmp_path / 'find_child.ps1'
    finder.write_text(FIND_UPDATE_CHILD, encoding='utf-8')
    ready = tmp_path / 'help.ready'
    output = tmp_path / 'handoff.stdout.log'
    with _HelpGate(ready) as gate, output.open('w', encoding='utf-8') as stream:
        script = _script(home, install=install, output=stream, HANDOFF_HOLD=str(hold),
                         **gate.env)
        lock = None
        try:
            deadline = time.monotonic() + 60
            while not (marker.exists() and _custodian(home, script.pid)
                       and marker.read_bytes().split(b'\n')[0] == _custodian(home, script.pid).encode()
                       and ready.exists()):
                assert time.monotonic() < deadline and script.poll() is None, 'custodian/help boundary never became ready'
                time.sleep(0.02)
            # The real help probe acknowledges it is paused before updater creation.
            # Observing a custodian alone left a race with delegate publication.
            assert gate.wait_ready(timeout=deadline - time.monotonic()) == int(ready.read_text())
            lock = _HeldLock(home)
            assert not ran.exists() and not any(line.startswith(b'delegate:') for line in marker.read_bytes().splitlines())
            gate.release()
            child = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(finder),
                                    '-Parent', str(script.pid), '-Seconds', '60'],
                                   capture_output=True, text=True, timeout=90, check=False)
            assert child.returncode == 0, 'the update child never appeared'
            child_pid = int(child.stdout)
            subprocess.run(['taskkill', '/F', '/PID', str(script.pid)], capture_output=True, check=True)
            script.wait(timeout=30)
            time.sleep(3)
            assert not ran.exists(), 'the update child ran before it was published as the delegate'
            assert not _alive(child_pid), 'the never-resumed update child outlived its script'
            lines = marker.read_bytes().decode().split('\n')
            assert lines[0] == _custodian(home, script.pid), lines
            assert not any(line.startswith('delegate:') for line in lines), lines
        except BaseException as error:
            snapshot = _marker_diagnostics(home, script, output)
            snapshot['help_ready'] = ready.exists()
            snapshot['help_released'] = gate.released
            snapshot['update_entered'] = ran.exists()
            text = json.dumps(snapshot, ensure_ascii=True, indent=2)
            (tmp_path / 'marker-failure.json').write_text(text, encoding='utf-8')
            error.add_note(text)
            raise
        finally:
            if lock:
                lock.release()
            gate.close()
            hold.touch()
            _stop_handoff(script)
    deadline = time.monotonic() + 60   # the custodian releases the marker once the lock is free
    while (verdict := _op(home, '-MarkerOp', 'reclaim')[1]).startswith('live '):
        assert time.monotonic() < deadline
        time.sleep(0.2)
    assert verdict in ('absent\n', 'reclaimed\n')
