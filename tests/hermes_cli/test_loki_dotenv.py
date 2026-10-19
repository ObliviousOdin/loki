"""Public Loki dotenv settings share the retained runtime's scoping and precedence."""

import os

import pytest

from agent.secret_scope import load_env_file
from hermes_cli.env_loader import (
    _load_dotenv_with_fallback,
    launch_dotenv_keys,
    load_hermes_dotenv,
    managed_dotenv_keys,
)
from loki_identity import ENV_BOUND, bind_loki_environment
from utils import env_float


@pytest.fixture
def owned_profile(tmp_path, monkeypatch):
    home = tmp_path / ".loki" / "profiles" / "work"
    home.mkdir(parents=True)
    monkeypatch.setenv(ENV_BOUND, "1")
    monkeypatch.setenv("LOKI_HOME", str(tmp_path / ".loki"))
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_MULTIPLEX_PROFILES", "0")
    return home


def test_public_timeout_reaches_runtime_without_rebinding_active_profile(owned_profile):
    (owned_profile / ".env").write_text("LOKI_API_TIMEOUT=73\n", encoding="utf-8")
    load_hermes_dotenv(load_external_secrets=False)
    assert env_float("HERMES_API_TIMEOUT", 1800.0) == 73.0
    assert os.environ["HERMES_HOME"] == str(owned_profile)
    assert {"LOKI_API_TIMEOUT", "HERMES_API_TIMEOUT"} <= launch_dotenv_keys()


def test_public_profile_behavior_is_not_scrubbed_as_undefined(owned_profile):
    (owned_profile / ".env").write_text("LOKI_ACP_AUTH_METHOD=oauth\n", encoding="utf-8")
    load_hermes_dotenv(load_external_secrets=False)
    assert os.environ["HERMES_ACP_AUTH_METHOD"] == "oauth"
    assert load_env_file(owned_profile / ".env")["HERMES_ACP_AUTH_METHOD"] == "oauth"


@pytest.mark.parametrize("public_defined", [False, True])
def test_public_dotenv_cannot_replace_parent_minted_session_token(owned_profile, monkeypatch, public_defined):
    monkeypatch.setenv("HERMES_DASHBOARD_SESSION_TOKEN", "parent-minted-fixture")
    if public_defined:
        monkeypatch.setenv("LOKI_DASHBOARD_SESSION_TOKEN", "parent-minted-fixture")
    else:
        monkeypatch.delenv("LOKI_DASHBOARD_SESSION_TOKEN", raising=False)
    (owned_profile / ".env").write_text("LOKI_DASHBOARD_SESSION_TOKEN=stale-file-fixture\n", encoding="utf-8")
    load_hermes_dotenv(load_external_secrets=False)
    assert os.environ["HERMES_DASHBOARD_SESSION_TOKEN"] == "parent-minted-fixture"
    assert os.environ["LOKI_DASHBOARD_SESSION_TOKEN"] == "parent-minted-fixture"
    # Native launchers carry the bound profile, then rebind their owned payload selectors.
    child = {**os.environ, "LOKI_HOME": os.environ["HERMES_HOME"]}
    child.pop(ENV_BOUND)
    bind_loki_environment(child)
    assert child["HERMES_DASHBOARD_SESSION_TOKEN"] == "parent-minted-fixture"
    assert child["HERMES_HOME"] == str(owned_profile)


def test_public_layer_precedence_and_reload_interpolation_are_stable(owned_profile, tmp_path, monkeypatch):
    monkeypatch.setenv("LOKI_API_TIMEOUT", "19")
    monkeypatch.setenv("HERMES_API_TIMEOUT", "19")
    (owned_profile / ".env").write_text("LOKI_API_TIMEOUT=${LOKI_API_TIMEOUT:-7}3\n", encoding="utf-8")
    project = tmp_path / "project.env"
    project.write_text("LOKI_API_TIMEOUT=11\n", encoding="utf-8")
    for _ in range(3):
        load_hermes_dotenv(project_env=project, load_external_secrets=False)
        assert os.environ["LOKI_API_TIMEOUT"] == os.environ["HERMES_API_TIMEOUT"] == "193"


def test_readonly_public_alias_wins_in_same_layer_without_mutating_process(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_API_TIMEOUT", "outside-fixture")
    path = tmp_path / ".env"
    path.write_text("LOKI_API_TIMEOUT=73\nHERMES_API_TIMEOUT=19\n", encoding="utf-8")
    values = load_env_file(path)
    assert values["LOKI_API_TIMEOUT"] == values["HERMES_API_TIMEOUT"] == "73"
    assert os.environ["HERMES_API_TIMEOUT"] == "outside-fixture"


def test_managed_aliases_retain_managed_provenance(tmp_path):
    path = tmp_path / "managed.env"
    path.write_text("LOKI_NAMESPACE_POLICY_FIXTURE=managed\n", encoding="utf-8")
    _load_dotenv_with_fallback(path, override=True, managed=True)
    names = {"LOKI_NAMESPACE_POLICY_FIXTURE", "HERMES_NAMESPACE_POLICY_FIXTURE"}
    assert names <= managed_dotenv_keys()
    assert not names & launch_dotenv_keys()


def test_routed_child_uses_only_its_own_public_aliases(tmp_path, monkeypatch):
    from tools.environments.local import served_profile_child_env

    root = tmp_path / ".loki"
    profile = root / "profiles" / "work"
    empty_profile = root / "profiles" / "empty"
    profile.mkdir(parents=True)
    empty_profile.mkdir()
    (root / ".env").write_text("LOKI_CUSTOM_API_KEY=launch-only-fixture\n", encoding="utf-8")
    (profile / ".env").write_text("LOKI_CUSTOM_API_KEY=profile-only-fixture\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv(ENV_BOUND, "1")
    load_hermes_dotenv(load_external_secrets=False)
    env = served_profile_child_env(target_home=profile, inherit_credentials=True)
    assert env["LOKI_CUSTOM_API_KEY"] == env["HERMES_CUSTOM_API_KEY"] == "profile-only-fixture"
    assert env["HERMES_HOME"] == str(profile)
    empty = served_profile_child_env(target_home=empty_profile, inherit_credentials=True)
    assert "LOKI_CUSTOM_API_KEY" not in empty and "HERMES_CUSTOM_API_KEY" not in empty
