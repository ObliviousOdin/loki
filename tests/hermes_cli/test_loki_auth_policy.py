"""Fork-owned credentials and explicit app configuration, with no live service calls."""

from unittest.mock import Mock

import pytest

from hermes_cli.auth_constants import AuthError
from hermes_cli.loki_auth_policy import require_oauth_client_id


def test_oauth_requires_an_explicit_app_and_preserves_explicit_setup(monkeypatch):
    from hermes_cli import config

    monkeypatch.setattr(config, "load_config_readonly", dict)
    with pytest.raises(AuthError, match="no authorized OAuth application"):
        require_oauth_client_id("openai-codex")
    monkeypatch.setattr(config, "load_config_readonly", lambda: {
        "auth": {"oauth_clients": {"openai-codex": {"client_id": "operator-owned-app"}}}})
    assert require_oauth_client_id("openai-codex") == "operator-owned-app"
    assert require_oauth_client_id("openai-codex", "explicit-app") == "explicit-app"


def test_external_logins_are_opt_in_and_fail_closed(monkeypatch):
    from agent.credential_sources import adopt_external_logins_enabled
    from hermes_cli import config

    for cfg in ({}, {"auth": {}}, {"auth": {"adopt_external_logins": "true"}}):
        monkeypatch.setattr(config, "load_config_readonly", lambda cfg=cfg: cfg)
        assert adopt_external_logins_enabled() is False
    monkeypatch.setattr(config, "load_config_readonly", Mock(side_effect=OSError("unreadable")))
    assert adopt_external_logins_enabled() is False
    monkeypatch.setattr(config, "load_config_readonly", lambda: {"auth": {"adopt_external_logins": True}})
    assert adopt_external_logins_enabled() is True


def test_anonymous_account_creation_never_contacts_upstream_without_configuration(monkeypatch):
    from hermes_cli import config
    from hermes_cli.anon_auth import mint_guest

    monkeypatch.setattr(config, "load_config_readonly", dict)
    client = Mock()
    with pytest.raises(AuthError, match="hosted services are not configured"):
        mint_guest(client, "https://portal.nousresearch.com")
    client.post.assert_not_called()


def test_telemetry_has_no_upstream_fallback():
    from hermes_cli.observability.shared_metrics_send_config import resolve_send_config

    cfg = resolve_send_config({"telemetry": {"shared_metrics": {"enabled": True, "send": True}}})
    assert cfg.send is False
    assert cfg.endpoint == ""
    configured = resolve_send_config({"telemetry": {"shared_metrics": {
        "enabled": True, "send": True, "endpoint": "http://localhost:9911/metrics"}}})
    assert configured.send is True


def test_qwen_login_is_not_silently_read(monkeypatch):
    from hermes_cli import config
    from hermes_cli import auth_qwen

    monkeypatch.setattr(config, "load_config_readonly", dict)
    path_reader = Mock(side_effect=AssertionError("must not inspect external state"))
    monkeypatch.setattr(auth_qwen, "_qwen_cli_auth_path", path_reader)
    with pytest.raises(AuthError, match="External Qwen login adoption is disabled"):
        auth_qwen._read_qwen_cli_tokens()
    path_reader.assert_not_called()


def test_diagnostics_never_uses_an_inherited_hosted_destination(monkeypatch):
    from hermes_cli import diagnostics_upload

    monkeypatch.setattr(diagnostics_upload, "NAS_BASE", "")
    request = Mock(side_effect=AssertionError("must not contact an upstream endpoint"))
    monkeypatch.setattr(diagnostics_upload, "_urlopen_checked", request)
    with pytest.raises(RuntimeError, match="Loki diagnostics upload is not configured"):
        diagnostics_upload.request_upload_url()
    request.assert_not_called()


def test_welcome_trial_requires_an_explicit_hosted_service(monkeypatch):
    from hermes_cli import config, install_state, welcome_trial

    monkeypatch.setattr(config, "load_config_readonly", dict)
    probe = Mock(side_effect=AssertionError("disabled trials must not inspect machine history"))
    monkeypatch.setattr(install_state, "probe", probe)

    assert welcome_trial.claim_blocker() == "Loki hosted services are not configured"
    assert welcome_trial.claim_desktop_free_tier() is None
    probe.assert_not_called()
