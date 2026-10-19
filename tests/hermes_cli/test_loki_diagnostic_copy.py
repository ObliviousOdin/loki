"""Product remedies are authored before user values and interoperability data are inserted."""

from pathlib import Path

import pytest


@pytest.mark.parametrize("fallback", ["defaults", "last-known-good", "last-known-good-backup"])
def test_config_remedy_preserves_literal_user_path(fallback):
    from hermes_cli.config_read_errors import format_config_parse_failure

    path = Path("/tmp/Hermes Agent/HERMES_HOME/Hermes-4.0/config.yaml")
    message = format_config_parse_failure(path, ValueError("invalid yaml"), fallback=fallback)
    assert str(path) in message
    assert "Loki is running" in message
    assert "`loki config edit`" in message
    assert "`loki config check`" in message


def test_entitlement_remedy_preserves_capability_and_external_billing_url():
    from hermes_cli.nous_account import format_nous_portal_entitlement_message

    message = format_nous_portal_entitlement_message(None, capability="Hermes Agent connector")
    assert message.startswith("Loki could not verify")
    assert "Hermes Agent connector" in message
    assert "`loki model`" in message
    assert "https://portal.nousresearch.com/billing" in message


def test_invalid_oauth_client_names_owned_configuration_and_preserves_retry():
    from hermes_cli.auth_error_copy import device_flow_error

    message = str(device_flow_error("invalid_client", "bad", retry_command="Hermes user retry"))
    assert "Check Loki's authorized client settings" in message
    assert "`Hermes user retry`" in message


def test_hosted_status_copy_does_not_promise_automatic_free_grants():
    from hermes_cli.anon_auth import FREE_TIER_NOT_SIGNED_IN

    assert "depend on your provider configuration" in FREE_TIER_NOT_SIGNED_IN
    assert "`loki auth`" in FREE_TIER_NOT_SIGNED_IN
    assert "always on" not in FREE_TIER_NOT_SIGNED_IN


def test_upstream_error_protocol_still_classifies_hermes_server_response():
    from hermes_cli.anon_auth import welcome_route_refusal

    assert welcome_route_refusal(400, "serves anonymous hermes agent accounts only") == "named_on_welcome_host"


def test_model_warning_retains_actual_upstream_model_name():
    from hermes_cli.model_switch import _check_hermes_model_warning

    message = _check_hermes_model_warning("NousResearch/Hermes-3-Llama-3.1-70B")
    assert "Nous Research Hermes 3 & 4" in message
    assert "for use with Loki" in message


def test_section_refusal_keeps_dynamic_keys_and_values(monkeypatch, capsys):
    from hermes_cli.config_section_guard import _guard_section_overwrite

    with pytest.raises(SystemExit) as exit_info:
        _guard_section_overwrite("Hermes_user", "Hermes Agent model", {"Hermes_user": {"key": "value"}}, False)
    assert exit_info.value.code == 1
    message = capsys.readouterr().err
    assert "loki config set Hermes_user.<sub-key>" in message
    assert "'Hermes Agent model'" in message


def test_memory_provider_remedy_preserves_user_provider_name(monkeypatch):
    from hermes_cli import doctor_state, memory_provider_migration
    from plugins import memory

    calls = []
    monkeypatch.setattr(memory, "load_memory_provider", lambda _name: None)
    monkeypatch.setattr(memory, "find_provider_dir", lambda _name: None)
    monkeypatch.setattr(memory_provider_migration, "catalog_install_hint", lambda *_a, **_k: None)
    monkeypatch.setattr(doctor_state, "check_warn", lambda *args: calls.append(args))
    doctor_state._memory_provider_generic("Hermes_user_provider")
    assert calls == [("Hermes_user_provider plugin not found", "run: loki memory setup")]


def test_restart_description_preserves_a_hermes_named_profile():
    from hermes_cli.update_inventory import describe_restart_mechanism

    assert describe_restart_mechanism("manual", "hermes-profile") == "loki -p hermes-profile gateway restart"
    assert describe_restart_mechanism("manual", "default") == "loki gateway restart"


@pytest.mark.parametrize("where", ["receipt", "unproven-receipt", "file"])
def test_manual_restart_remedy_preserves_dynamic_owner_fields(monkeypatch, capsys, where):
    import json
    from hermes_cli import process_identity, update_serve_obligations
    from hermes_constants import get_hermes_home

    row = {"kind": "Hermes user backend", "profile": "Hermes user profile", "pid": 4242,
           "create_time": 1000.0, "detail": {"create_time": 1000.0}}
    pending = [row]
    if where == "unproven-receipt":
        row["detail"] = {}
    elif where == "file":
        directory = get_hermes_home() / "serve_restart_pending"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "fixture.json").write_text(json.dumps(row), encoding="utf-8")
        monkeypatch.setattr(process_identity, "_pid_alive_matches", lambda *_: True)
        pending = []
    update_serve_obligations.warn_pending_manual_serves(pending_manual=pending)
    message = capsys.readouterr().out
    assert "Hermes user backend" in message and "Hermes user profile" in message
    assert "`loki serve` / `loki dashboard`" in message
    assert "`hermes serve`" not in message and "`hermes dashboard`" not in message
