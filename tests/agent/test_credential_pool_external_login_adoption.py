"""Explicit external-login adoption remains compatible with the OAuth pool path."""

import json
import time

from tests.loki_auth_fixture import configure_auth


def test_load_pool_oauth_path_still_autodiscovers(tmp_path, monkeypatch):
    """OAuth path: ANTHROPIC_TOKEN set, autodiscovery still fires.

    Regression guard: the API-key gate must not affect users who chose the
    OAuth path at `hermes setup`.  When ANTHROPIC_TOKEN is set (and
    ANTHROPIC_API_KEY is empty), autodiscovered Claude Code creds should
    still be seeded into the pool as before.
    """
    configure_auth(monkeypatch, clients=("anthropic",), adopt_external_logins=True)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_TOKEN", "sk-ant-oat01-explicit-oauth-token")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    home = tmp_path / "hermes"
    home.mkdir()
    (home / "auth.json").write_text(json.dumps({"version": 1, "providers": {}}), encoding="utf-8")
    monkeypatch.setattr("hermes_cli.auth.is_provider_explicitly_configured", lambda pid: True)

    monkeypatch.setattr(
        "agent.anthropic_credentials.read_hermes_oauth_credentials",
        lambda: None,
    )
    monkeypatch.setattr(
        "agent.anthropic_credentials.read_claude_code_credentials",
        lambda: {
            "accessToken": "sk-ant-oat01-autodiscovered-cc",
            "refreshToken": "cc-refresh",
            "expiresAt": int(time.time() * 1000) + 3_600_000,
        },
    )

    from agent.credential_pool import load_pool

    pool = load_pool("anthropic")
    sources = {entry.source for entry in pool.entries()}

    # Both env OAuth token and autodiscovered Claude Code creds should be there.
    assert "env:ANTHROPIC_TOKEN" in sources
    assert "claude_code" in sources

