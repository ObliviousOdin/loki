"""Portable installer embedding contract; native suite also requires PS5.1 and 7."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


SUITE = Path(__file__).resolve().parents[3] / "scripts/tests/test-install-ps1-dot-source.ps1"


def test_dot_source_preserves_caller_environment():
    powershell = shutil.which("pwsh")
    if powershell is None:
        pytest.skip("Portable PowerShell is unavailable; native Windows suite requires both shells")
    environment = dict(os.environ, POWERSHELL_TELEMETRY_OPTOUT="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SUITE)],
        env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DOT_SOURCE_ENVIRONMENT_OK" in result.stdout
