"""Opt-in, profile-scoped smart-home tools; registration never connects to a home."""

from __future__ import annotations

import json

from .client import Client, HomeError, settings

CHECKLIST = [
    "Set up an existing Home Assistant instance and add supported devices there.",
    "Set this plugin's Home Assistant address in Settings > Plugins > Smart home.",
    "Enter a dedicated Home Assistant access token in the masked token field.",
    "Add exact light.* or switch.* IDs to Allowed lights and switches.",
    "Run smart_home_check and smart_home_read while read-only; confirm the correct devices.",
    "Optionally enable Allow confirmed changes; each on/off change still needs a fresh approval.",
]


def _token() -> str:
    from agent.secret_scope import get_secret
    return (get_secret("LOKI_SMART_HOME_TOKEN", "") or "").strip()


def _client(ctx):
    config = settings(ctx)
    if not config.url:
        raise HomeError("unconfigured", "Set your Home Assistant address first.")
    token = _token()
    if not token:
        raise HomeError("authentication_required", "Enter the Home Assistant token in the masked settings field.")
    return Client(config, token)


def _allowed(client, entity):
    if not isinstance(entity, str) or entity not in client.config.entities:
        raise HomeError("denied", "This exact light or switch is outside the profile's allowlist.")


def _confirm(entity: str, state: str) -> bool:
    from tools.approval import request_tool_approval
    result = request_tool_approval("smart_home_set_state", f"Turn {entity} {state}?", require_fresh=True)
    return result.get("approved") is True


def _status(ctx, args):
    config = settings(ctx)
    return {"status": "unconfigured" if not config.url else "not_checked",
            "mode": "confirmed_control" if config.control else "read_only",
            "token_present": bool(_token()), "allowed_entities": list(config.entities),
            "connection_checked": False, "checklist": CHECKLIST}


def _check(ctx, args):
    client = _client(ctx)
    body = client.request("")
    if not isinstance(body, dict) or body.get("message") != "API running.":
        raise HomeError("error", "The configured address did not return a Home Assistant API response.")
    return {"status": "connected", "mode": "confirmed_control" if client.config.control else "read_only",
            "allowed_entities": list(client.config.entities)}


def _read(ctx, args):
    client = _client(ctx)
    entity = args.get("entity_id")
    if entity is not None:
        _allowed(client, entity)
    targets = [entity] if entity is not None else client.config.entities
    return {"status": "ok", "entities": [client.state(e) for e in targets],
            "scope": "Only explicitly allowed lights and switches are read."}


def _set_state(ctx, args):
    client = _client(ctx)
    entity, state = args.get("entity_id"), args.get("state")
    _allowed(client, entity)
    if state not in ("on", "off") or set(args) != {"entity_id", "state"}:
        raise HomeError("denied", "Choose on or off for one allowed light or switch; no other action parameters are accepted.")
    if not client.config.control:
        raise HomeError("read_only", "Changes are disabled. Review the device in read-only mode before enabling confirmed control.")
    before = client.state(entity)
    if before["state"] in ("unavailable", "unknown"):
        raise HomeError("unavailable", "The device is unavailable; no change was sent.")
    if not _confirm(entity, state):
        raise HomeError("confirmation_required", "The change was not confirmed. No command was sent; do not retry automatically.")
    if settings(ctx) != client.config or _token() != client.token:
        raise HomeError("configuration_changed", "Settings changed during confirmation. No command was sent.")
    client.request(f"services/{entity.split('.')[0]}/turn_{state}", body={"entity_id": entity})
    return {"status": "submitted", "entity_id": entity, "requested_state": state,
            "message": "Home Assistant accepted the request. Read the device again to verify its state."}


def _handler(ctx, action):
    def handle(args, **kwargs):
        try:
            if not isinstance(args, dict):
                raise HomeError("denied", "Expected an object of tool arguments.")
            result = action(ctx, args)
        except HomeError as exc:
            result = {"status": exc.status, "message": str(exc)}
        except (ImportError, TypeError, RuntimeError, ValueError, PermissionError):
            # Never return transport/secret exception text to the model or renderer.
            result = {"status": "error", "message": "Smart home could not complete this request. No automatic retry was attempted."}
        return json.dumps(result)
    return handle


def register(ctx):
    definitions = [
        ("smart_home_status", "Show local setup checklist and access mode without connecting.", {}, [], _status),
        ("smart_home_check", "Explicitly test the configured Home Assistant API; no device changes.", {}, [], _check),
        ("smart_home_read", "Read only allowed lights and switches; omit the ID to discover the configured scope.",
         {"entity_id": {"type": "string"}}, [], _read),
        ("smart_home_set_state", "Set one allowed light or switch on/off after fresh human confirmation.",
         {"entity_id": {"type": "string"}, "state": {"type": "string", "enum": ["on", "off"]}},
         ["entity_id", "state"], _set_state),
    ]
    for name, description, properties, required, action in definitions:
        ctx.register_tool(name=name, toolset="smart_home", description=description,
                          schema={"name": name, "description": description, "parameters": {
                              "type": "object", "properties": properties, "required": required,
                              "additionalProperties": False}}, handler=_handler(ctx, action))
