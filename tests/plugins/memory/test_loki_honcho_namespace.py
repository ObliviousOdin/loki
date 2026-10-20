"""Exercise the optional provider with real config resolution and a network-free SDK double."""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from datetime import UTC, datetime

import pytest

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from plugins.memory import _load_package

SOURCE = Path(__file__).resolve().parents[3] / "optional-plugins/honcho"


@pytest.fixture
def provider(tmp_path, monkeypatch):
    root = tmp_path / ".loki"
    root.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv("LOKI_HOME", str(root))
    token = set_hermes_home_override(root)
    package = _load_package(SOURCE, "honcho")
    assert package is not None
    client = importlib.import_module(package.__name__ + ".client")
    monkeypatch.setattr(client, "_get_default_hermes_home", lambda: root)
    monkeypatch.setattr("hermes_cli.profiles._get_default_hermes_home", lambda: root)
    monkeypatch.setattr("hermes_cli.profiles.get_active_profile_name", lambda: "default")
    monkeypatch.setattr(client, "get_secret", lambda name, default=None:
                        "synthetic-owned-key" if name == "HONCHO_API_KEY" else default)
    client.reset_honcho_client()
    try:
        yield package, client, root
    finally:
        client.reset_honcho_client()
        reset_hermes_home_override(token)


def _foreign_canaries(home):
    raw = {"defaultHost": "hermes", "hosts": {"hermes": {
        "apiKey": "synthetic-foreign-key", "workspace": "foreign-memory", "aiPeer": "foreign-peer"}}}
    paths = [home / ".honcho/config.json", home / ".hermes/honcho.json", home / ".fabric/honcho.json"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw), encoding="utf-8")
    return {path: path.read_bytes() for path in paths}


@pytest.mark.parametrize("profile", ["default", "work", "fabric", "hermes"])
def test_fresh_profile_never_adopts_foreign_global_memory(provider, tmp_path, monkeypatch, profile):
    package, client, root = provider
    foreign = _foreign_canaries(tmp_path)
    home = root if profile == "default" else root / "profiles" / profile
    home.mkdir(parents=True, exist_ok=True)
    token = set_hermes_home_override(home)
    monkeypatch.setattr("hermes_cli.profiles.get_active_profile_name", lambda: profile)
    try:
        config = client.HonchoClientConfig.from_global_config()
    finally:
        reset_hermes_home_override(token)
    expected = "loki" if profile == "default" else f"loki_{profile}"
    assert (config.host, config.workspace_id, config.ai_peer) == (expected, expected, expected)
    assert config.api_key == "synthetic-owned-key"
    assert config.config_path == home / "honcho.json"
    assert config.raw == {} and config.enabled is True
    assert package.HonchoMemoryProvider().backup_paths() == []
    assert all(path.read_bytes() == before for path, before in foreign.items())


def test_sdk_constructor_uses_owned_defaults_without_network(provider, monkeypatch):
    _package, client, root = provider
    captured = []

    def construct(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(sys.modules, "honcho", SimpleNamespace(Honcho=construct))
    config = client.HonchoClientConfig.from_global_config()
    client.get_honcho_client(config)
    assert len(captured) == 1
    assert captured[0]["workspace_id"] == "loki"
    assert captured[0]["api_key"] == "synthetic-owned-key"
    assert captured[0]["default_headers"]["X-Honcho-Host"].startswith("loki/")
    assert config.config_path == root / "honcho.json"


def test_missing_peer_and_session_fallbacks_are_owned_but_explicit_values_survive(provider):
    package, _client, _root = provider
    peers = importlib.import_module(package.__name__ + ".session_peers")
    assert peers.assistant_peer_id_for(SimpleNamespace(ai_peer=None)) == "loki-assistant"
    assert peers.assistant_peer_id_for(SimpleNamespace(ai_peer="hermes-assistant")) == "hermes-assistant"
    config = SimpleNamespace(resolve_session_name=lambda **_kw: None)
    instance = package.HonchoMemoryProvider()
    assert instance._resolve_session_key(config, "", cwd="/") == "loki-default"
    assert instance._resolve_session_key(config, "hermes-explicit-session", cwd="/") == "hermes-explicit-session"


def test_explicit_own_file_values_and_host_choice_are_preserved(provider, monkeypatch):
    _package, client, root = provider
    explicit = {"defaultHost": "Hermes chosen host", "hosts": {"Hermes chosen host": {
        "workspace": "Hermes chosen workspace", "aiPeer": "Hermes chosen peer", "apiKey": "explicit-owned-key"}},
        "baseUrl": "http://127.0.0.1:8000", "sessionStrategy": "per-repo"}
    path = root / "honcho.json"
    path.write_text(json.dumps(explicit), encoding="utf-8")
    original = path.read_bytes()
    config = client.HonchoClientConfig.from_global_config()
    assert (config.host, config.workspace_id, config.ai_peer) == (
        "Hermes chosen host", "Hermes chosen workspace", "Hermes chosen peer")
    assert config.api_key == "explicit-owned-key" and config.session_strategy == "per-repo"
    assert config.base_url == "http://127.0.0.1:8000"
    assert client.HonchoClientConfig.from_env(workspace_id="hermes").workspace_id == "hermes"
    assert path.read_bytes() == original


def test_named_profile_reads_explicit_own_root_host_block(provider, monkeypatch):
    _package, client, root = provider
    path = root / "honcho.json"
    path.write_text(json.dumps({"hosts": {"loki_work": {"workspace": "chosen", "aiPeer": "peer"}}}), encoding="utf-8")
    token = set_hermes_home_override(root / "profiles/work")
    monkeypatch.setattr("hermes_cli.profiles.get_active_profile_name", lambda: "work")
    try:
        config = client.HonchoClientConfig.from_global_config()
    finally:
        reset_hermes_home_override(token)
    assert (config.host, config.workspace_id, config.ai_peer) == ("loki_work", "chosen", "peer")
    assert config.config_path == path


def test_explicit_config_path_and_backend_strings_remain_operator_choices(provider, tmp_path):
    _package, client, _root = provider
    selected = tmp_path / "operator selected Honcho.json"
    selected.write_text(json.dumps({"workspace": "hermes", "aiPeer": "explicit peer"}), encoding="utf-8")
    config = client.HonchoClientConfig.from_global_config(host="explicit host", config_path=selected)
    assert config.config_path == selected
    assert (config.host, config.workspace_id, config.ai_peer) == ("explicit host", "hermes", "explicit peer")


def test_oauth_requires_owned_client_before_socket_or_browser(provider, monkeypatch):
    package, _client, _root = provider
    flow = importlib.import_module(package.__name__ + ".oauth_flow")
    from hermes_cli.auth_constants import AuthError

    monkeypatch.setattr("hermes_cli.loki_auth_policy._auth_config", dict)
    monkeypatch.setattr("agent.secret_scope.get_secret", lambda _key, default=None: default)

    def prohibited(*_args, **_kwargs):
        raise AssertionError("unconfigured OAuth must not open a socket/browser or make requests")

    monkeypatch.setattr(flow, "_bind_loopback_server", prohibited)
    monkeypatch.setattr("httpx.get", prohibited)
    monkeypatch.setattr("httpx.post", prohibited)
    with pytest.raises(AuthError, match="no authorized OAuth application"):
        flow.authorize_via_loopback(open_url=prohibited)


def test_explicit_oauth_client_and_self_hosted_endpoint_remain_supported(provider, monkeypatch):
    package, _client, _root = provider
    flow = importlib.import_module(package.__name__ + ".oauth_flow")
    monkeypatch.setattr("agent.secret_scope.get_secret", lambda name, default=None:
                        "owned-test-client" if name == "HONCHO_OAUTH_CLIENT_ID" else default)
    endpoints = flow.resolve_endpoints(environment="production", base_url="https://honcho.example.invalid")
    assert endpoints.client_id == "owned-test-client"
    assert endpoints.token_url == "https://honcho.example.invalid/oauth/token"


def test_fallback_traceback_retains_location_but_never_error_secrets(provider, caplog):
    package, _client, _root = provider
    diagnostics = importlib.import_module(package.__name__ + ".fallback_diagnostics")
    secret = "synthetic-private-Honcho-credential"
    try:
        raise ValueError(secret)
    except ValueError:
        with caplog.at_level(logging.ERROR):
            logging.getLogger("loki.honcho.test").exception("provider fallback", exc_info=diagnostics.redacted_exc_info())
    record = caplog.records[-1]
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert "ValueError: provider error details omitted" in formatted
    assert "test_fallback_traceback_retains_location_but_never_error_secrets" in formatted


def test_actual_config_fallback_records_do_not_expose_error_payload(provider, monkeypatch, caplog):
    _package, client, root = provider
    (root / "honcho.json").write_text("{}", encoding="utf-8")
    secret = "synthetic-private-credential-in-provider-error"

    def unreadable(_path):
        raise OSError(secret)

    monkeypatch.setattr(client, "_read_config", unreadable)
    with caplog.at_level(logging.DEBUG):
        config = client.HonchoClientConfig.from_global_config()
    assert config.api_key == "synthetic-owned-key" and config.workspace_id == "loki"
    assert caplog.records
    assert all(secret not in logging.Formatter().format(record) for record in caplog.records)
    assert any("OSError" in logging.Formatter().format(record) for record in caplog.records)


def test_actual_session_init_fallback_never_logs_provider_error_payload(provider, monkeypatch, caplog):
    package, client, _root = provider
    instance = package.HonchoMemoryProvider()
    instance._config = client.HonchoClientConfig.from_env()
    instance._lazy_init_kwargs = {"platform": "cli"}
    instance._lazy_init_session_id = "owned-session"
    secret = "synthetic-credential-in-SDK-error"

    def failed(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(instance, "_do_session_init", failed)
    with caplog.at_level(logging.DEBUG):
        assert instance._run_session_init("foreground") is False
    assert instance._manager is None and instance._session_initialized is False
    assert all(secret not in logging.Formatter().format(record) for record in caplog.records)
    assert any("session init failed: RuntimeError" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("explicit", [False, True])
def test_enabled_injection_audit_owns_default_and_preserves_explicit_path(provider, tmp_path, monkeypatch, explicit):
    package, client, root = provider
    foreign = tmp_path / ".honcho/injection.log"
    foreign.parent.mkdir()
    foreign.write_bytes(b"foreign injection audit")
    requested = tmp_path / "manual audit/Honcho selected.log"
    if explicit:
        monkeypatch.setenv("HONCHO_INJECTION_LOG", str(requested))
    else:
        monkeypatch.delenv("HONCHO_INJECTION_LOG", raising=False)
    instance = package.HonchoMemoryProvider()
    path = instance._resolve_injection_log_path(client._HostLookup({}, {"logging": True}))
    expected = requested if explicit else root / "logs/honcho-injection.log"
    assert path == str(expected)
    instance._injection_log_path = path
    assert instance._log_injection("test", "own audit") == "own audit"
    assert json.loads(expected.read_text(encoding="utf-8"))["payload"] == "own audit"
    assert foreign.read_bytes() == b"foreign injection audit"


@pytest.mark.parametrize("location,fields", [
    ("profile", {}), ("root", {}),
    ("root", {"workspace": "Hermes chosen workspace", "aiPeer": "Hermes chosen peer"}),
])
def test_profile_rename_preserves_resolved_backend_identity(provider, tmp_path, monkeypatch, location, fields):
    _package, client, root = provider
    from hermes_cli import profiles

    foreign = _foreign_canaries(tmp_path)
    old = root / "profiles/old"
    old.mkdir(parents=True)
    path = (old if location == "profile" else root) / "honcho.json"
    path.write_text(json.dumps({**fields, "hosts": {"loki_old": {"enabled": True}}}), encoding="utf-8")
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "old")
    token = set_hermes_home_override(old)
    try:
        before = client.HonchoClientConfig.from_global_config()
    finally:
        reset_hermes_home_override(token)
    original_read = Path.read_text

    def guarded(candidate, *args, **kwargs):
        assert candidate not in foreign, "renaming must not read another application's config"
        return original_read(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    profiles.rename_profile("old", "renamed")
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "renamed")
    token = set_hermes_home_override(root / "profiles/renamed")
    try:
        after = client.HonchoClientConfig.from_global_config()
    finally:
        reset_hermes_home_override(token)
    assert before.workspace_id == after.workspace_id
    assert before.ai_peer == after.ai_peer
    assert after.host == "loki_renamed"
    assert all(path.read_bytes() == raw for path, raw in foreign.items())


@pytest.mark.parametrize("profile,explicit", [("default", False), ("work", False), ("work", True)])
def test_setup_enter_defaults_use_owned_host_without_changing_explicit_values(provider, monkeypatch, profile, explicit):
    package, client, root = provider
    command = importlib.import_module(package.__name__ + ".cli")
    home = root if profile == "default" else root / "profiles" / profile
    home.mkdir(parents=True, exist_ok=True)
    host = "loki" if profile == "default" else f"loki_{profile}"
    fields = {"workspace": "Hermes chosen workspace", "aiPeer": "Hermes chosen peer"} if explicit else {}
    (home / "honcho.json").write_text(json.dumps({"hosts": {host: fields}}), encoding="utf-8")
    monkeypatch.setattr("hermes_cli.profiles.get_active_profile_name", lambda: profile)
    monkeypatch.setattr(command, "_ensure_sdk_installed", lambda: True)
    monkeypatch.setattr(command, "_setup_identity_mapping", lambda *_args: None)
    monkeypatch.setattr(command, "_setup_tuning", lambda *_args: None)
    monkeypatch.setattr(command, "_connect", lambda host, **_kw:
                        (client.HonchoClientConfig.from_global_config(host=host), object()))
    defaults = {}

    def enter(label, default="", **_kwargs):
        defaults[label] = default
        return "local" if label == "Cloud or local?" else default

    monkeypatch.setattr(command, "_prompt", enter)
    token = set_hermes_home_override(home)
    try:
        command.cmd_setup(SimpleNamespace())
    finally:
        reset_hermes_home_override(token)
    assert defaults["AI peer name"] == fields.get("aiPeer", host)
    assert defaults["Workspace ID"] == fields.get("workspace", host)
    stored = json.loads((home / "honcho.json").read_text(encoding="utf-8"))["hosts"][host]
    assert stored["aiPeer"] == defaults["AI peer name"]
    assert stored["workspace"] == defaults["Workspace ID"]


@pytest.mark.parametrize("aware", [False, True])
def test_history_order_keeps_missing_timestamps_first(provider, aware):
    package, _client, _root = provider
    session = importlib.import_module(package.__name__ + ".session")
    timezone = UTC if aware else None
    older = SimpleNamespace(created_at=datetime(2026, 1, 1, tzinfo=timezone))
    newer = SimpleNamespace(created_at=datetime(2026, 1, 2, tzinfo=timezone))
    unknown = SimpleNamespace(created_at=None)
    manager = object.__new__(session.HonchoSessionManager)
    manager._context_tokens = 1024
    manager._authed_call = lambda _label, call: call()
    manager._sdk_session = lambda _sid: SimpleNamespace(context=lambda **_kw:
                                                        SimpleNamespace(messages=[newer, unknown, older]))
    assert manager._load_existing_messages("own-session") == [unknown, older, newer]
