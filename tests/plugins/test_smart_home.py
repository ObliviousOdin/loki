"""Optional smart-home capability through the real plugin discovery and tool registry."""

import io
import json
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from hermes_cli.config import atomic_config_write
from hermes_cli.plugins import PluginManager
from tools.registry import registry


@pytest.fixture
def home_plugin(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    shutil.copytree(Path(__file__).resolve().parents[2] / "optional-plugins" / "smart-home",
                    home / "plugins" / "smart-home")
    config = {"plugins": {"enabled": ["smart-home"], "entries": {"smart-home": {"settings": {
        "url": "http://homeassistant.local:8123", "allowed_entities": ["light.kitchen", "switch.lamp"],
        "allow_control": False,
    }}}}}
    atomic_config_write(home / "config.yaml", config)
    manager = PluginManager()
    monkeypatch.setattr(manager, "_scan_entry_points", list)
    monkeypatch.setattr(manager, "_get_bundled_plugins_dir", lambda: tmp_path / "no-bundled", raising=False)
    manager.discover_and_load()
    loaded = manager._plugins["smart-home"]
    assert loaded.enabled and not loaded.error
    module = loaded.module
    from agent.secret_scope import get_secret
    monkeypatch.setattr("agent.secret_scope.get_secret", lambda key, default="": "fixture-token")
    requests = []
    responses = []
    def open_request(request, timeout):
        requests.append(request)
        assert timeout == 5
        if responses:
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
        elif "/states/" in request.full_url:
            value = {"entity_id": request.full_url.rsplit("/", 1)[-1], "state": "off",
                     "attributes": {"friendly_name": "Kitchen", "private_attribute": "hidden"}}
        else:
            value = {"message": "API running."}
        return io.BytesIO(json.dumps(value).encode())
    from types import SimpleNamespace
    client_module = __import__(module.__name__ + ".client", fromlist=["Client"])
    monkeypatch.setattr(client_module, "build_opener", lambda *a: SimpleNamespace(open=open_request))
    def call(name, args=None):
        return json.loads(registry.get_entry(name, scope=manager.scope_key).handler(args or {}))
    def configure(**kwargs):
        config["plugins"]["entries"]["smart-home"]["settings"].update(kwargs)
        atomic_config_write(home / "config.yaml", config)
    yield SimpleNamespace(call=call, configure=configure, requests=requests, responses=responses,
                          module=module, client=client_module, real_get_secret=get_secret)
    manager.unload("smart-home")


def test_registration_status_and_empty_scope_never_connect(home_plugin):
    p = home_plugin
    p.configure(url="", allowed_entities=[])
    status = p.call("smart_home_status")
    assert status["status"] == "unconfigured" and status["mode"] == "read_only"
    assert status["checklist"] and not status["connection_checked"]
    assert not p.requests
    assert p.call("smart_home_check")["status"] == "unconfigured"
    p.configure(url="http://homeassistant.local:8123")
    assert p.call("smart_home_read")["entities"] == []
    assert not p.requests


def test_explicit_check_and_scoped_read_exclude_private_attributes(home_plugin):
    p = home_plugin
    assert p.call("smart_home_check")["status"] == "connected"
    result = p.call("smart_home_read", {"entity_id": "light.kitchen"})
    assert result["entities"] == [{"entity_id": "light.kitchen", "name": "Kitchen", "state": "off"}]
    assert len(p.requests) == 2


@pytest.mark.parametrize("entity", ["light.other", "camera.front", "lock.door", "switch.lamp/../../services", None])
def test_denied_entities_never_make_network_calls(home_plugin, entity):
    p = home_plugin
    assert p.call("smart_home_set_state", {"entity_id": entity, "state": "on"})["status"] == "denied"
    assert not p.requests


def test_missing_auth_and_default_read_only_never_send_device_changes(home_plugin, monkeypatch):
    p = home_plugin
    assert p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})["status"] == "read_only"
    assert not p.requests
    monkeypatch.setattr("agent.secret_scope.get_secret", lambda *a: "")
    assert p.call("smart_home_check")["status"] == "authentication_required"
    assert not p.requests


@pytest.mark.parametrize("approved", [True, False])
def test_control_requires_fresh_host_consent_for_one_exact_entity(home_plugin, monkeypatch, approved):
    p = home_plugin
    p.configure(allow_control=True)
    def approval(tool, reason, **kwargs):
        assert kwargs == {"require_fresh": True}
        assert "light.kitchen" in reason and "on" in reason
        return {"approved": approved}
    monkeypatch.setattr("tools.approval.request_tool_approval", approval)
    result = p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})
    assert result["status"] == ("submitted" if approved else "confirmation_required")
    writes = [r for r in p.requests if r.method == "POST"]
    assert len(writes) == int(approved)
    if writes:
        assert writes[0].full_url.endswith("/api/services/light/turn_on")
        assert json.loads(writes[0].data) == {"entity_id": "light.kitchen"}


def test_unavailable_device_and_configuration_change_prevent_writes(home_plugin, monkeypatch):
    p = home_plugin
    p.configure(allow_control=True)
    p.responses.append({"entity_id": "light.kitchen", "state": "unavailable"})
    assert p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})["status"] == "unavailable"
    def changed(*a, **kw):
        p.configure(allowed_entities=[])
        return {"approved": True}
    monkeypatch.setattr("tools.approval.request_tool_approval", changed)
    assert p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})["status"] == "configuration_changed"
    assert all(r.method == "GET" for r in p.requests)


@pytest.mark.parametrize("failure,status", [
    (URLError("fixture-token must not escape"), "offline"),
    (HTTPError("http://fixture", 401, "fixture-token", {}, None), "authentication_required"),
    (HTTPError("http://fixture", 404, "fixture-token", {}, None), "unavailable"),
    (HTTPError("http://fixture", 302, "redirect", {}, None), "error"),
])
def test_safe_connection_failures_are_redacted(home_plugin, failure, status):
    p = home_plugin
    p.responses.append(failure)
    result = p.call("smart_home_check")
    assert result["status"] == status
    assert "fixture-token" not in json.dumps(result)


def test_uncertain_write_is_not_retried(home_plugin, monkeypatch):
    p = home_plugin
    p.configure(allow_control=True)
    monkeypatch.setattr("tools.approval.request_tool_approval", lambda *a, **kw: {"approved": True})
    p.responses.extend([{"entity_id": "light.kitchen", "state": "off"}, URLError("lost response")])
    assert p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})["status"] == "outcome_unknown"
    assert len([r for r in p.requests if r.method == "POST"]) == 1


def test_real_host_gate_blocks_without_viewer_even_when_approvals_are_off(home_plugin, monkeypatch):
    from tools import approval
    p = home_plugin
    p.configure(allow_control=True)
    monkeypatch.setattr(approval, "_presence", lambda cb: (None, False, False, False))
    monkeypatch.setattr(approval, "_yolo_active", lambda: True)
    monkeypatch.setattr(approval, "is_approved", lambda *a: True)
    result = p.call("smart_home_set_state", {"entity_id": "light.kitchen", "state": "on"})
    assert result["status"] == "confirmation_required"
    assert all(r.method == "GET" for r in p.requests)


def test_profile_scoped_secret_miss_does_not_borrow_launch_token(home_plugin, monkeypatch):
    from agent import secret_scope
    p = home_plugin
    monkeypatch.setattr(secret_scope, "get_secret", p.real_get_secret)
    monkeypatch.setenv("LOKI_SMART_HOME_TOKEN", "foreign-launch-token")
    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({})
    try:
        assert p.module._token() == ""
    finally:
        secret_scope.reset_secret_scope(token)
        secret_scope.set_multiplex_active(False)


@pytest.mark.parametrize("configuration", [
    {"url": "http://public.example"}, {"url": "https://user:password@example.com"},
    {"url": "https://example.com/path"}, {"allowed_entities": ["camera.front"]},
    {"allow_control": "true"},
])
def test_invalid_settings_fail_closed(home_plugin, configuration):
    p = home_plugin
    p.configure(**configuration)
    assert p.call("smart_home_status")["status"] == "invalid_configuration"
    assert not p.requests
