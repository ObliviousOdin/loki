"""Generated s6 gateways execute Loki's installed operator command."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import loki_identity
import pytest

from hermes_cli.service_manager import S6ServiceManager


@pytest.mark.platforms("posix")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="this contract executes the unprivileged service branch")
@pytest.mark.parametrize("profile", ["default", "writer"])
def test_generated_service_executes_owned_command_and_preserves_supervision(tmp_path, profile):
    binaries = tmp_path / "installed commands"
    binaries.mkdir()
    receipt = tmp_path / "invocation.json"
    owned = binaries / "loki"
    owned.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        f"sys.path.insert(0, {str(Path(loki_identity.__file__).resolve().parent)!r})\n"
        "from loki_identity import bind_loki_environment\n"
        "bind_loki_environment()\n"
        "pathlib.Path(os.environ['SERVICE_PROBE_RECEIPT']).write_text(json.dumps({\n"
        " 'argv': sys.argv[1:],\n"
        " 's6_child': os.environ['HERMES_S6_SUPERVISED_CHILD'],\n"
        " 'supervised_child': os.environ['HERMES_SUPERVISED_CHILD']}))\n",
        encoding="utf-8",
    )
    owned.chmod(0o755)
    foreign = binaries / "hermes"
    foreign.write_text("#!/bin/sh\nexit 98\n", encoding="utf-8")
    foreign.chmod(0o755)
    script = tmp_path / "run"
    script.write_text(S6ServiceManager._render_run_script(
        profile, {"SERVICE_PROBE_RECEIPT": str(receipt)}), encoding="utf-8")
    # The real generated command runs on this host. Only the container's fixed
    # working directory is substituted; no host /opt/data is created or changed.
    result = subprocess.run(
        ["/bin/sh", "-c", 'cd() { [ "$1" = /opt/data ]; }; . "$1"', "--", str(script)],
        env={"PATH": str(binaries) + os.pathsep + "/usr/bin:/bin"},
        cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    observed = json.loads(receipt.read_text(encoding="utf-8"))
    selection = [] if profile == "default" else ["-p", profile]
    assert observed == {
        "argv": [*selection, "gateway", "run", "--replace"],
        "s6_child": "1", "supervised_child": "1",
    }
