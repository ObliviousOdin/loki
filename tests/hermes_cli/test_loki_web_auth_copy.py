"""Authored dashboard guidance names Loki; provider and user values remain verbatim."""
import asyncio
from types import SimpleNamespace


def test_login_pages_brand_loki_without_rewriting_provider_or_proxy_values(monkeypatch):
    from hermes_cli.dashboard_auth import login_page

    provider = SimpleNamespace(name="HermesCustom", display_name="Hermes <Account>", supports_password=False)
    monkeypatch.setattr(login_page, "list_session_providers", lambda: [provider])
    html = login_page.render_login_html(next_path="/Hermes-user-session", prefix="/Hermes-user-prefix")
    assert "<title>Sign in — Loki</title>" in html
    assert '<div class="brand">Loki</div>' in html
    assert "continue to the Loki dashboard" in html
    assert "Sign in with Hermes &lt;Account&gt;" in html
    assert "/Hermes-user-prefix/auth/login?provider=HermesCustom" in html
    assert "next=%2FHermes-user-session" in html

    monkeypatch.setattr(login_page, "list_session_providers", list)
    assert "<title>Sign-in unavailable — Loki</title>" in login_page.render_login_html()


def test_owned_oauth_commands_use_loki_while_external_commands_and_catalog_values_survive(monkeypatch):
    from hermes_cli import provider_catalog
    from hermes_cli.web_routers import oauth

    custom = SimpleNamespace(tab="accounts", slug="HermesCustom", label="Hermes Provider",
                             signup_url="https://example.test/Hermes")
    monkeypatch.setattr(provider_catalog, "provider_catalog", lambda: [custom])
    rows = {row["id"]: row for row in oauth._build_oauth_catalog()}
    for name in ("nous", "openai-codex", "qwen-oauth", "minimax-oauth", "xai-oauth", "anthropic"):
        assert rows[name]["cli_command"] == f"loki auth add {name}"
    assert rows["copilot-acp"]["cli_command"] == "copilot login"
    assert rows["claude-code"]["cli_command"] == "claude setup-token"
    assert rows[custom.slug]["cli_command"] == "loki auth add HermesCustom"
    assert (rows[custom.slug]["name"], rows[custom.slug]["docs_url"]) == (custom.label, custom.signup_url)


def test_chat_start_guidance_preserves_dynamic_error_detail():
    from hermes_cli.web_routers.chat_ws_errors import chat_start_failure_message

    detail = "Hermes-user-workspace could not be opened"
    message = chat_start_failure_message(RuntimeError(detail))
    assert detail in message
    assert "`loki dashboard`" in message
    assert "Loki needs Node.js" in chat_start_failure_message(FileNotFoundError(2, "missing", "node"))


def test_profile_and_plugin_commands_preserve_custom_names(monkeypatch):
    from hermes_cli import web_server_dashboard
    from hermes_cli.web_routers import profiles

    monkeypatch.setattr(profiles, "_resolve_profile_dir", lambda name: None)
    assert profiles._profile_setup_command("default") == "loki setup"
    assert profiles._profile_setup_command("HermesCustom") == "HermesCustom setup"
    assert web_server_dashboard._plugin_login_command("HermesCustom") == "loki auth HermesCustom"
    assert web_server_dashboard._plugin_login_command("spotify") == "loki spotify login"


def test_default_telegram_name_is_loki_and_explicit_user_name_is_preserved(monkeypatch):
    from hermes_cli.web_models import TelegramOnboardingStart
    from hermes_cli.web_routers import messaging

    names = []

    async def request(method, path, *, body):
        names.append(body["bot_name"])
        return {"pairing_id": f"synthetic-{len(names)}", "poll_token": "synthetic-only",
                "expires_at": "2099-01-01T00:00:00Z", "deep_link": "https://example.test/owned"}

    monkeypatch.setattr(messaging, "_telegram_onboarding_request", request)
    monkeypatch.setattr(messaging, "_telegram_onboarding_pairings", {})
    asyncio.run(messaging.start_telegram_onboarding(TelegramOnboardingStart()))
    asyncio.run(messaging.start_telegram_onboarding(TelegramOnboardingStart(bot_name="Hermes Custom")))
    assert names == ["Loki", "Hermes Custom"]


def test_headless_and_termux_guidance_never_directs_updates_to_a_foreign_package():
    from hermes_cli import web_server_dashboard
    from hermes_cli.web_routers.actions import _NON_APPLYABLE_MESSAGES

    assert "loki serve" in web_server_dashboard._HEADLESS_MSG
    assert "`loki dashboard`" in web_server_dashboard._HEADLESS_MSG
    message = _NON_APPLYABLE_MESSAGES["apt"]()
    assert "Loki" in message and "no configured Termux APT update channel" in message
    assert "pkg upgrade hermes-agent" not in message
