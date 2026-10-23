"""Derived display viewers carry credential custody separately from account ownership."""
import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from hermes_cli.dashboard_auth.device_links_live import Channel, DeviceLinkSocketMiddleware, revoke_channels
from hermes_cli.dashboard_auth.device_links_provider import DeviceLinkProvider
from hermes_cli.dashboard_auth.registry import clear_providers, register_provider
from hermes_cli.dashboard_auth.ws_tickets import TicketInvalid, consume_ticket, mint_ticket
from tests.hermes_cli.test_dashboard_device_links_store import approve_phone

pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_store',)


@pytest.fixture
def registered_phone(phone_store):
    store, owner, _ = phone_store
    _, claim = approve_phone(store, owner)
    clear_providers()
    register_provider(DeviceLinkProvider(store))
    context = {'home': store.home, 'host_id': store.host_id, 'device_id': claim['device_id']}
    yield store, owner, claim, context
    clear_providers()


@pytest.mark.asyncio
async def test_display_observe_propagates_only_server_credential_context(registered_phone, monkeypatch, tmp_path):
    from tui_gateway import server
    from tui_gateway.ws import WSTransport
    from tools.bot_desktop import runtime
    store, owner, claim, context = registered_phone
    monkeypatch.setattr(runtime, 'rfb_socket_path', lambda: tmp_path / 'fixture-rfb.sock')
    identity = {'provider': owner.provider, 'user_id': owner.user_id, 'issuer': owner.issuer}
    ws = SimpleNamespace(scope={'loki.device_channel': Channel(store, claim['device_id'])})
    transport = WSTransport(ws, asyncio.get_running_loop(), auth_identity=identity)
    response = await asyncio.to_thread(server.dispatch, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'display.observe', 'params': {}}, transport)
    assert 'result' in response, response
    info = consume_ticket(response['result']['ticket'])
    assert info['device_link'] == context and info['provider'] == 'bot-desktop'
    assert transport.auth_identity == identity and 'device_link' not in identity
    ordinary = WSTransport(SimpleNamespace(), asyncio.get_running_loop(), auth_identity=identity)
    response = await asyncio.to_thread(server.dispatch, {
        'jsonrpc': '2.0', 'id': 2, 'method': 'display.observe', 'params': {}}, ordinary)
    assert 'device_link' not in consume_ticket(response['result']['ticket'])


def test_revoke_retires_active_and_unused_display_ticket(registered_phone, monkeypatch):
    from hermes_cli import web_server
    from hermes_cli.web_routers import display
    store, _, claim, context = registered_phone
    monkeypatch.setattr(web_server.app.state, 'bound_host', '127.0.0.1', raising=False)
    monkeypatch.setattr(web_server.app.state, 'trusted_public_hosts', frozenset(), raising=False)
    async def bridge(ws, info):
        while True:
            await ws.receive_text()
    monkeypatch.setattr(display, '_bridge', bridge)
    app = FastAPI()
    app.include_router(display.router)
    app.add_middleware(DeviceLinkSocketMiddleware)
    def ticket():
        return mint_ticket(user_id='display:fixture', provider='bot-desktop', extra={
            'hermes_home': store.home, 'viewer_id': 'fixture', 'device_link': context})
    first, outstanding = ticket(), ticket()
    with TestClient(app, base_url='http://localhost') as client, client.websocket_connect('ws://localhost/api/display/ws?display_ticket=' + first) as ws:
        store.revoke(claim['device_id'])
        revoke_channels(store, claim['device_id'])
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
        assert closed.value.code == 4401
    with pytest.raises(TicketInvalid, match='device revoked'):
        consume_ticket(outstanding)
