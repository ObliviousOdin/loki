"""Loki's first-entry boundary keeps ambient Hermes state outside the fork."""

from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

from loki_identity import ENV_BOUND, bind_loki_environment, default_home


def test_fresh_entry_discards_ambient_hermes_state(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    env = {"HERMES_HOME": str(tmp_path / "old-hermes"), "HERMES_RUNTIME_DIR": "/old/runtime",
           "HERMES_SHARED_AUTH_DIR": "/old/auth", "HERMES_CUSTOM_API_KEY": "old-secret",
           "__HERMES_ACTIVATED": "/old/environment", "PATH": "/bin"}
    bind_loki_environment(env)
    assert env["HERMES_HOME"] == str(default_home(env))
    assert not ({"HERMES_RUNTIME_DIR", "HERMES_SHARED_AUTH_DIR", "HERMES_CUSTOM_API_KEY",
                 "__HERMES_ACTIVATED"} & env.keys())
    assert env[ENV_BOUND] == "1"
    assert env["PATH"] == "/bin"


def test_owned_overrides_win_and_children_keep_the_active_profile(tmp_path):
    env = {"HERMES_HOME": "/old/home", "LOKI_HOME": str(tmp_path),
           "LOKI_RUNTIME_DIR": str(tmp_path / "tools")}
    bind_loki_environment(env)
    assert env["HERMES_HOME"] == str(tmp_path)
    assert env["HERMES_RUNTIME_DIR"] == str(tmp_path / "tools")
    env["HERMES_HOME"] = str(tmp_path / "profiles" / "work")
    bind_loki_environment(env)
    assert env["HERMES_HOME"] == str(tmp_path / "profiles" / "work")


@pytest.mark.platforms("posix")
def test_posix_default_is_loki(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert default_home({}) == tmp_path / ".loki"
    assert default_home({"LOKI_DATA_DIR_SUFFIX": "-preview"}) == tmp_path / ".loki-preview"


@pytest.mark.platforms("windows")
def test_windows_default_is_loki(tmp_path):
    assert default_home({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "loki"


def test_internal_profile_override_remains_a_runtime_seam(tmp_path, monkeypatch):
    from hermes_constants import get_default_hermes_root, get_hermes_home

    home = tmp_path / "loki" / "profiles" / "work"
    monkeypatch.setenv("HERMES_HOME", str(home))
    assert get_hermes_home() == home
    assert get_default_hermes_root() == tmp_path / "loki"


def test_persisted_runtime_command_does_not_promote_a_foreign_home(tmp_path):
    from hermes_cli._launchers import runtime_command

    # Execute the real generated launcher and environment binder against a tiny
    # stdlib-only runtime fixture: dependency activation is a separate PM contract.
    fixture = tmp_path / "runtime"
    fixture.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[1] / "loki_identity.py", fixture)
    (fixture / "hermes_bootstrap.py").write_text(
        "from loki_identity import bind_loki_environment\nbind_loki_environment()\n", encoding="utf-8")
    owned = tmp_path / "owned-loki"
    env = {**os.environ, "HERMES_HOME": str(tmp_path / "foreign-hermes")}
    env.pop(ENV_BOUND, None)
    command = runtime_command(fixture, python=sys.executable, home=owned,
                              code="print(os.environ['HERMES_HOME'])")
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == str(owned)
    env[ENV_BOUND] = "1"
    env["HERMES_HOME"] = str(owned / "profiles" / "work")
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == env["HERMES_HOME"]


def test_provider_client_identity_uses_the_product_version_not_the_inherited_sdk():
    from loki_identity import CLIENT_USER_AGENT, PRODUCT_NAME, UPSTREAM_SDK_VERSION, VERSION

    assert CLIENT_USER_AGENT == f"{PRODUCT_NAME}/{VERSION}"
    assert UPSTREAM_SDK_VERSION not in CLIENT_USER_AGENT
