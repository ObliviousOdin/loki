"""No inherited Telegram hosting; explicit operator endpoints and names remain usable."""
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from hermes_cli import telegram_managed_bot as bot
from hermes_cli import web_server_messaging as web
from loki_identity import CLIENT_USER_AGENT


def test_missing_telegram_service_never_makes_network_requests(monkeypatch, capsys):
    monkeypatch.delenv(bot.TELEGRAM_ONBOARDING_URL_ENV, raising=False)
    post = Mock(side_effect=AssertionError("must not use inherited hosting"))
    get = Mock(side_effect=AssertionError("must not poll inherited hosting"))
    monkeypatch.setattr(bot.httpx, "post", post)
    monkeypatch.setattr(bot.httpx, "get", get)
    assert bot.create_pairing() is None
    assert bot.auto_setup_telegram_bot_result() is None
    assert "TELEGRAM_ONBOARDING_URL" in capsys.readouterr().out
    post.assert_not_called()
    get.assert_not_called()


@pytest.mark.parametrize("name", [None, "Hermes custom bot"])
def test_explicit_telegram_service_uses_loki_default_preserving_custom_names(monkeypatch, name):
    response = Mock(status_code=201)
    response.json.return_value = {"pairing_id": "synthetic", "poll_token": "synthetic-only",
                                  "suggested_username": "custom_bot", "deep_link": "https://example.test/bot"}
    post = Mock(return_value=response)
    monkeypatch.setattr(bot.httpx, "post", post)
    args = {} if name is None else {"bot_name": name}
    assert bot.create_pairing("https://operator.example.test/", **args) is not None
    post.assert_called_once_with("https://operator.example.test/v1/telegram/pairings",
                                 json={"bot_name": name or "Loki"}, timeout=10.0)


def test_web_telegram_service_refuses_before_opening_http_client(monkeypatch):
    import httpx

    monkeypatch.delenv(bot.TELEGRAM_ONBOARDING_URL_ENV, raising=False)
    client = Mock(side_effect=AssertionError("must not construct client without configured hosting"))
    monkeypatch.setattr(httpx, "Client", client)
    with pytest.raises(HTTPException) as error:
        web._telegram_onboarding_request_sync("POST", "/v1/telegram/pairings", body={"bot_name": "Loki"})
    assert error.value.status_code == 503
    assert "TELEGRAM_ONBOARDING_URL" in error.value.detail
    client.assert_not_called()


def test_web_telegram_service_uses_explicit_endpoint_and_owned_client_identity(monkeypatch):
    import httpx

    monkeypatch.setenv(bot.TELEGRAM_ONBOARDING_URL_ENV, "https://operator.example.test/")
    response = Mock()
    response.json.return_value = {"pairing_id": "synthetic"}
    client = Mock()
    client.request.return_value = response
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(httpx, "Client", Mock(return_value=context))
    assert web._telegram_onboarding_request_sync("POST", "/v1/telegram/pairings", body={"bot_name": "Hermes custom"}) == response.json.return_value
    assert client.request.call_args.args == ("POST", "https://operator.example.test/v1/telegram/pairings")
    assert client.request.call_args.kwargs["headers"]["User-Agent"] == CLIENT_USER_AGENT
    assert client.request.call_args.kwargs["json"] == {"bot_name": "Hermes custom"}
