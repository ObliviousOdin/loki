"""Legacy image startup binds Loki before init captures its environment."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.platforms("posix")


@pytest.mark.parametrize("program", ["command", "init", "wrapper", "init-wrapper"])
def test_legacy_tini_binds_before_init_without_changing_pid_or_arguments(tmp_path, program):
    receipt = tmp_path / "init.json"
    init = tmp_path / "init"
    wrapper = tmp_path / "wrapper"
    init.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "keys = ('HERMES_HOME', 'HERMES_UID', 'HERMES_GID', "
        "'HERMES_GATEWAY_BOOTSTRAP_STATE', 'HERMES_DASHBOARD', '__LOKI_ENV_BOUND')\n"
        f"pathlib.Path({str(receipt)!r}).write_text(json.dumps({{\n"
        " 'argv':sys.argv[1:], 'pid':os.getpid(),\n"
        " 'env':{key:os.environ.get(key) for key in keys},\n"
        " 'foreign_key_present':'HERMES_API_KEY' in os.environ}))\n"
    )
    init.chmod(0o755)
    wrapper.write_text("#!/bin/sh\nexit 99\n")
    wrapper.chmod(0o755)
    # The image exposes /usr/bin/tini as a symlink to its source. Exercise
    # that invocation shape as well as the real shared startup binder.
    executable = tmp_path / "bin" / "tini"
    executable.parent.mkdir()
    executable.symlink_to(ROOT / "docker" / "tini-shim.sh")
    own = tmp_path / "Loki home"
    foreign = tmp_path / "Hermes foreign"
    foreign.mkdir()
    canary = foreign / "config.yaml"
    canary.write_bytes(b"foreign-state-must-survive\n")
    expected = {
        "HOME": str(own), "UID": "23456", "GID": "23457",
        "GATEWAY_BOOTSTRAP_STATE": "running", "DASHBOARD": "1",
    }
    env = {
        "PATH": os.environ["PATH"], "HOME": str(tmp_path),
        "HERMES_TINI_SHIM_TARGET": str(init),
        "HERMES_TINI_SHIM_WRAPPER": str(wrapper),
        "HERMES_HOME": str(foreign), "HERMES_UID": "foreign-uid",
        "HERMES_API_KEY": "foreign-placeholder-never-adopt", "__LOKI_ENV_BOUND": "1",
        **{"LOKI_" + key: value for key, value in expected.items()},
    }
    arguments = ["chat", "--query", "literal $(noexec); value", "", "two words"]
    prefix = {
        "command": [], "init": [str(init)], "wrapper": [str(wrapper)],
        "init-wrapper": [str(init), str(wrapper)],
    }[program]
    process = subprocess.Popen(
        ["sh", str(executable), "-g", "--", *prefix, *arguments],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, (stdout, stderr)
    observed = json.loads(receipt.read_text())
    expected_arguments = arguments if program == "init" else [str(wrapper), *arguments]
    assert observed["argv"] == expected_arguments
    assert observed["pid"] == process.pid
    assert observed["env"] == {
        **{"HERMES_" + key: value for key, value in expected.items()},
        "__LOKI_ENV_BOUND": "1",
    }
    assert observed["foreign_key_present"] is False
    assert canary.read_bytes() == b"foreign-state-must-survive\n"
    assert sorted(item.name for item in foreign.iterdir()) == ["config.yaml"]
    assert not own.exists(), "binding must not initialize user state"
