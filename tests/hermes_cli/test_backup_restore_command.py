"""Restore guidance passes one unchanged archive argument through the target shell."""

import json
from argparse import Namespace
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


@pytest.mark.platforms("posix")
def test_actual_backup_prints_a_copyable_path_with_spaces_and_shell_characters(tmp_path, monkeypatch, capsys):
    from hermes_cli.backup import run_backup

    home = tmp_path / ".loki"
    home.mkdir()
    (home / "config.yaml").write_text("model: fixture-model\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    archive = tmp_path / "Loki user's $HOME;$(printf injected)`printf inline`.zip"

    assert run_backup(Namespace(output=str(archive), keep=1)) is True

    hint = next(line.removeprefix("Restore with: ") for line in capsys.readouterr().out.splitlines()
                if line.startswith("Restore with: "))
    assert shlex.split(hint) == ["loki", "import", str(archive)]


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("archive", ["backup.zip", "/tmp/Loki user's/$HOME;$(printf injected)`printf backtick`.zip"])
def test_posix_restore_hint_passes_the_original_archive_argument(archive):
    from hermes_cli.backup_restore import _restore_command

    command = _restore_command(archive, powershell=False)
    assert shlex.split(command) == ["loki", "import", archive]
    probe = shlex.join([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))"])
    result = subprocess.run(["/bin/sh", "-c", probe + command.removeprefix("loki import")],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [archive]


def test_powershell_restore_hint_preserves_literal_metacharacters():
    from hermes_cli.backup_restore import _restore_command

    archive = "C:\\Loki user's\\$HOME;$(Write-Output injected)`t.zip"
    assert _restore_command(archive, powershell=True) == (
        "loki import 'C:\\Loki user''s\\$HOME;$(Write-Output injected)`t.zip'"
    )
    assert _restore_command("C:\\Loki ‘smart’ user’s\\backup.zip", powershell=True) == (
        "loki import 'C:\\Loki ‘‘smart’’ user’’s\\backup.zip'"
    )


@pytest.mark.platforms("windows")
@pytest.mark.parametrize("archive", ["C:\\Loki user's\\$HOME;$(Write-Output injected)`t.zip", "C:\\Loki ‘smart’ user’s\\backup.zip"])
def test_native_powershell_restore_hint_passes_one_archive_argument(archive):
    from hermes_cli.backup_restore import _restore_command

    powershell = shutil.which("pwsh") or shutil.which("powershell")
    assert powershell, "Windows qualification requires the installed PowerShell interpreter"
    argument = _restore_command(archive, powershell=True).removeprefix("loki import ")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command",
         "ConvertTo-Json -Compress -InputObject @(" + argument + ")"],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [archive]
