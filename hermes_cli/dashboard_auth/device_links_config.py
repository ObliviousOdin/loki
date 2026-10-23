"""Captured host configuration and bounded rendezvous registration for phone linking."""
from __future__ import annotations

import re
import time
from urllib.parse import urlsplit

import httpx
import idna

from hermes_cli.dashboard_auth.device_links_crypto import LinkError
from hermes_cli.dashboard_auth.device_links_store import DeviceLinkStore

SECRET_ENV = 'LOKI_PHONE_LINK_REGISTRATION_TOKEN'


def _registration_secret(home, name):
    from agent.secret_scope import build_profile_secret_scope, reset_secret_scope, set_secret_scope
    from hermes_cli.config import get_env_value
    token = set_secret_scope(build_profile_secret_scope(home), profile_home=str(home))
    try:
        return get_env_value(name) or ''
    finally:
        reset_secret_scope(token)


def owner_authorize_base(request, phone_origin):
    """Keep the upstream cookie on its configured callback host; redemption stays local."""
    from hermes_cli.dashboard_auth.prefix import normalise_prefix, resolve_public_url
    runner = getattr(request.app.state, 'gateway_runner', None)
    local = getattr(getattr(runner, 'session_api', None), 'api_origin', '')
    base = resolve_public_url() or local
    if not base or any(ord(c) <= 32 or c in '\\' for c in base):
        return None
    try:
        parsed, phone = urlsplit(base), urlsplit(phone_origin or '')
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.port == 0
                or (parsed.path and normalise_prefix(parsed.path) != parsed.path.rstrip('/'))):
            return None
        if parsed.scheme == 'http':
            return base if base == local and parsed.hostname in {'127.0.0.1', '::1'} else None
        if parsed.scheme != 'https':
            return None
        if (parsed.hostname.lower(), parsed.port or 443) == (phone.hostname, phone.port or 443):
            return None
    except ValueError:
        return None
    return base


def https_origin(value):
    if not isinstance(value, str) or not value or len(value) > 512 or any(c.isspace() for c in value):
        raise LinkError('invalid_https_origin')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or parsed.port not in (None, 443)):
        raise LinkError('invalid_https_origin')
    import ipaddress
    host = parsed.hostname
    if '%' in host:
        raise LinkError('invalid_https_origin')
    try:
        address = ipaddress.ip_address(host)
        canonical_host = '[' + address.compressed + ']' if address.version == 6 else address.compressed
    except ValueError:
        try:
            canonical_host = idna.encode(host, uts46=True, std3_rules=True).decode('ascii').lower()
        except idna.IDNAError:
            raise LinkError('invalid_https_origin') from None
    return 'https://' + canonical_host


class DeviceLinkService:
    def __init__(self, store, rendezvous_url, registration_secret):
        self.store, self.rendezvous_url = store, rendezvous_url
        self._registration_secret = registration_secret
        self.transport_verified_at = None
        self.transport_error = 'transport_unverified'

    def verify_transport(self):
        """An explicit owner action checks the public facade's canonical host binding."""
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', self.store.gateway_url + '/health') as response:
                    data = bytearray()
                    for chunk in response.iter_bytes(4097):
                        data.extend(chunk)
                        if len(data) > 4096:
                            raise LinkError('transport_unavailable')
                    import json
                    value = json.loads(data)
                    if (response.status_code != 200 or not isinstance(value, dict)
                            or value.get('service') != 'loki-phone-ingress'
                            or value.get('version') != 1 or value.get('ready') is not True
                            or value.get('host_id') != self.store.host_id):
                        raise LinkError('transport_unavailable')
        except (httpx.HTTPError, ValueError):
            self.transport_verified_at = None
            self.transport_error = 'transport_unreachable'
            raise LinkError('transport_unavailable') from None
        self.transport_verified_at = int(time.time())
        self.transport_error = None

    @property
    def transport_ready(self):
        return self.transport_verified_at is not None and time.time() - self.transport_verified_at < 60

    def registration(self, pairing):
        self._request('POST', '/v1/pairings', pairing)

    def cancellation(self, pairing_id):
        self._request('DELETE', '/v1/pairings/' + pairing_id, None)

    def _request(self, method, path, body):
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                response = client.request(method, self.rendezvous_url + path, json=body,
                    headers={'Authorization': 'Bearer ' + self._registration_secret})
            if response.status_code not in (200, 201, 204):
                raise LinkError('rendezvous_unavailable')
        except httpx.HTTPError:
            raise LinkError('rendezvous_unavailable') from None


def configure_device_links(app):
    """Called once from the canonical dashboard mount's launch-home context."""
    from hermes_cli.config import load_config
    from hermes_cli.dashboard_auth.device_links_provider import DeviceLinkProvider
    from hermes_cli.dashboard_auth.registry import (
        get_provider, register_global_provider, unregister_global_provider)
    from hermes_constants import get_hermes_home

    app.state.device_links_service = None
    config = (load_config().get('dashboard') or {}).get('device_links') or {}
    app.state.device_links_enabled = config.get('enabled') is True
    previous = get_provider(DeviceLinkProvider.name)
    if isinstance(previous, DeviceLinkProvider):
        unregister_global_provider(DeviceLinkProvider.name, previous)
    if not app.state.device_links_enabled:
        return
    try:
        gateway_url, rendezvous_url = map(https_origin, (config.get('gateway_url'), config.get('rendezvous_url')))
        name = config.get('host_name')
        if not isinstance(name, str) or not name.strip() or len(name.encode()) > 120 or any(ord(c) < 32 for c in name):
            raise LinkError('invalid_host_name')
        name = name.strip()
        secret_env = config.get('registration_secret_env') or SECRET_ENV
        if not isinstance(secret_env, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', secret_env):
            raise LinkError('invalid_secret_name')
        secret = _registration_secret(get_hermes_home(), secret_env)
        if len(secret) < 43 or any(c.isspace() for c in secret):
            raise LinkError('registration_secret_missing')
        store = DeviceLinkStore(get_hermes_home(), gateway_url=gateway_url, host_name=name)
    except (ValueError, OSError) as exc:
        app.state.device_links_error = str(exc)
        return
    app.state.device_links_error = ''
    app.state.device_links_service = DeviceLinkService(store, rendezvous_url, secret)
    register_global_provider(DeviceLinkProvider(store))
