"""Fresh tool consent cannot be replaced by cached or unattended approvals."""

import pytest

from tools import approval


@pytest.fixture(autouse=True)
def bypasses(monkeypatch):
    monkeypatch.setattr(approval, "_yolo_active", lambda: True)
    monkeypatch.setattr(approval, "is_approved", lambda *a: True)
    monkeypatch.setattr(approval.approval_context, "_get_approval_mode", lambda: "off")
    monkeypatch.setattr(approval, "get_current_session_key", lambda: "fresh-test")
    monkeypatch.setattr(approval, "_persist_choice", lambda *a: pytest.fail("fresh consent must never persist"))


@pytest.mark.parametrize("choice", ["once", "session", "always", "deny", "timeout", "cancelled", None])
def test_cli_accepts_only_fresh_once_even_with_all_bypasses(monkeypatch, choice):
    monkeypatch.setattr(approval, "_presence", lambda cb: (cb, True, False, False))
    def prompt(*a, **kw):
        assert kw["allow_session"] is False and kw["allow_permanent"] is False
        return choice
    monkeypatch.setattr(approval, "prompt_dangerous_approval", prompt)
    result = approval.request_tool_approval("test_action", "Confirm this exact action", require_fresh=True)
    assert result["approved"] is (choice == "once")


def test_unattended_and_disconnected_viewer_do_not_autoapprove(monkeypatch):
    for presence in [(None, False, False, False), (None, False, True, False)]:
        monkeypatch.setattr(approval, "_presence", lambda cb: presence)
        monkeypatch.setattr(approval, "_gateway_notify_cb", lambda sk: None)
        assert not approval.request_tool_approval("test_action", "Confirm", require_fresh=True)["approved"]


@pytest.mark.parametrize("decision,accepted", [
    ({"resolved": True, "choice": "once"}, True),
    ({"resolved": True, "choice": "always"}, False),
    ({"resolved": True, "choice": "deny"}, False),
    ({"resolved": False, "choice": "once"}, False),
    ({"resolved": True, "choice": "once", "cancelled": "viewer left"}, False),
    ({"resolved": True, "choice": "once", "notify_failed": True}, False),
])
def test_gateway_requires_current_resolved_once(monkeypatch, decision, accepted):
    monkeypatch.setattr(approval, "_presence", lambda cb: (None, False, True, False))
    monkeypatch.setattr(approval, "_gateway_notify_cb", lambda sk: lambda data: None)
    def wait(sk, cb, data, **kw):
        assert data["allow_session"] is False and data["allow_permanent"] is False
        return decision
    monkeypatch.setattr(approval, "_await_gateway_decision", wait)
    assert approval.request_tool_approval("test_action", "Confirm", require_fresh=True)["approved"] is accepted
