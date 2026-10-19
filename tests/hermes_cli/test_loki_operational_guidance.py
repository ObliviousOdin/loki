"""Public operational guidance brands authored templates and preserves user data."""

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("answer", [None, {"reloaded": True}, {"error": "Hermes user-supplied reason"}])
def test_plugin_reload_hints_use_owned_command_without_rewriting_plugin_or_error(answer):
    from hermes_cli.plugins_activation import gateway_reload_hint
    text = gateway_reload_hint(answer, "Hermes user's plugin")
    assert "loki gateway restart" in text
    if answer and answer.get("reloaded"):
        assert "Hermes user's plugin" in text
    if answer and answer.get("error"):
        assert answer["error"] in text


@pytest.mark.parametrize("factory,command", [
    ("_missing_profile_error", "loki profile create"),
    ("_unknown_profile_error", "loki profile list"),
    ("_profile_exists_error", "loki profile use"),
])
def test_profile_remedies_preserve_a_name_containing_hermes(factory, command):
    from hermes_cli import profiles
    text = str(getattr(profiles, factory)("Hermes user's profile"))
    assert command in text and "Hermes user's profile" in text


def test_service_failure_guidance_names_loki_and_keeps_exception_details():
    import subprocess
    from hermes_cli.gateway_command_errors import explain_service_failure, SystemctlUnavailableError
    lines = explain_service_failure(subprocess.CalledProcessError(1, ["custom", "Hermes user command"]))
    assert "loki gateway status --deep" in "\n".join(lines)
    assert "Hermes user command" in lines[-1]
    assert "Loki" in "\n".join(explain_service_failure(SystemctlUnavailableError()))


def test_slack_default_copy_preserves_protocol_and_explicit_user_branding():
    from hermes_cli.slack_cli import _build_full_manifest
    manifest = _build_full_manifest("Loki", "", messaging_experience="assistant")
    assert manifest["display_information"]["description"] == "Your Loki agent on Slack"
    assert manifest["features"]["assistant_view"]["assistant_description"] == "Chat with Loki in threads and DMs."
    assert any(row["command"] == "/hermes" for row in manifest["features"]["slash_commands"])
    custom = _build_full_manifest("Hermes user name", "Hermes-3 / my provider")
    assert custom["display_information"]["name"] == "Hermes user name"
    assert custom["display_information"]["description"] == "Hermes-3 / my provider"


def test_console_title_is_loki_and_user_command_text_is_preserved():
    from hermes_cli.console_engine import HermesConsoleEngine
    console = HermesConsoleEngine()
    assert console.help_text().startswith("Loki Console\n")
    result = console.execute("HermesUserCommand")
    assert result.status == "error" and "HermesUserCommand" in result.output


def test_webhook_empty_command_prints_owned_usage(capsys):
    from hermes_cli.webhook import webhook_command
    webhook_command(SimpleNamespace(webhook_action=None))
    assert "Usage: loki webhook" in capsys.readouterr().out


def test_skills_empty_command_prints_owned_usage(capsys):
    from hermes_cli.skills_hub import skills_command
    assert skills_command(SimpleNamespace(skills_action=None)) is None
    assert "Usage: loki skills" in capsys.readouterr().out


def test_snapshot_recovery_hint_uses_loki():
    from hermes_cli.backup import _snapshot_recovery_hint
    assert "start `loki`" in _snapshot_recovery_hint()


def test_dashboard_oauth_choice_requires_project_authority_and_owned_state(monkeypatch, capsys):
    from hermes_cli import main_dashboard
    monkeypatch.setattr("hermes_cli.web_server.should_require_dashboard_auth", lambda _host: True)
    monkeypatch.setattr("hermes_cli.dashboard_auth.list_providers", list)
    monkeypatch.setattr(main_dashboard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(main_dashboard.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")
    with pytest.raises(SystemExit) as exited:
        main_dashboard._maybe_setup_dashboard_auth_interactively(SimpleNamespace(host="0.0.0.0"))
    assert exited.value.code == 0
    output = capsys.readouterr().out
    assert "loki dashboard register" in output
    assert "authorized for this Loki project" in output
    assert "Upstream hosted OAuth clients are not included" in output
    assert "this Loki profile's .env" in output
    assert "~/.hermes" not in output
