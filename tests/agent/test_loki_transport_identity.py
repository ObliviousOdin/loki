"""Owned client presentation must not adopt another distribution or rewrite custom copy."""
import inspect
from importlib.metadata import PackageNotFoundError

import pytest


def test_copilot_client_announces_loki_and_its_own_version():
    from agent.copilot_acp_client import _INITIALIZE_PARAMS
    from loki_identity import VERSION

    assert _INITIALIZE_PARAMS["clientInfo"] == {"name": "loki-agent", "title": "Loki", "version": VERSION}
    assert _INITIALIZE_PARAMS["protocolVersion"] == 1


def test_codex_client_defaults_announce_loki():
    from agent.transports.codex_app_server import CodexAppServerClient

    parameters = inspect.signature(CodexAppServerClient.initialize).parameters
    assert parameters["client_name"].default == "loki"
    assert parameters["client_title"].default == "Loki"


@pytest.mark.parametrize("installed", [True, False])
def test_codex_client_version_reads_only_own_distribution(monkeypatch, installed):
    import importlib.metadata
    from agent.transports.codex_app_server_session import _get_hermes_version
    from loki_identity import DISTRIBUTION, VERSION

    read = []

    def version(distribution):
        read.append(distribution)
        if not installed:
            raise PackageNotFoundError(distribution)
        return "9.1.2-loki"

    monkeypatch.setattr(importlib.metadata, "version", version)
    assert _get_hermes_version() == ("9.1.2-loki" if installed else VERSION)
    assert read == [DISTRIBUTION]


@pytest.mark.parametrize("configured", [None, "Hermes user header\\n", ""])
def test_whatsapp_prefix_brands_only_the_default(monkeypatch, configured):
    from gateway.config import PlatformConfig
    from plugins.platforms.whatsapp.adapter import WhatsAppAdapter

    monkeypatch.setenv("WHATSAPP_MODE", "self-chat")
    monkeypatch.delenv("WHATSAPP_REPLY_PREFIX", raising=False)
    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"reply_prefix": configured}))
    expected = "*Loki*\n────────────\n" if configured is None else configured.replace("\\n", "\n")
    assert adapter._effective_reply_prefix() == expected
