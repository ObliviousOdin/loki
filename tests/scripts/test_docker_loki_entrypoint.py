"""Container startup binds public Loki overrides before shell bootstrap."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.platforms("posix")


def _image_declarations() -> tuple[dict[str, str], list[str]]:
    """Read image metadata, then execute its declared entry point below."""
    environment = {}
    entrypoint = []
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        if line.startswith("ENV "):
            for declaration in shlex.split(line.removeprefix("ENV ")):
                key, _, value = declaration.partition("=")
                if key.startswith(("LOKI_", "HERMES_", "__LOKI_")):
                    environment[key] = value
        elif line.startswith("ENTRYPOINT "):
            entrypoint = json.loads(line.removeprefix("ENTRYPOINT "))
    return environment, entrypoint


def _start_image(tmp_path: Path, overrides: dict[str, str]) -> tuple[dict, Path, Path]:
    image = tmp_path / "image"
    docker = image / "docker"
    docker.mkdir(parents=True)
    shutil.copy2(ROOT / "loki_identity.py", image / "loki_identity.py")
    bridge = ROOT / "docker" / "entrypoint-env.py"
    if bridge.exists():
        shutil.copy2(bridge, docker / bridge.name)
    dispatch = docker / "entrypoint-dispatch.sh"
    dispatch.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['PROBE_RECEIPT']).write_text(json.dumps({\n"
        " 'env':dict(os.environ), 'argv':sys.argv[1:], 'pid':os.getpid()}))\n"
    )
    dispatch.chmod(0o755)
    environment, declared = _image_declarations()
    owned_home = tmp_path / "home"
    owned_home.mkdir()
    foreign = tmp_path / "Hermes foreign"
    foreign.mkdir()
    canary = foreign / "config.yaml"
    canary.write_bytes(b"foreign-state-must-survive\n")
    receipt = tmp_path / "startup.json"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(owned_home),
        "PROBE_RECEIPT": str(receipt),
        **environment,
        "HERMES_HOME": str(foreign),
        "HERMES_RUNTIME_DIR": str(foreign / "runtime"),
        "HERMES_API_KEY": "foreign-placeholder-never-adopt",
        **overrides,
    }
    # Map immutable image locations into this disposable filesystem; execute
    # the actual bridge and a shell-bootstrap observer instead of real s6.
    command = [
        sys.executable
        if item == "/usr/local/bin/python3"
        else item.replace("/opt/hermes/", str(image) + "/")
        for item in declared
    ]
    argv = ["-p", "Hermes named profile", "chat", "--query", "literal $(noexec); value"]
    process = subprocess.Popen(
        [*command, *argv], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, (stdout, stderr)
    observed = json.loads(receipt.read_text())
    assert observed["argv"] == argv
    assert observed["pid"] == process.pid, (
        "binding must exec, preserving the container PID"
    )
    assert canary.read_bytes() == b"foreign-state-must-survive\n"
    assert sorted(path.name for path in foreign.iterdir()) == ["config.yaml"]
    assert list(owned_home.iterdir()) == [], (
        "binding imports must not initialize user state"
    )
    return observed["env"], foreign, image


@pytest.mark.parametrize("stale_marker", [False, True])
def test_container_public_overrides_reach_bootstrap_and_foreign_state_is_not_adopted(
    tmp_path, stale_marker
):
    own = tmp_path / "Loki own home"
    runtime = tmp_path / "Loki runtime"
    values = {
        "HOME": str(own),
        "RUNTIME_DIR": str(runtime),
        "PYTHON": "/chosen/python",
        "TUI_DIR": "/chosen/tui",
        "WEB_DIST": "/chosen/web",
        "WRITE_SAFE_ROOT": "/chosen/write",
    }
    overrides = {"LOKI_" + key: value for key, value in values.items()}
    if stale_marker:
        overrides["__LOKI_ENV_BOUND"] = "1"
    env, foreign, _ = _start_image(tmp_path, overrides)
    assert {key: env.get("HERMES_" + key) for key in values} == values
    assert env["__LOKI_ENV_BOUND"] == "1"
    assert "HERMES_API_KEY" not in env
    assert env["HERMES_HOME"] != str(foreign)


def test_container_default_paths_survive_first_loki_binding(tmp_path):
    env, _, _ = _start_image(tmp_path, {})
    expected = {
        "HOME": "/opt/data",
        "RUNTIME_DIR": "/opt/hermes/tools",
        "PYTHON": "/opt/hermes/.venv/bin/python",
        "TUI_DIR": "/opt/hermes/ui-tui",
        "WEB_DIST": "/opt/hermes/hermes_cli/web_dist",
        "WRITE_SAFE_ROOT": "/opt/data",
    }
    assert {key: env.get("HERMES_" + key) for key in expected} == expected
    assert env["__LOKI_ENV_BOUND"] == "1"
    assert "HERMES_API_KEY" not in env
