"""Loki's Codex callback coexists with foreign Hermes configuration."""
import sys
import tomllib
from types import SimpleNamespace

import pytest

from hermes_cli import codex_runtime_plugin_migration as migration


@pytest.mark.parametrize("terminated", [True, False])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_foreign_managed_section_is_preserved_across_real_migrations(tmp_path, monkeypatch, terminated, newline):
    foreign = ('# managed by hermes-agent — `hermes codex-runtime migrate` regenerates this section\n'
               'default_permissions = ":read-only"\n\n'
               '[mcp_servers.hermes-tools]\ncommand = "foreign-hermes"\n'
               'args = ["Hermes user argument"]\n\n'
               '[plugins."foreign@openai-curated"]\nenabled = false\n')
    if terminated:
        foreign += '# end hermes-agent managed section\n'
    foreign = foreign.replace("\n", newline)
    target = tmp_path / "config.toml"
    target.write_bytes(foreign.encode("utf-8"))
    auth = tmp_path / "auth.json"
    auth.write_bytes(b'foreign credential canary: never read or change\n')
    monkeypatch.setattr(migration, "_query_codex_plugins", lambda **_: ([
        {"name": "foreign", "marketplace": "openai-curated", "enabled": True},
        {"name": "new", "marketplace": "openai-curated", "enabled": True}], None))

    for _ in range(2):
        report = migration.migrate({}, codex_home=tmp_path)
        assert report.errors == [] and report.written
        text = target.read_bytes().decode("utf-8")
        assert foreign in text
        parsed = tomllib.loads(text)
        assert parsed["default_permissions"] == ":read-only"
        assert parsed["mcp_servers"]["hermes-tools"] == {
            "command": "foreign-hermes", "args": ["Hermes user argument"]}
        assert parsed["mcp_servers"]["loki-tools"]["args"] == [
            "-m", "agent.transports.hermes_tools_mcp_server"]
        assert parsed["plugins"]["foreign@openai-curated"]["enabled"] is False
        assert parsed["plugins"]["new@openai-curated"]["enabled"] is True
        assert report.migrated_plugins == ["new@openai-curated"]
        assert report.wrote_permissions_default is None
        assert text.count(migration.MIGRATION_MARKER) == 1
        assert auth.read_bytes() == b'foreign credential canary: never read or change\n'


def test_user_hermes_server_is_not_claimed_by_loki(tmp_path):
    foreign = '[mcp_servers.hermes-tools]\ncommand = "user-hermes"\n'
    target = tmp_path / "config.toml"
    target.write_text(foreign)
    report = migration.migrate({}, codex_home=tmp_path, discover_plugins=False,
                               default_permission_profile=None)
    assert report.errors == [] and report.written
    assert foreign in target.read_text()
    assert report.migrated == ["loki-tools"]


def test_closed_foreign_block_keeps_nested_loki_marker_comments(tmp_path):
    foreign = ('# managed by hermes-agent — `hermes codex-runtime migrate` regenerates this section\n'
               '[mcp_servers.hermes-tools]\ncommand = "foreign-hermes"\n'
               + migration.MIGRATION_MARKER + '\n'
               '[mcp_servers.foreign-extra]\ncommand = "Hermes user command"\n'
               + migration.MIGRATION_END_MARKER + '\n# end hermes-agent managed section\n')
    target = tmp_path / "config.toml"
    target.write_bytes(foreign.encode())
    report = migration.migrate({}, codex_home=tmp_path, discover_plugins=False)
    assert report.errors == [] and report.written
    text = target.read_bytes().decode()
    assert foreign in text
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["foreign-extra"]["command"] == "Hermes user command"
    assert "loki-tools" in parsed["mcp_servers"]


@pytest.mark.parametrize("name,action", [("loki-tools", "accept"), ("hermes-tools", "decline"), ("user-tools", "decline")])
def test_only_owned_callback_gets_automatic_elicitation(name, action):
    from agent.transports.codex_app_server_session import CodexAppServerSession
    assert object.__new__(CodexAppServerSession)._respond_elicitation({"serverName": name})["action"] == action


def test_only_owned_callback_loses_its_display_namespace():
    from agent.codex_runtime import _codex_item_to_tool_name
    assert _codex_item_to_tool_name({"type": "mcpToolCall", "server": "loki-tools", "tool": "web_search"}) == "web_search"
    assert _codex_item_to_tool_name({"type": "mcpToolCall", "server": "hermes-tools", "tool": "web_search"}) == "mcp.hermes-tools.web_search"


@pytest.mark.parametrize("bound", [True, False])
def test_callback_entry_uses_public_selector_without_adopting_ambient_hermes(monkeypatch, bound):
    from loki_identity import bind_loki_environment
    own = "/Users/loki-fixture/.loki/profiles/Hermes user profile"
    monkeypatch.setenv("HERMES_HOME", own if bound else "/Users/loki-fixture/.hermes")
    monkeypatch.setenv("LOKI_HOME", own)
    monkeypatch.setenv("__LOKI_ENV_BOUND", "1" if bound else "")
    env = migration._build_hermes_tools_mcp_entry()["env"]
    child = {"HOME": "/Users/loki-fixture", "HERMES_HOME": "/Users/loki-fixture/.hermes", **env}
    bind_loki_environment(child)
    assert env["LOKI_HOME"] == own and child["HERMES_HOME"] == own
    assert child["HERMES_QUIET"] == "1" and child["HERMES_REDACT_SECRETS"] == "true"
    monkeypatch.delenv("LOKI_HOME")
    monkeypatch.delenv("__LOKI_ENV_BOUND")
    assert "LOKI_HOME" not in migration._build_hermes_tools_mcp_entry()["env"]


def test_actual_server_registration_keeps_tool_identity_and_custom_description(monkeypatch):
    from agent.transports import hermes_tools_mcp_server as module
    class Server:
        def __init__(self, name, **kwargs):
            self.name, self.instructions, self.tools = name, kwargs["instructions"], []
        def add_tool(self, handler, **kwargs):
            self.tools.append((handler, kwargs))
    monkeypatch.setitem(sys.modules, "mcp.server", SimpleNamespace(MCPServer=Server))
    monkeypatch.setattr("model_tools.get_tool_definitions", lambda **_: [{"type": "function", "function": {
        "name": "web_search", "description": "Hermes user description", "parameters": {"type": "object"}}}])
    server = module._build_server()
    assert server.name == "loki-tools" and "Loki" in server.instructions and "Hermes Agent" not in server.instructions
    assert server.tools[0][1] == {"name": "web_search", "description": "Hermes user description"}
