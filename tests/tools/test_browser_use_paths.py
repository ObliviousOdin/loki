"""Loki never attaches or reloads another product's browser-harness daemon."""

import json
import os
import sys
from pathlib import Path

import pytest

from tools import browser_use_cli as bu
from tools.browser_use_paths import harness_subprocess_env


@pytest.mark.platforms("posix", "windows")
def test_actual_harness_uses_owned_paths_and_preserves_foreign_pid(tmp_path, monkeypatch):
    home = tmp_path / "loki"
    monkeypatch.setenv("HERMES_HOME", str(home))
    foreign = tmp_path / "hermes-harness"
    foreign.mkdir()
    legacy_pid = foreign / "bu-research.pid"
    legacy_pid.write_text("foreign-daemon", encoding="utf-8")
    env = bu._base_subprocess_env() | {
        "BU_NAME": "research", "BH_HOME": str(foreign), "BH_CONFIG_DIR": str(foreign),
        "BROWSER_HARNESS_HOME": str(foreign), "BH_RUNTIME_DIR": str(foreign),
        "BH_TMP_DIR": str(foreign), "BH_RUNTIME_DIR_SHARED": "1", "BH_TMP_DIR_SHARED": "0",
    }
    probe = """import json
from browser_harness import _ipc, paths
print(json.dumps({'home':str(paths.home_dir()), 'config':str(paths.config_dir()),
 'pid':str(_ipc.pid_path('research')), 'tmp':str(paths.tmp_dir()),
 'existing_pid':_ipc.pid_path('research').exists()}))
"""
    child = bu._run_cli_killing_process_group([sys.executable, "-c", probe], "", env, 30)
    assert child.returncode == 0, child.stderr
    observed = json.loads(child.stdout)
    assert observed["home"] == str(home / "cache" / "browser-harness")
    assert observed["config"] == str(home / "cache" / "browser-harness" / "config")
    assert observed["tmp"] == str(home / "cache" / "browser-harness" / "tmp")
    assert observed["existing_pid"] is False
    assert Path(observed["pid"]).name == "bu.pid"
    assert "loki-browser" in observed["pid"]
    assert legacy_pid.read_text(encoding="utf-8") == "foreign-daemon"


def test_harness_namespaces_profiles_sessions_and_maximum_length_names(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile-a"))
    first = harness_subprocess_env({"BU_NAME": "x" * 64})
    assert first == harness_subprocess_env({"BU_NAME": "x" * 64})
    second = harness_subprocess_env({"BU_NAME": "different"})
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile-b"))
    third = harness_subprocess_env({"BU_NAME": "x" * 64})
    assert len({entry["BH_RUNTIME_DIR"] for entry in (first, second, third)}) == 3
    if os.name != "nt":
        assert len(os.fsencode(str(Path(first["BH_RUNTIME_DIR"]) / "bu.sock"))) < 104
        assert Path(first["BH_RUNTIME_DIR"]).stat().st_mode & 0o777 == 0o700
    assert first["BH_RUNTIME_DIR_SHARED"] == "0"


@pytest.mark.platforms("posix")
def test_harness_refuses_foreign_runtime_symlink(tmp_path, monkeypatch):
    from tools import browser_tool
    monkeypatch.setattr(browser_tool, "_socket_safe_tmpdir", lambda: str(tmp_path))
    env = harness_subprocess_env({})
    runtime = Path(env["BH_RUNTIME_DIR"])
    runtime.rmdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    sentinel = foreign / "keep"
    sentinel.write_text("preserve", encoding="utf-8")
    runtime.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Refusing unowned Loki"):
        harness_subprocess_env({})
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_own_tab_marker_is_owned_and_only_pins_once(tmp_path, monkeypatch):
    from browser_harness import _ipc
    runtime = tmp_path / "owned"
    runtime.mkdir()
    pid = tmp_path / "daemon.pid"
    pid.write_text("123", encoding="utf-8")
    monkeypatch.setattr(_ipc, "pid_path", lambda _: pid)
    monkeypatch.setenv("BH_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("BU_NAME", "research")
    legacy = tmp_path / "hermes-bu-owntab-foreign"
    legacy.write_text("preserve", encoding="utf-8")
    created, switched = [], []
    scope = {"cdp": lambda *args, **kwargs: created.append(args) or {"targetId": "owned-tab"},
             "switch_tab": switched.append}
    exec(bu._OWN_TAB_PREAMBLE, scope)
    exec(bu._OWN_TAB_PREAMBLE, scope)
    assert len(created) == 1
    assert switched == ["owned-tab"]
    assert (runtime / "own-tab-research-123").exists()
    assert legacy.read_text(encoding="utf-8") == "preserve"


def test_reload_reaches_every_owned_profile_daemon(tmp_path, monkeypatch):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    homes = [tmp_path / "profile-a", tmp_path / "profile-b"]
    runtimes = []
    for home in homes:
        token = set_hermes_home_override(home)
        try:
            runtimes.append(Path(harness_subprocess_env({"BU_NAME": "research"})["BH_RUNTIME_DIR"]))
        finally:
            reset_hermes_home_override(token)
    probe = tmp_path / "reload.py"
    probe.write_text("import os, pathlib\npathlib.Path(os.environ['BH_RUNTIME_DIR'], 'reload').write_text('owned')\n",
                     encoding="utf-8")
    monkeypatch.setattr(bu, "_find_cli", lambda: [sys.executable, str(probe)])
    monkeypatch.setattr(bu, "_driven_daemons", {(str(home), "research") for home in homes})
    bu.stop_harness_daemons()
    assert all((runtime / "reload").read_text(encoding="utf-8") == "owned" for runtime in runtimes)
    assert not bu._driven_daemons
