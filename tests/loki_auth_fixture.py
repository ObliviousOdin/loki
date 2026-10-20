"""Explicit synthetic authorization for positive provider integration fixtures.

These helpers are opt-in at individual tests or their local on-disk fixture.
They do not change the product defaults or authorize a real hosted application.
"""
from copy import deepcopy

import hermes_yaml as yaml


def configure_auth(monkeypatch, *, clients=(), adopt_external_logins=None, hosted_services=None):
    from hermes_cli import config

    original = config.load_config_readonly

    def configured():
        result = deepcopy(original())
        auth = result.setdefault("auth", {})
        auth.setdefault("oauth_clients", {}).update({
            provider: {"client_id": f"loki-test-{provider}-app"} for provider in clients
        })
        if adopt_external_logins is not None:
            auth["adopt_external_logins"] = adopt_external_logins
        if hosted_services is not None:
            auth["hosted_services"] = hosted_services
        return result

    monkeypatch.setattr(config, "load_config_readonly", configured)


def write_auth_config(home, *, clients=(), adopt_external_logins=None):
    """Give child processes the same explicit fixture authorization as their parent."""
    path = home / "config.yaml"
    result = yaml.safe_load(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    result = result or {}
    auth = result.setdefault("auth", {})
    auth.setdefault("oauth_clients", {}).update({
        provider: {"client_id": f"loki-test-{provider}-app"} for provider in clients
    })
    if adopt_external_logins is not None:
        auth["adopt_external_logins"] = adopt_external_logins
    path.write_text(yaml.safe_dump(result), encoding="utf-8")
