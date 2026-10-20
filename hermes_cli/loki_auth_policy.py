"""Explicit configuration for services whose upstream apps Loki does not own."""

from __future__ import annotations


def _auth_config() -> dict:
    from hermes_cli.config import load_config_readonly

    config = load_config_readonly()
    auth = config.get("auth") if isinstance(config, dict) else None
    return auth if isinstance(auth, dict) else {}


def require_oauth_client_id(provider: str, client_id: str | None = None) -> str:
    """Require an app supplied explicitly by the operator, before network/browser I/O."""
    if isinstance(client_id, str) and client_id.strip():
        return client_id.strip()
    clients = _auth_config().get("oauth_clients", {})
    entry = clients.get(provider, {}) if isinstance(clients, dict) else {}
    value = entry.get("client_id", "") if isinstance(entry, dict) else ""
    if isinstance(value, str) and value.strip():
        return value.strip()
    from hermes_cli.auth_constants import AuthError

    raise AuthError(
        f"Loki has no authorized OAuth application configured for {provider}. "
        f"Configure auth.oauth_clients.{provider}.client_id in Loki's config.yaml "
        "with an application authorized for your use, or select an API-key/local provider.",
        provider=provider, code="loki_oauth_app_not_configured")


def hosted_services_enabled() -> bool:
    """No anonymous accounts, welcome trials or hosted connector provisioning by default."""
    return _auth_config().get("hosted_services") is True


def require_hosted_services() -> None:
    from hermes_cli.auth_constants import AuthError

    if not hosted_services_enabled():
        raise AuthError(
            "Loki hosted services are not configured. Configure an authorized service and "
            "set auth.hosted_services before requesting account provisioning.",
            provider="nous", code="loki_hosted_service_not_configured")
