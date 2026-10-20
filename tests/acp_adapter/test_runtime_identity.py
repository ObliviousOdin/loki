"""Runtime identity contracts for ACP's human and machine surfaces."""

from types import SimpleNamespace
from typing import cast

import pytest

from acp_adapter import entry
from acp_adapter.server import HermesACPAgent
from acp_adapter.session import SessionState


def test_version_flag_displays_derived_version(monkeypatch, capsys):
    monkeypatch.setattr(
        "hermes_cli.version_info.get_version_info",
        lambda: SimpleNamespace(base_version="1.2.3", derived_version="1.2.3+4.gabcdef0"),
    )

    entry.main(["--version"])

    assert capsys.readouterr().out == "1.2.3+4.gabcdef0\n"


def test_version_slash_command_displays_derived_version(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.version_info.get_version_info",
        lambda: SimpleNamespace(base_version="1.2.3", derived_version="1.2.3+4.gabcdef0"),
    )

    agent = object.__new__(HermesACPAgent)
    state = cast(SessionState, SimpleNamespace(cwd="."))
    assert agent._handle_slash_command("/version", state) == "Loki v1.2.3+4.gabcdef0"


@pytest.mark.asyncio
async def test_initialize_advertises_base_version(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.version_info.get_version_info",
        lambda: SimpleNamespace(base_version="1.2.3", derived_version="1.2.3+4.gabcdef0"),
    )

    response = await object.__new__(HermesACPAgent).initialize()

    assert response.agent_info is not None
    assert response.agent_info.name == "loki"
    assert response.agent_info.version == "1.2.3"


@pytest.mark.asyncio
async def test_gateway_initialize_advertises_loki_without_changing_capabilities():
    from acp_adapter.gateway_server import GatewayACPAgent
    from hermes_cli import __version__

    response = await GatewayACPAgent().initialize()

    assert response.agent_info.name == "loki"
    assert response.agent_info.version == __version__
    assert response.agent_capabilities.load_session is True
    assert response.agent_capabilities.prompt_capabilities.image is True


def test_entry_help_and_dependency_check_name_the_public_product(capsys):
    with pytest.raises(SystemExit) as exit_info:
        entry.main(["--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "loki-acp" in help_text and "Loki" in help_text
    assert "Hermes" not in help_text and "hermes-acp" not in help_text

    entry.main(["--check"])
    assert capsys.readouterr().out == "Loki ACP check OK\n"


def test_advertised_version_command_names_loki():
    commands = {command.name: command.description for command in HermesACPAgent._available_commands()}
    assert commands["version"] == "Show Loki version"


def test_terminal_setup_uses_public_command_when_argv_is_empty(monkeypatch):
    invoked = []
    monkeypatch.setattr(entry.sys, "argv", [])
    monkeypatch.setattr(entry.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("hermes_cli.main.main", lambda: invoked.append(entry.sys.argv[:]))

    entry._run_setup()

    assert invoked == [["loki", "model"]]
    assert entry.sys.argv == []
