"""Common auxiliary failures retain provider details and point to Loki recovery commands."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent import auxiliary_client as auxiliary
from agent import credential_pool
from agent.auxiliary_unavailable import AuxiliaryClientUnavailable
from agent.redact import RedactingFormatter


def _rendered_warning(caplog, logger_name):
    warnings = [record for record in caplog.records
                if record.name == logger_name and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    text = RedactingFormatter("%(message)s").format(warnings[0])
    assert "hermes model" not in text
    assert "hermes auth" not in text
    return text


def test_malformed_endpoint_names_the_owned_recovery_commands():
    with pytest.raises(RuntimeError) as error:
        auxiliary._validate_base_url("https://fixture.invalid:bad-port/v1")
    message = str(error.value)
    assert "fixture.invalid:bad-port" in message
    assert "`loki setup` or `loki model`" in message


def test_stale_endpoint_warning_names_the_owning_profile(monkeypatch, caplog):
    monkeypatch.setattr(auxiliary, "_stale_base_url_warned", False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://fixture.invalid/v1")
    with caplog.at_level(logging.WARNING, logger=auxiliary.__name__):
        auxiliary._warn_stale_openai_base_url("anthropic")
    message = _rendered_warning(caplog, auxiliary.__name__)
    assert "model.provider is 'anthropic'" in message
    assert "Run: loki model" in message
    assert "your Loki profile's .env" in message


def test_unavailable_configured_provider_keeps_the_no_discovery_boundary(caplog):
    with caplog.at_level(logging.WARNING, logger=auxiliary.__name__):
        assert auxiliary._discovery_chain_allowed("anthropic", "compression") is False
    message = _rendered_warning(caplog, auxiliary.__name__)
    assert "main provider anthropic is unavailable" in message
    assert "refusing to guess" in message
    assert "(`loki model`)" in message


@pytest.mark.parametrize("provider", ["openai-codex", "xai-oauth"])
def test_missing_optional_oauth_route_logs_an_owned_command(monkeypatch, caplog, provider):
    builder_name, resolver_name, label = {
        "openai-codex": ("_build_codex_client", "_resolve_openai_codex_branch", "Codex OAuth"),
        "xai-oauth": ("_build_xai_oauth_aux_client", "_resolve_xai_oauth_branch", "xAI OAuth"),
    }[provider]
    builder = Mock(return_value=(None, None))
    monkeypatch.setattr(auxiliary, builder_name, builder)
    request = SimpleNamespace(model="Hermes-3", raw_codex=False, provider=provider)
    with caplog.at_level(logging.WARNING, logger=auxiliary.__name__):
        assert getattr(auxiliary, resolver_name)(request) == (None, None)
    builder.assert_called_once_with("Hermes-3")
    message = _rendered_warning(caplog, auxiliary.__name__)
    assert provider in message and label in message
    assert "run: loki model" in message


def test_no_auxiliary_client_names_the_owned_setup_command(monkeypatch):
    monkeypatch.setattr(auxiliary, "_get_cached_client", Mock(return_value=(None, None)))
    with pytest.raises(AuxiliaryClientUnavailable) as error:
        auxiliary._resolve_call_client(
            "compression", provider="custom", model="Hermes-3", base_url="https://fixture.invalid/v1",
            api_key=None, resolved_provider="custom", resolved_model="Hermes-3",
            resolved_base_url="https://fixture.invalid/v1", resolved_api_key=None,
            resolved_api_mode=None, main_runtime=None, async_mode=False,
        )
    assert "task=compression provider=custom. Run: loki setup" in str(error.value)


def test_env_ingestion_warning_keeps_the_spending_warning_and_owned_opt_out(monkeypatch, caplog):
    monkeypatch.setattr(credential_pool, "_ENV_INGESTION_WARNED", set())
    with caplog.at_level(logging.WARNING, logger=credential_pool.__name__):
        credential_pool._warn_env_ingestion_once("openrouter", "OPENROUTER_API_KEY")
        credential_pool._warn_env_ingestion_once("openrouter", "OPENROUTER_API_KEY")
    message = _rendered_warning(caplog, credential_pool.__name__)
    assert "OPENROUTER_API_KEY" in message
    assert "enables OpenRouter spend" in message
    assert "loki auth remove openrouter <n>" in message
