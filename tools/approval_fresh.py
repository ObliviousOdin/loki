"""Fresh, once-only human consent for callers that cannot accept policy bypasses."""

from __future__ import annotations


def request_fresh_approval(tool_name: str, reason: str, *, approval_callback=None) -> dict:
    """Ask an attached human; never consult cached approvals or unattended/yolo policy."""
    from tools import approval as gate

    callback, is_cli, is_gateway, is_ask = gate._presence(approval_callback)
    session_key = gate.get_current_session_key()
    description = reason or f"Confirm {tool_name}"
    # No model-provided confirmation parameter or reusable receipt authorizes this call.
    if is_gateway or is_ask:
        notify = gate._gateway_notify_cb(session_key)
        if notify is None:
            return {"approved": False, "message": "Fresh confirmation unavailable: no attached approval viewer."}
        from agent.redact import redact_sensitive_text
        decision = gate._await_gateway_decision(session_key, notify, {
            "command": redact_sensitive_text(tool_name),
            "description": redact_sensitive_text(description),
            "pattern_key": "fresh_tool_confirmation",
            "pattern_keys": [], "allow_session": False, "allow_permanent": False,
        }, surface="gateway")
        accepted = (decision.get("resolved") is True and decision.get("choice") == "once"
                    and not decision.get("cancelled") and not decision.get("notify_failed"))
    elif is_cli:
        choice = gate.prompt_dangerous_approval(
            tool_name, description, approval_callback=callback,
            allow_session=False, allow_permanent=False,
        )
        accepted = choice == "once"
    else:
        accepted = False
    return {"approved": accepted, "message": None if accepted else
            "Action blocked: fresh confirmation was denied, unavailable, or unanswered. Do not retry automatically."}
