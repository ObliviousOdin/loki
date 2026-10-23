"""A hidden session verifier; its registration name is never an account identity."""
from __future__ import annotations

from hermes_cli.dashboard_auth.base import DashboardAuthProvider, RefreshExpiredError


class DeviceLinkProvider(DashboardAuthProvider):
    name = 'loki-device'
    display_name = 'Linked iPhone'
    supports_interactive_login = False

    def __init__(self, store):
        self.store = store

    def start_login(self, *, redirect_uri):
        raise NotImplementedError('Linked devices use signed challenges')

    def complete_login(self, **kwargs):
        raise NotImplementedError('Linked devices use signed challenges')

    def verify_session(self, *, access_token):
        return self.store.verify_token(access_token)

    def refresh_session(self, *, refresh_token):
        raise RefreshExpiredError('Linked devices require a signed challenge')

    def revoke_session(self, *, refresh_token):
        return None


def device_ticket_context(session):
    if not session.device_id:
        return None
    return {'device_link': {'home': session.device_home, 'host_id': session.device_host_id,
                            'device_id': session.device_id}}


def context_store(context):
    """Only an existing server-owned provider may resolve a ticket's private provenance."""
    from hermes_cli.dashboard_auth.registry import get_provider
    provider = get_provider(DeviceLinkProvider.name)
    if not isinstance(provider, DeviceLinkProvider) or not isinstance(context, dict):
        return None
    store = provider.store
    if context.get('home') != store.home or context.get('host_id') != store.host_id:
        return None
    return store if store.is_active(context.get('device_id', '')) else None
