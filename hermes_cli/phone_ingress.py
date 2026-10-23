"""Loopback-only phone facade for a named outbound TLS tunnel.

The canonical gateway verifies every bearer and one-use dashboard WS ticket.
This facade never mints private grants and always supplies an Origin, preventing
the upstream's same-user native WS bootstrap fastpath from admitting a phone.
Run with the PM-selected interpreter: ``python -m hermes_cli.phone_ingress``.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import ipaddress
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qsl, urlsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocketDisconnect, WebSocketState
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

_BOOTSTRAP = frozenset('/auth/device/' + name for name in ('claims', 'poll', 'challenge', 'token'))
_REST = {
    '/api/health': {'GET'}, '/api/auth/me': {'GET'}, '/api/auth/ws-ticket': {'POST'},
    '/api/cron/capabilities': {'GET'}, '/api/cron/jobs': {'GET', 'POST'},
    '/api/audio/stt-lease': {'POST'}, '/api/audio/transcribe': {'POST'}, '/api/audio/speak': {'POST'},
    '/api/skills': {'GET'}, '/api/skills/toggle': {'PUT'},
    '/api/learning/graph': {'GET'}, '/api/learning/node': {'GET', 'PUT'},
    **{'/api/fs/' + path: {'GET'} for path in ('default-cwd', 'list', 'read-text', 'read-data-url')},
}
_JOB = re.compile(r'^/api/cron/jobs/[A-Za-z0-9_-]{1,128}(?:/(runs|trigger|pause|resume))?$')
_CALLBACK = re.compile(r'^/api/mcp/oauth/callback/[A-Za-z0-9_.-]{1,120}$')
_TICKET = re.compile(r'^hermes-gateway-ticket\.[A-Za-z0-9_-]{16,512}$')
_BODY_LIMIT = 32 * 1024 * 1024
_RESPONSE_LIMIT = 40 * 1024 * 1024
_RATE_LIMITS = {'bootstrap': 120, 'health': 20, 'socket': 60}


def _json(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def allowed_http(path: str, method: str) -> bool:
    if path in _BOOTSTRAP:
        return method == 'POST'
    if method in _REST.get(path, set()):
        return True
    match = _JOB.fullmatch(path)
    if match:
        action = match.group(1)
        return method in ({'GET'} if action == 'runs' else {'POST'} if action else {'GET', 'PUT', 'DELETE'})
    return method == 'GET' and bool(_CALLBACK.fullmatch(path))


def safe_query(raw: bytes) -> bool:
    """Phone credentials belong in headers/subprotocols, never URLs."""
    if len(raw) > 4096:
        return False
    try:
        pairs = parse_qsl(raw.decode('ascii'), max_num_fields=32, errors='strict')
    except (ValueError, UnicodeError):
        return False
    return all(key.lower() not in {'token', 'ticket', 'internal', 'access_token', 'refresh_token'} for key, _ in pairs)


def gateway_endpoint(home: Path):
    """Discover only: no start, update, private grant or implicit profile switch."""
    from hermes_cli.gateway_runtime import attachable, discover_gateway_endpoint
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        observed = discover_gateway_endpoint(home)
        return observed.endpoint if attachable(observed) else None
    finally:
        reset_hermes_home_override(token)


class PhoneIngress:
    def __init__(self, home, public_origin, *, endpoint=gateway_endpoint, client=None, ws_connect=connect,
                 clock=time.monotonic):
        self.home, self.origin = Path(home).resolve(), public_origin
        self.endpoint, self.client, self.ws_connect = endpoint, client, ws_connect
        self.host = urlsplit(public_origin).netloc
        self.clock = clock
        self._rate_window = int(clock()) // 60
        self._rates = {}
        self._rate_salt = secrets.token_bytes(32)

    def _allow_public(self, connection, kind):
        # Cloudflare overwrites this address on the named tunnel. It is ONLY a
        # fairness bucket, never authentication, identity or a private-peer claim.
        values = connection.headers.getlist('cf-connecting-ip')
        address = connection.client.host if connection.client else 'unknown'
        if len(values) == 1:
            try:
                address = str(ipaddress.ip_address(values[0]))
            except ValueError:
                address = connection.client.host if connection.client else 'unknown'
        window = int(self.clock()) // 60
        if window != self._rate_window:
            self._rates.clear()
            self._rate_window = window
        key = hashlib.sha256(self._rate_salt + address.encode()).digest()
        if key not in self._rates:
            if len(self._rates) >= 1024:
                return False
            self._rates[key] = {}
        row = self._rates[key]
        if row.get(kind, 0) >= _RATE_LIMITS[kind]:
            return False
        row[kind] = row.get(kind, 0) + 1
        return True

    async def _target(self):
        target = await asyncio.to_thread(self.endpoint, self.home)
        if target is None:
            return None
        parsed = urlsplit(target.api_origin)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1'}
                or not parsed.port or parsed.path or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None):
            return None
        return target

    def _headers(self, request):
        # An allowlist also strips cookies, native/control tickets, proxy-supplied
        # identity, static-session headers and any Connection-nominated headers.
        headers = {'Host': self.host, 'Origin': self.origin, 'X-Forwarded-Proto': 'https'}
        for name in ('authorization', 'content-type', 'accept'):
            values = request.headers.getlist(name)
            if len(values) == 1:
                headers[name] = values[0]
        return headers

    async def _authorize_mutation(self, target, request):
        """Reject an invented bearer before buffering an Internet upload."""
        try:
            response = await self.client.get(target.api_origin + '/api/auth/me',
                headers=self._headers(request), timeout=5)
            if response.status_code in (401, 403):
                return _json({'error': 'unauthenticated'}, 401)
            if response.status_code != 200 or len(response.content) > 65536:
                return _json({'error': 'gateway_unavailable'}, 503)
            account = response.json()
            if (not isinstance(account, dict) or account.get('provider') == 'loopback'
                    or not all(isinstance(account.get(key), str) and account[key] for key in ('user_id', 'provider'))):
                return _json({'error': 'gateway_unavailable'}, 503)
        except (httpx.HTTPError, ValueError):
            return _json({'error': 'gateway_unavailable'}, 503)
        return None

    async def health(self, request):
        if not self._allow_public(request, 'health'):
            return _json({'error': 'try_later'}, 429)
        target = await self._target()
        if target is None:
            return _json({'service': 'loki-phone-ingress', 'version': 1, 'ready': False}, 503)
        try:
            headers = {'Host': self.host, 'Origin': self.origin}
            gate = await self.client.get(target.api_origin + '/api/health', headers=headers, timeout=3)
            status = await self.client.get(target.api_origin + '/auth/device/status', headers=headers, timeout=3)
            info = status.json()
            ready = (gate.status_code == 200 and gate.json().get('auth_required') is True
                     and status.status_code == 200 and info.get('ready') is True
                     and info.get('gateway_url') == self.origin
                     and bool(re.fullmatch('[a-f0-9]{64}', info.get('host_id', ''))))
        except (httpx.HTTPError, ValueError):
            ready, info = False, {}
        result = {'service': 'loki-phone-ingress', 'version': 1, 'ready': ready}
        if ready:
            result['host_id'] = info['host_id']
        return _json(result, 200 if ready else 503)

    async def http(self, request: Request):
        path = request.url.path
        if not allowed_http(path, request.method) or not safe_query(request.scope['query_string']):
            return _json({'error': 'not_found'}, 404)
        if path in _BOOTSTRAP and not self._allow_public(request, 'bootstrap'):
            return _json({'error': 'try_later'}, 429)
        if path.startswith('/api/') and not _CALLBACK.fullmatch(path):
            bearers = request.headers.getlist('authorization')
            if len(bearers) != 1 or not re.fullmatch(r'Bearer [A-Za-z0-9._~-]{16,4096}', bearers[0]):
                return _json({'error': 'unauthenticated'}, 401)
        target = await self._target()
        if target is None:
            return _json({'error': 'gateway_unavailable'}, 503)
        if request.method != 'GET' and path not in _BOOTSTRAP:
            refused = await self._authorize_mutation(target, request)
            if refused is not None:
                return refused
        limit = 0 if request.method == 'GET' else 4096 if path in _BOOTSTRAP else _BODY_LIMIT
        body = bytearray()
        try:
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    return _json({'error': 'request_too_large'}, 413)
                body.extend(chunk)
        except ClientDisconnect:
            return Response(status_code=499)
        query = request.scope['query_string'].decode('ascii')
        url = target.api_origin + path + ('?' + query if query else '')
        try:
            read_timeout = 190 if path == '/api/audio/stt-lease' else 130 if path in {
                '/api/audio/transcribe', '/api/audio/speak'} else 60
            upstream = await self.client.send(self.client.build_request(
                request.method, url, headers=self._headers(request), content=bytes(body),
                timeout=httpx.Timeout(read_timeout, connect=3)), stream=True)
        except httpx.HTTPError:
            return _json({'error': 'gateway_unavailable'}, 503)
        if 300 <= upstream.status_code < 400:
            await upstream.aclose()
            return _json({'error': 'unexpected_gateway_redirect'}, 502)
        async def content():
            total = 0
            try:
                async for chunk in upstream.aiter_bytes():
                    total += len(chunk)
                    if total > _RESPONSE_LIMIT:
                        raise RuntimeError('gateway_response_too_large')
                    yield chunk
            finally:
                await upstream.aclose()
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        for name in ('content-type', 'retry-after'):
            if name in upstream.headers:
                headers[name] = upstream.headers[name]
        return StreamingResponse(content(), status_code=upstream.status_code, headers=headers)

    async def websocket(self, ws):
        if not self._allow_public(ws, 'socket'):
            await ws.close(code=1013)
            return
        protocols = ws.scope.get('subprotocols', [])
        if (ws.scope['query_string'] or len(protocols) != 2
                or protocols.count('hermes-gateway-v1') != 1
                or sum(bool(_TICKET.fullmatch(value)) for value in protocols) != 1):
            await ws.close(code=4403)
            return
        target = await self._target()
        if target is None:
            await ws.close(code=1013)
            return
        address = urlsplit(target.api_origin)
        # URI carries the public Host; host/port fix the actual TCP destination.
        # Supplying Origin ensures the canonical native-control fastpath refuses.
        try:
            async with self.ws_connect('ws://' + self.host + '/api/ws', host=address.hostname,
                    port=address.port, origin=self.origin, subprotocols=protocols, proxy=None,
                    open_timeout=10, close_timeout=3, max_size=16 * 1024 * 1024,
                    ping_interval=20, ping_timeout=20) as upstream:
                if upstream.subprotocol != 'hermes-gateway-v1':
                    await ws.close(code=4403)
                    return
                await ws.accept(subprotocol='hermes-gateway-v1')
                await _bridge(ws, upstream)
        except (OSError, TimeoutError, InvalidHandshake):
            await ws.close(code=4403)


async def _bridge(ws, upstream):
    async def to_gateway():
        try:
            while True:
                message = await ws.receive()
                if message['type'] == 'websocket.disconnect':
                    return 1000
                await upstream.send(message.get('text') if message.get('text') is not None else message['bytes'])
        except (WebSocketDisconnect, ConnectionClosed):
            return 1000

    async def to_phone():
        try:
            async for message in upstream:
                if isinstance(message, str):
                    await ws.send_text(message)
                else:
                    await ws.send_bytes(message)
            return upstream.close_code or 1000
        except ConnectionClosed as exc:
            return exc.code or 1000
        except WebSocketDisconnect:
            return 1000

    tasks = {asyncio.create_task(to_gateway()), asyncio.create_task(to_phone())}
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        code = next(iter(done)).result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if ws.client_state != WebSocketState.DISCONNECTED:
        await ws.close(code=code if code not in (1005, 1006, 1015) else 1011)


def create_app(home=None):
    from hermes_cli.config import load_config
    from hermes_cli.dashboard_auth.device_links_config import https_origin
    from hermes_constants import get_hermes_home
    home = Path(home or get_hermes_home()).resolve()
    # A service is pinned to the launch home; no request can choose another home.
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        config = (load_config().get('dashboard') or {}).get('device_links') or {}
    finally:
        reset_hermes_home_override(token)
    if config.get('enabled') is not True:
        raise ValueError('phone_links_disabled')
    origin = https_origin(config.get('gateway_url'))
    ingress = PhoneIngress(home, origin)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=3), follow_redirects=False,
                                     trust_env=False) as client:
            ingress.client = client
            yield
            ingress.client = None

    app = Starlette(routes=[Route('/health', ingress.health), WebSocketRoute('/api/ws', ingress.websocket),
                           Route('/{path:path}', ingress.http, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])],
                    lifespan=lifespan)
    app.state.phone_ingress = ingress
    app.state.phone_ingress_port = config.get('ingress_port', 9450)
    return app


def main():
    import uvicorn
    app = create_app()
    port = app.state.phone_ingress_port
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('invalid_phone_ingress_port')
    uvicorn.run(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False,
                log_level='warning', ws_max_size=16 * 1024 * 1024, timeout_graceful_shutdown=5)


if __name__ == '__main__':
    main()
