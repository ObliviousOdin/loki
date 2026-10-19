"""Auxiliary Nous warnings give Loki commands before log formatting reaches any surface."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent import auxiliary_client as auxiliary
from agent.redact import RedactingFormatter


def _assert_warning_command(caplog, command):
    warnings = [record for record in caplog.records
                if record.name == auxiliary.__name__ and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    warning = warnings[0]
    assert "Nous" in warning.getMessage()
    assert f"(run: {command})" in warning.getMessage()
    assert "hermes auth" not in warning.getMessage()
    formatted = RedactingFormatter("%(levelname)s %(name)s: %(message)s").format(warning)
    assert f"(run: {command})" in formatted


@pytest.mark.parametrize("stored_auth,command", [(None, "loki auth"), ({"fixture": True}, "loki auth add nous")])
def test_missing_nous_auth_warns_with_the_owned_command(monkeypatch, caplog, stored_auth, command):
    monkeypatch.setattr(auxiliary, "_read_nous_auth", lambda: stored_auth)
    monkeypatch.setattr(auxiliary, "_resolve_nous_runtime_api", lambda **kwargs: None)
    monkeypatch.setattr(auxiliary, "_nous_api_key", lambda auth: None)
    monkeypatch.setattr(auxiliary, "_mark_provider_unhealthy", Mock())
    client_factory = Mock(side_effect=AssertionError("No provider call is allowed"))
    monkeypatch.setattr(auxiliary, "_create_openai_client", client_factory)

    with caplog.at_level(logging.WARNING, logger=auxiliary.__name__):
        assert auxiliary._try_nous() == (None, None)

    _assert_warning_command(caplog, command)
    client_factory.assert_not_called()


def test_explicit_nous_route_warns_with_the_owned_command(monkeypatch, caplog):
    attempt = Mock(return_value=(None, None))
    monkeypatch.setattr(auxiliary, "_try_nous", attempt)
    request = SimpleNamespace(model=None, is_vision=False)

    with caplog.at_level(logging.WARNING, logger=auxiliary.__name__):
        assert auxiliary._resolve_nous_branch(request) == (None, None)

    attempt.assert_called_once_with(vision=False)
    _assert_warning_command(caplog, "loki auth")
