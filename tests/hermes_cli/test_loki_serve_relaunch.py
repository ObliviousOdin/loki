"""Manual backend recovery must launch Loki even beside foreign Hermes shims."""

import subprocess
from types import SimpleNamespace

import pytest

from hermes_cli import update_cmd, update_cmd_windows


ENTRY = {"purpose": "serve", "profile": "owned profile", "host": "127.0.0.1", "port": 9123}
TAIL = ["--profile", "owned profile", "serve", "--host", "127.0.0.1", "--port", "9123"]


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    scripts = tmp_path / "runtime scripts"
    scripts.mkdir()
    spawned, steps = [], []
    facade = SimpleNamespace(
        _venv_scripts_dir=lambda: scripts,
        _respawn_dashboard_processes=lambda commands: spawned.append(commands) or [],
    )
    monkeypatch.setattr(update_cmd, "_m", lambda: facade)
    monkeypatch.setattr(update_cmd, "_record_update_step", lambda *args: steps.append(args))
    return scripts, facade, spawned, steps


@pytest.mark.parametrize("launcher", ["loki.exe", "loki"])
def test_relaunch_prefers_owned_runtime_launcher(runtime, launcher):
    scripts, _facade, _spawned, _steps = runtime
    own = scripts / launcher
    own.write_bytes(b"Owned launcher canary; command construction only.\n")
    foreign = {scripts / name: b"Foreign launcher must remain untouched.\n" for name in ("hermes.exe", "hermes")}
    for path, data in foreign.items():
        path.write_bytes(data)

    assert update_cmd_windows._serve_relaunch_commands([ENTRY]) == [[str(own), *TAIL]]
    assert {path: path.read_bytes() for path in foreign} == foreign


@pytest.mark.parametrize("foreign_name", ["hermes.exe", "hermes"])
def test_foreign_only_runtime_shim_never_reaches_respawn(runtime, foreign_name):
    scripts, _facade, spawned, steps = runtime
    foreign = scripts / foreign_name
    contents = b"Foreign launcher must never execute or change.\n"
    foreign.write_bytes(contents)
    token = {"pending": True, "entries": [ENTRY]}

    update_cmd_windows._relaunch_stopped_serves(token)
    update_cmd_windows._relaunch_stopped_serves(token)

    assert spawned == [[["loki", *TAIL]]]
    assert token["pending"] is False
    assert steps == [("serve_relaunch", True, "relaunched=1 failed=0 skipped=0")]
    assert foreign.read_bytes() == contents


def test_relaunch_keeps_ledger_validation_and_default_profile(runtime):
    entries = [dict(ENTRY, port=value) for value in (None, "9123", 0, -1)]
    entries.append(dict(ENTRY, purpose="dashboard", profile="default", host="::1"))

    assert update_cmd_windows._serve_relaunch_commands(entries) == [
        ["loki", "dashboard", "--host", "::1", "--port", "9123"]
    ]


@pytest.mark.platforms("posix")
def test_selected_owned_posix_launcher_executes_with_exact_ledger_arguments(runtime):
    scripts, _facade, _spawned, _steps = runtime
    own = scripts / "loki"
    own.write_text('#!/bin/sh\nprintf "owned\\n"\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    own.chmod(0o700)
    foreign = scripts / "hermes"
    foreign.write_bytes(b"Foreign canary must not execute.\n")

    command = update_cmd_windows._serve_relaunch_commands([ENTRY])[0]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["owned", *TAIL]
    assert foreign.read_bytes() == b"Foreign canary must not execute.\n"


def test_failed_relaunch_names_loki_for_manual_recovery(runtime, capsys):
    _scripts, facade, _spawned, steps = runtime
    facade._respawn_dashboard_processes = list

    update_cmd_windows._relaunch_stopped_serves({"pending": True, "entries": [ENTRY]})

    assert "loki serve --host <ip> --port <port>" in capsys.readouterr().out
    assert steps == [("serve_relaunch", False, "relaunched=0 failed=1 skipped=0")]
