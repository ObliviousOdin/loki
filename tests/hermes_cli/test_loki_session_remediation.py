"""Authored recovery commands must preserve user session names and provider labels."""

import argparse
from contextlib import asynccontextmanager

import pytest

from hermes_cli import foreign_sessions, gateway_chat, sessions_cmd


def test_missing_session_preserves_requested_id_and_names_loki(capsys):
    session_id = "Hermes-3-session"
    assert sessions_cmd._not_found(session_id) == 1
    assert capsys.readouterr().out == f"No session '{session_id}'. Run: loki sessions list to find the id.\n"


def test_gateway_footer_and_model_keep_user_identity(monkeypatch):
    from hermes_cli.gateway_chat_view import GatewayChatView, resume_footer
    session_id = "session-Hermes-3"
    monkeypatch.setattr("hermes_cli.profiles.get_active_profile_name", lambda: "fabric")
    view = GatewayChatView(None, {"stored_session_id": session_id, "info": {"model": "nousresearch/Hermes-3"}})
    assert view.model == "Hermes-3" and view.session_id == session_id
    assert f"loki --resume {session_id} -p fabric" in resume_footer(session_id)
    assert GatewayChatView(None, {"stored_session_id": session_id}).model == "Loki"


def test_import_remedy_preserves_foreign_provider_and_new_session_id(tmp_path, monkeypatch, capsys):
    path = tmp_path / "foreign.jsonl"
    path.touch()
    calls = []

    def imported(source, selected, *, db):
        calls.append((source, selected, db))
        return "session-Hermes-3"

    monkeypatch.setattr(foreign_sessions, "import_foreign_session", imported)
    assert foreign_sessions.run_sessions_import(argparse.Namespace(from_source="codex", path=str(path))) == "session-Hermes-3"
    assert calls == [("codex", path, None)]
    output = capsys.readouterr().out
    assert "Imported Codex CLI session as session-Hermes-3" in output
    assert "Continue it with:  loki --resume session-Hermes-3" in output


@pytest.mark.asyncio
async def test_gateway_missing_resume_preserves_requested_name_and_lookup_order(monkeypatch):
    name = "Hermes-3 discussion with Fabric"
    calls = []

    class Peer:
        async def rpc(self, method, **params):
            if method == "runtime.describe":
                return {}
            assert method == "session.resume"
            calls.append(params)
            raise gateway_chat.GatewayClientError("not_found")

    @asynccontextmanager
    async def connected():
        yield Peer()

    monkeypatch.setattr(gateway_chat, "connect_gateway", connected)
    with pytest.raises(gateway_chat.GatewayClientError) as caught:
        await gateway_chat.run_gateway_chat(argparse.Namespace(resume=name, query="q", quiet=True))
    assert calls == [{"session_id": name}, {"title": name}]
    assert f"No session found matching '{name}'. Use 'loki sessions list'" in str(caught.value)


@pytest.mark.asyncio
async def test_gateway_missing_latest_points_at_public_loki_commands(tmp_path, monkeypatch):
    calls = []

    class Peer:
        async def rpc(self, method, **params):
            calls.append((method, params))
            raise gateway_chat.GatewayClientError("not_found")

    monkeypatch.setattr(gateway_chat, "_workspace_key", lambda _cwd: "owned-workspace")
    with pytest.raises(gateway_chat.GatewayClientError) as caught:
        await gateway_chat._resume_latest(Peer(), argparse.Namespace(in_dir=str(tmp_path)))
    assert calls == [("session.resume", {"latest": "cli", "workspace": "owned-workspace"})]
    assert "Start a new one with `loki`" in str(caught.value)
    assert "list sessions with `loki sessions list`" in str(caught.value)
