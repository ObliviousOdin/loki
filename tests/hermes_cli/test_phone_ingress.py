"""The phone's public facade cannot admit private Mac credentials or arbitrary routes."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hermes_cli.phone_ingress import PhoneIngress

ORIGIN = 'https://phone.example.test'
HOST_ID = 'a' * 64
TOKEN = 'synthetic-phone-bearer-0123456789'
PROTOCOLS = ['hermes-gateway-v1', 'hermes-gateway-ticket.synthetic_0123456789']


@pytest.fixture
def facade(tmp_path):
    seen = []

    def upstream(request):
        seen.append(request)
        if request.url.path == '/api/health':
            return httpx.Response(200, json={'ok': True, 'auth_required': True})
        if request.url.path == '/auth/device/status':
            return httpx.Response(200, json={'ready': True, 'host_id': HOST_ID, 'gateway_url': ORIGIN})
        if request.url.path == '/api/auth/me':
            return httpx.Response(200, json={'user_id': 'synthetic-account', 'provider': 'synthetic-provider'})
        return httpx.Response(200, json={'ok': True}, headers={'Set-Cookie': 'private=must-not-forward'})

    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    target = SimpleNamespace(api_origin='http://127.0.0.1:12345')
    ingress = PhoneIngress(tmp_path, ORIGIN, endpoint=lambda home: target, client=client)
    app = Starlette(routes=[Route('/health', ingress.health), WebSocketRoute('/api/ws', ingress.websocket),
        Route('/{path:path}', ingress.http, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])])
    with TestClient(app) as browser:
        yield browser, ingress, seen


@pytest.mark.parametrize('path,method', [
    ('/api/device-links', 'GET'), ('/api/device-links/pairings', 'POST'),
    ('/api/host/identity', 'GET'), ('/api/health/retirement', 'POST'),
    ('/auth/native/token', 'POST'), ('/auth/native/authorize', 'GET'),
    ('/auth/password-login', 'POST'), ('/api/config', 'GET'), ('/', 'GET'),
])
def test_private_and_unselected_surfaces_never_reach_the_gateway(facade, path, method):
    browser, _, seen = facade
    result = browser.request(method, path, headers={'Authorization': 'Bearer ' + TOKEN})
    assert result.status_code == 404
    assert seen == []


def test_private_header_and_browser_cookie_cannot_authorize_a_phone(facade):
    browser, _, seen = facade
    response = browser.get('/api/auth/me', headers={
        'X-Hermes-Gateway-Ticket': 'synthetic-private-grant',
        'X-Session-Token': 'synthetic-static-token', 'Cookie': 'hermes_session=synthetic-cookie'})
    assert response.status_code == 401
    assert seen == []


def test_forwards_only_explicit_mobile_auth_headers_and_forces_public_origin(facade):
    browser, _, seen = facade
    result = browser.get('/api/auth/me', headers={
        'Authorization': 'Bearer ' + TOKEN, 'X-Hermes-Gateway-Ticket': 'synthetic-private-grant',
        'Cookie': 'hermes_session=synthetic-cookie', 'X-Session-Token': 'synthetic-static-token',
        'Origin': 'http://localhost', 'X-Forwarded-For': '127.0.0.1',
        'X-Forwarded-Prefix': '/private', 'X-Forwarded-Proto': 'http',
    })
    assert result.status_code == 200
    forwarded = seen[0]
    assert forwarded.url.host == '127.0.0.1'
    assert forwarded.headers['Host'] == 'phone.example.test'
    assert forwarded.headers['Origin'] == ORIGIN
    assert forwarded.headers['X-Forwarded-Proto'] == 'https'
    assert forwarded.headers['Authorization'] == 'Bearer ' + TOKEN
    for name in ('X-Hermes-Gateway-Ticket', 'Cookie', 'X-Session-Token', 'X-Forwarded-For', 'X-Forwarded-Prefix'):
        assert name not in forwarded.headers
    assert 'Set-Cookie' not in result.headers
    assert result.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('query', ['token=x', '%74oken=x', 'internal=x', 'ticket=x', 'ACCESS_TOKEN=x', 'refresh_token=x'])
def test_url_credentials_are_refused_before_proxying(facade, query):
    browser, _, seen = facade
    assert browser.get('/api/auth/me?' + query, headers={'Authorization': 'Bearer ' + TOKEN}).status_code == 404
    assert seen == []


def test_bootstrap_accepts_no_bearer_and_bounds_the_body_before_forwarding(facade):
    browser, _, seen = facade
    assert browser.post('/auth/device/claims', json={'synthetic': True}).status_code == 200
    assert len(seen) == 1
    assert browser.post('/auth/device/claims', content=b'x' * 4097).status_code == 413
    assert len(seen) == 1


def test_unverified_bearer_is_refused_before_a_mutation_body_is_read(facade):
    browser, ingress, _ = facade
    seen = []
    def upstream(request):
        seen.append(request)
        return httpx.Response(401, json={'detail': 'Unauthorized'})
    ingress.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    response = browser.post('/api/audio/transcribe', content=b'x' * 4097,
        headers={'Authorization': 'Bearer ' + TOKEN})
    assert response.status_code == 401
    assert [request.url.path for request in seen] == ['/api/auth/me']


@pytest.mark.asyncio
async def test_invalid_bearer_refusal_never_receives_the_streamed_upload(facade):
    _, ingress, _ = facade
    ingress.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    async def unread_body():
        raise AssertionError('An unauthenticated upload must not be read')
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/audio/transcribe',
        'scheme': 'http', 'query_string': b'', 'headers': [(b'authorization', ('Bearer ' + TOKEN).encode())],
        'client': ('192.0.2.1', 1234), 'server': ('127.0.0.1', 9450)}, receive=unread_body)
    assert (await ingress.http(request)).status_code == 401


def test_get_body_is_refused_and_voice_timeout_preserves_native_warmup_budget(facade):
    browser, _, seen = facade
    headers = {'Authorization': 'Bearer ' + TOKEN}
    assert browser.request('GET', '/api/auth/me', content=b'x', headers=headers).status_code == 413
    assert seen == []
    assert browser.post('/api/audio/stt-lease', json={'active': True}, headers=headers).status_code == 200
    assert [request.url.path for request in seen] == ['/api/auth/me', '/api/audio/stt-lease']
    assert seen[1].extensions['timeout']['read'] >= 180


def test_public_rate_buckets_bound_state_and_do_not_share_two_clients(facade):
    browser, ingress, _ = facade
    tick = [0]
    ingress.clock = lambda: tick[0]
    for _ in range(120):
        assert browser.post('/auth/device/poll', json={}, headers={'CF-Connecting-IP': '192.0.2.1'}).status_code == 200
    assert browser.post('/auth/device/poll', json={}, headers={'CF-Connecting-IP': '192.0.2.1'}).status_code == 429
    assert browser.post('/auth/device/poll', json={}, headers={'CF-Connecting-IP': '192.0.2.2'}).status_code == 200
    for index in range(2, 1024):
        request = Request({'type': 'http', 'headers': [(b'cf-connecting-ip', f'2001:db8::{index:x}'.encode())], 'client': ('127.0.0.1', 1)})
        assert ingress._allow_public(request, 'bootstrap')
    assert browser.post('/auth/device/poll', json={}, headers={'CF-Connecting-IP': '198.51.100.1'}).status_code == 429
    assert len(ingress._rates) == 1024
    tick[0] = 60
    assert browser.post('/auth/device/poll', json={}, headers={'CF-Connecting-IP': '198.51.100.1'}).status_code == 200


@pytest.mark.parametrize('gate,origin,expected', [(True, ORIGIN, 200), (False, ORIGIN, 503), (True, 'https://wrong.example.test', 503)])
def test_health_requires_gated_canonical_gateway_and_exact_phone_origin(facade, gate, origin, expected):
    browser, ingress, _ = facade
    def upstream(request):
        if request.url.path == '/api/health':
            return httpx.Response(200, json={'auth_required': gate})
        return httpx.Response(200, json={'ready': True, 'host_id': HOST_ID, 'gateway_url': origin})
    ingress.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    response = browser.get('/health')
    assert response.status_code == expected
    assert response.json()['ready'] is (expected == 200)
    assert 'host_id' in response.json() if expected == 200 else 'host_id' not in response.json()


def test_gateway_redirect_cannot_move_bearer_or_cookies_to_another_endpoint(facade):
    browser, ingress, _ = facade
    seen = []
    def upstream(request):
        seen.append(request)
        return httpx.Response(307, headers={'Location': 'https://unrelated.example.test'})
    ingress.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    response = browser.get('/api/auth/me', headers={'Authorization': 'Bearer ' + TOKEN})
    assert response.status_code == 502
    assert len(seen) == 1


@pytest.mark.parametrize('url', ['https://remote.example.test', 'http://192.168.1.2:1234', 'http://user@127.0.0.1:1234', 'http://127.0.0.1:1234/path'])
def test_canonical_discovery_cannot_become_an_arbitrary_proxy(facade, url):
    browser, ingress, seen = facade
    ingress.endpoint = lambda home: SimpleNamespace(api_origin=url)
    assert browser.get('/api/auth/me', headers={'Authorization': 'Bearer ' + TOKEN}).status_code == 503
    assert seen == []


@pytest.mark.parametrize('path,protocols', [('/api/ws?internal=x', PROTOCOLS), ('/api/ws?token=x', PROTOCOLS),
    ('/api/ws', []), ('/api/ws', ['hermes-gateway-v1']), ('/api/ws', PROTOCOLS + ['extra'])])
def test_websocket_refuses_query_and_ambiguous_credentials(facade, path, protocols):
    browser, _, seen = facade
    with pytest.raises(WebSocketDisconnect) as closed:
        with browser.websocket_connect(path, subprotocols=protocols):
            pass
    assert closed.value.code == 4403
    assert seen == []


def test_websocket_preserves_frames_and_remote_revocation_close(facade):
    browser, ingress, _ = facade
    captured = []
    class Upstream:
        subprotocol = 'hermes-gateway-v1'
        close_code = 4403
        def __init__(self):
            self.queue = asyncio.Queue()
        async def send(self, data):
            await self.queue.put(None if data == 'revoke' else data)
        def __aiter__(self):
            return self
        async def __anext__(self):
            value = await self.queue.get()
            if value is None:
                raise StopAsyncIteration
            return value
    @asynccontextmanager
    async def dial(url, **kwargs):
        captured.append((url, kwargs))
        yield Upstream()
    ingress.ws_connect = dial
    with browser.websocket_connect('/api/ws', subprotocols=PROTOCOLS) as phone:
        assert phone.accepted_subprotocol == 'hermes-gateway-v1'
        phone.send_text('hello')
        assert phone.receive_text() == 'hello'
        phone.send_bytes(b'\x00\x01')
        assert phone.receive_bytes() == b'\x00\x01'
        phone.send_text('revoke')
        with pytest.raises(WebSocketDisconnect) as closed:
            phone.receive_text()
        assert closed.value.code == 4403
    url, options = captured[0]
    assert url == 'ws://phone.example.test/api/ws'
    assert options['host'] == '127.0.0.1' and options['port'] == 12345
    assert options['origin'] == ORIGIN
    assert options['subprotocols'] == PROTOCOLS
    assert options['proxy'] is None
    assert 'additional_headers' not in options


def test_enabled_phone_config_engages_canonical_auth_despite_desktop_loopback_exemption(tmp_path, monkeypatch):
    from hermes_cli.config import atomic_config_write
    from hermes_cli.web_server_boundary import _dashboard_public_hosts, listener_auth_required
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_DESKTOP', '1')
    monkeypatch.setenv('HERMES_DASHBOARD_SESSION_TOKEN', 'synthetic-static-token')
    atomic_config_write(tmp_path / 'config.yaml', {'dashboard': {'device_links': {'enabled': True, 'gateway_url': ORIGIN}}})
    hosts = _dashboard_public_hosts()
    assert 'phone.example.test' in hosts
    assert listener_auth_required('127.0.0.1', hosts) is True
