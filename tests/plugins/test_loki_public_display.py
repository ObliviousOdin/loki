"""Public plugin defaults use Loki without rewriting explicit names or wire identifiers."""
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from loki_identity import CLIENT_USER_AGENT


@pytest.mark.parametrize("guest_name,expected", [(None, "Loki"), ("Hermes Agent custom", "Hermes Agent custom")])
@pytest.mark.parametrize("node", [None, "Hermes-node"])
def test_meet_join_preserves_custom_guest_and_node(monkeypatch, guest_name, expected, node):
    from plugins.google_meet import tools

    calls = []

    def start(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "meeting_id": "Hermes-session"}

    monkeypatch.setattr(tools, "check_meet_requirements", lambda: True)
    monkeypatch.setattr(tools.pm, "start", start)
    monkeypatch.setattr(tools, "resolve_node", lambda name: (SimpleNamespace(start_bot=start), name))
    args = {"url": "https://meet.google.com/abc-defg-hij", "node": node}
    if guest_name is not None:
        args["guest_name"] = guest_name
    result = json.loads(tools.handle_meet_join(args))
    assert result["success"] is True
    assert result["meeting_id"] == "Hermes-session"
    assert calls == [{"url": args["url"], "guest_name": expected, "duration": None,
                      "headed": False, "mode": "transcribe"}]
    if node:
        assert result["node"] == node


def test_meet_parser_default_and_explicit_guest():
    from plugins.google_meet.cli import register_cli

    parser = argparse.ArgumentParser(prog="loki meet")
    register_cli(parser)
    url = "https://meet.google.com/abc-defg-hij"
    assert parser.parse_args(["join", url]).guest_name == "Loki"
    assert parser.parse_args(["join", url, "--guest-name", "Hermes custom"]).guest_name == "Hermes custom"


@pytest.mark.parametrize("organization,expected", [(None, "Loki"), ("Hermes Research custom", "Hermes Research custom")])
def test_a2a_card_preserves_custom_names_and_protocol(monkeypatch, organization, expected):
    from plugins.platforms.a2a.protocol import build_agent_card, skills_from_toolsets

    monkeypatch.delenv("A2A_PROVIDER_ORG", raising=False)
    if organization is not None:
        monkeypatch.setenv("A2A_PROVIDER_ORG", organization)
    skills = skills_from_toolsets({"Hermes-tools": ["hermes_tool"]})
    card = build_agent_card(name="Hermes-3 custom", url="https://example.invalid/a2a",
                            description="Hermes user-authored description", skills=skills,
                            auth_required=True, tenant="Hermes-tenant")
    assert card["provider"]["organization"] == expected
    assert card["name"] == "Hermes-3 custom"
    assert card["description"] == "Hermes user-authored description"
    assert card["skills"] == [{"id": "toolset.Hermes-tools", "name": "Hermes-tools",
                               "description": "Loki 'Hermes-tools' capabilities",
                               "tags": ["Hermes-tools", "hermes_tool"]}]
    assert card["supportedInterfaces"] == [{"url": "https://example.invalid/a2a",
                                            "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                                            "tenant": "Hermes-tenant"}]
    assert card["security"] == [{"bearer": []}]


def test_missing_xai_credentials_give_owned_command_without_network(monkeypatch):
    from plugins.web.xai import provider

    monkeypatch.setattr(provider, "resolve_xai_http_credentials", dict)
    result = provider.XAIWebSearchProvider().search("Hermes-3 model")
    assert result["success"] is False
    assert "`loki auth`" in result["error"]
    assert "XAI_API_KEY" in result["error"]


def test_qq_user_agent_preserves_vendor_and_runtime_components():
    import platform
    import sys
    from plugins.platforms.qqbot.constants import QQBOT_VERSION
    from plugins.platforms.qqbot.utils import get_api_headers

    headers = get_api_headers()
    assert headers == {"Content-Type": "application/json", "Accept": "application/json",
                       "User-Agent": f"QQBotAdapter/{QQBOT_VERSION} (Python/{sys.version_info.major}."
                       f"{sys.version_info.minor}.{sys.version_info.micro}; {platform.system().lower()}; {CLIENT_USER_AGENT})"}


def test_dashboard_missing_client_remedy_preserves_invalid_client_value(monkeypatch):
    from plugins.dashboard_auth import nous
    from unittest.mock import MagicMock

    monkeypatch.setenv("HERMES_DASHBOARD_OAUTH_CLIENT_ID", "Hermes-explicit-invalid")
    monkeypatch.setattr(nous, "_load_config_oauth_section", dict)
    ctx = MagicMock()
    nous.register(ctx)
    ctx.register_dashboard_auth_provider.assert_not_called()
    assert "LOKI_DASHBOARD_OAUTH_CLIENT_ID='Hermes-explicit-invalid'" in nous.LAST_SKIP_REASON
    assert "agent:{instance_id}" in nous.LAST_SKIP_REASON
    assert "explicitly authorized client" in nous.LAST_SKIP_REASON
    assert "not included with Loki" in nous.LAST_SKIP_REASON
    assert "Fly" not in nous.LAST_SKIP_REASON


@pytest.mark.parametrize("prefix,expected", [(None, "loki_meet"), ("Hermes-custom", "Hermes-custom")])
def test_meet_audio_owns_defaults_and_unloads_only_its_modules(monkeypatch, prefix, expected):
    from plugins.google_meet import audio_bridge

    calls = []
    foreign = {7: "hermes_meet_sink", 8: "hermes_meet_src"}
    modules = dict(foreign)

    def pactl(*args, check):
        calls.append((args, check))
        if args[0] == "load-module":
            module_id = 41 + len(calls)
            modules[module_id] = args[2]
            return SimpleNamespace(stdout=f"{module_id}\n")
        assert args[0] == "unload-module"
        del modules[int(args[1])]
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(audio_bridge, "_pactl", pactl)
    bridge = audio_bridge.AudioBridge(**({"name_prefix": prefix} if prefix is not None else {}))
    info = bridge._setup_linux()
    assert calls[0] == (("load-module", "module-null-sink", f"sink_name={expected}_sink",
                         "sink_properties=device.description=LokiMeetSink"), True)
    assert f"master={expected}_sink.monitor" in calls[1][0]
    assert info["device_name"] == f"{expected}_src"
    assert info["write_target"] == f"{expected}_sink"
    assert info["module_ids"] == [42, 43]
    bridge.teardown()
    assert calls[2:] == [(("unload-module", "43"), False), (("unload-module", "42"), False)]
    assert modules == foreign
    bridge.teardown()
    assert len(calls) == 4


@pytest.mark.parametrize("target,expected", [(None, "loki_meet_sink"), ("Hermes-custom_sink", "Hermes-custom_sink")])
def test_meet_pcm_target_preserves_custom_and_owns_fallback(monkeypatch, tmp_path, target, expected):
    from plugins.google_meet import meet_bot
    from unittest.mock import Mock

    commands = []

    def popen(command, **kwargs):
        commands.append(command)
        raise FileNotFoundError("unit fixture: no external audio process")

    monkeypatch.setattr(meet_bot.subprocess, "Popen", popen)
    state = SimpleNamespace(set=Mock())
    runtime = {}
    meet_bot._start_pcm_pump(runtime, {"platform": "linux", "write_target": target},
                             tmp_path / "speaker.pcm", state, {"stop": False})
    assert commands == [["paplay", "--raw", "--rate=24000", "--format=s16le", "--channels=1",
                         f"--device={expected}", "-"]]
    assert runtime == {}
    state.set.assert_called_once_with(error="paplay not found — install pulseaudio-utils for realtime on Linux")
