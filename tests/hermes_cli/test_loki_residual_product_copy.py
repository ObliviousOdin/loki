"""Actual published metadata and authored fallback descriptions identify Loki."""

import pytest


def test_command_registry_fallback_descriptions_name_loki(monkeypatch):
    from hermes_cli import commands

    monkeypatch.setattr(commands, "t", lambda key: key)
    assert commands.resolve_command("update").describe() == "Update Loki to the latest version"
    assert commands.resolve_command("version").describe() == "Show Loki version"
    assert "Nous" in commands.resolve_command("subscription").describe()


def test_actual_openapi_document_names_loki():
    from hermes_cli.web_server import app

    assert app.openapi()["info"]["title"] == "Loki"


@pytest.mark.platforms("posix")
def test_missing_native_pty_dependency_names_public_repair_command(monkeypatch):
    from hermes_cli import pty_bridge

    monkeypatch.setattr(pty_bridge, "_PTY_AVAILABLE", False)
    with pytest.raises(pty_bridge.PtyUnavailableError, match="Run loki pm repair, then restart Loki"):
        pty_bridge.PtyBridge.spawn(["unused"])
