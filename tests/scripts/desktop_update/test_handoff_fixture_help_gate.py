"""The inert launcher can hold the real handoff before updater creation."""
import os
import json
from pathlib import Path
import subprocess
import sys

from tests.installation_launcher_fixture import publish_fixture_launcher
from tests.scripts.desktop_update.windows_handoff_support import HOLD_CLI, MARKER, _HelpGate, _marker_diagnostics


def test_help_probe_waits_for_controller_release_before_the_update(tmp_path: Path) -> None:
    launcher = publish_fixture_launcher(tmp_path / 'checkout', HOLD_CLI)
    ready = tmp_path / 'help.ready'
    update = tmp_path / 'update.release'
    with _HelpGate(ready) as gate:
        env = {**os.environ, **gate.env, 'HANDOFF_HOLD': str(update)}
        proc = subprocess.Popen([str(launcher), 'update', '--help'], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            pid = gate.wait_ready(timeout=10)
            assert pid == int(ready.read_text()) and proc.poll() is None, 'help ran past the controller gate'
            assert not Path(str(update) + '.pid').exists()
            gate.release()
            out, _ = proc.communicate(timeout=10)
            assert proc.returncode == 0 and out.strip() == '--keep-stash', out
            assert not Path(str(update) + '.pid').exists()
        finally:
            gate.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)


def test_controller_disconnect_cancels_help_before_the_update(tmp_path: Path) -> None:
    launcher = publish_fixture_launcher(tmp_path / 'checkout', HOLD_CLI)
    update = tmp_path / 'update.release'
    with _HelpGate(tmp_path / 'help.ready') as gate:
        env = {**os.environ, **gate.env, 'HANDOFF_HOLD': str(update)}
        proc = subprocess.Popen([str(launcher), 'update', '--help'], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            gate.wait_ready(timeout=10)
            assert proc.poll() is None and not Path(str(update) + '.pid').exists()
            gate.close()
            out, _ = proc.communicate(timeout=10)
            assert proc.returncode != 0 and not out.strip(), out
            assert not Path(str(update) + '.pid').exists()
        finally:
            gate.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)


def test_uncontrolled_help_probe_keeps_its_original_behavior(tmp_path: Path) -> None:
    launcher = publish_fixture_launcher(tmp_path / 'checkout', HOLD_CLI)
    env = {key: value for key, value in os.environ.items() if not key.startswith('HANDOFF_')}
    result = subprocess.run([str(launcher), 'update', '--help'], env=env,
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0 and result.stdout.strip() == '--keep-stash', result.stdout + result.stderr


def test_exited_handoff_diagnostics_retain_phase_and_redact_fixture_paths(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    (home / 'logs').mkdir(parents=True)
    (home / MARKER).write_text('123\n456\nct:7.000\n')
    (home / 'logs/desktop-update-handoff.log').write_text(f'claimed marker under {home}\n')
    output = tmp_path / 'stdout.log'
    output.write_text(f'pre-custodian output {tmp_path}\n')
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait(timeout=10)
    snapshot = _marker_diagnostics(home, child, output)
    assert snapshot['script_exit'] == 0 and 'children' not in snapshot
    assert snapshot['files'][MARKER]['tail'] == '123\n456\nct:7.000\n'
    assert snapshot['files']['.hermes-update-result.json'] == {'read_error': 'FileNotFoundError'}
    text = json.dumps(snapshot)
    assert str(tmp_path) not in text and '<fixture>' in text
    assert 'pre-custodian output' in text and 'claimed marker' in text
