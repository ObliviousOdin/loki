"""Quick setup saves optional settings without claiming a failed provider is ready."""

from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("provider_ready", [False, True])
def test_quick_setup_reports_provider_readiness_and_preserves_settings(
    tmp_path, monkeypatch, capsys, provider_ready
):
    from hermes_cli import model_setup_flows, setup, setup_quick
    from hermes_cli.auth import AuthError

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    setup.save_config({"terminal": {"backend": "local"}, "agent": {"max_turns": 40}})

    def run_provider(config, **kwargs):
        if not provider_ready:
            raise AuthError("Provider setup failed.", code="oauth_client_not_configured")
        saved = setup.load_config()
        saved["model"] = {"provider": "nous", "default": "fixture-model"}
        setup.save_config(saved)

    def configure_terminal(config):
        config["terminal"]["cwd"] = str(tmp_path / "workspace")

    def configure_gateway(config):
        config.setdefault("gateway", {})["multiplex_profiles"] = False

    summary = Mock()
    monkeypatch.setattr(model_setup_flows, "_model_flow_nous", run_provider)
    monkeypatch.setattr(setup_quick, "_print_macos_fda_tip", Mock())
    monkeypatch.setattr(setup, "setup_terminal_backend", configure_terminal)
    monkeypatch.setattr(setup, "setup_gateway", configure_gateway)
    monkeypatch.setattr(setup, "prompt_choice", lambda *args, **kwargs: 0)
    monkeypatch.setattr(setup, "_print_setup_summary", summary)

    config = setup.load_config()
    setup_quick._run_first_time_quick_setup(config, tmp_path, False)

    saved = setup.load_config()
    assert saved["terminal"]["cwd"] == str(tmp_path / "workspace")
    assert saved["gateway"]["multiplex_profiles"] is False
    assert saved["agent"]["max_turns"] == 150
    output = capsys.readouterr().out
    if provider_ready:
        assert saved["model"]["provider"] == "nous"
        assert saved["model"]["default"] == "fixture-model"
        assert "You're ready to go" in output
        summary.assert_called_once_with(config, tmp_path)
    else:
        assert "Settings saved" in output
        assert "Loki cannot chat yet" in output
        assert "loki model" in output
        assert "You're ready to go" not in output
        summary.assert_not_called()


def test_portal_setup_explains_account_requirements_and_public_start_command(monkeypatch, capsys):
    from hermes_cli import setup, setup_quick

    monkeypatch.setattr(setup_quick, "_run_nous_flow", lambda *args, **kwargs: True)
    monkeypatch.setattr(setup_quick, "_reload_config_into", Mock())
    monkeypatch.setattr(setup, "_record_setup_completed", Mock())

    setup_quick._run_portal_one_shot({})

    output = capsys.readouterr().out
    assert "your own Nous Portal account" in output
    assert "client authorized for Loki" in output
    assert "depend on your account" in output
    assert "300+" not in output
    assert "Run `loki` to start chatting" in output
