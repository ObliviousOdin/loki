"""Real loopback facade → canonical gateway; synthetic existing IdP, no cloud exposure."""
import asyncio
import json
import socket

from cryptography.hazmat.primitives.asymmetric import ec
import httpx
import pytest
import pytest_asyncio
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tests.hermes_cli.test_dashboard_device_links_store import claim_request
from tests.waiting import async_wait_until

pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_http',)


@pytest_asyncio.fixture
async def public_facade(device_api):
    from hermes_cli.phone_ingress import create_app
    from hermes_constants import get_hermes_home
    app = create_app(get_hermes_home())
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False, proxy_headers=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await async_wait_until(lambda: server.started or task.done(), timeout=10)
        assert server.started
        async with httpx.AsyncClient(base_url='http://127.0.0.1:' + str(listener.getsockname()[1]),
                                     trust_env=False, follow_redirects=False) as client:
            yield client, device_api
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        listener.close()


async def _link(public, canonical, native, owner):
    from hermes_cli.dashboard_auth.device_links_crypto import fingerprint, sign, unb64
    created = await canonical.post('/api/device-links/pairings', json={}, headers={**native(), **owner})
    assert created.status_code == 200
    key = ec.generate_private_key(ec.SECP256R1())
    request = claim_request(created.json(), key)
    claim_result = await public.post('/auth/device/claims', json=request)
    assert claim_result.status_code == 200
    claim = claim_result.json()
    assert (await canonical.post('/api/device-links/claims/' + claim['claim_id'] + '/approve',
        json={'key_fingerprint': fingerprint(request['device_public_key']), 'comparison': claim['comparison']},
        headers=native())).status_code == 200
    challenge_result = await public.post('/auth/device/challenge', json={
        'host_id': claim['host_id'], 'device_id': claim['device_id']})
    assert challenge_result.status_code == 200
    challenge = challenge_result.json()
    token_result = await public.post('/auth/device/token', json={'device_id': claim['device_id'],
        'challenge_id': challenge['challenge_id'], 'signature': sign(key, unb64(challenge['payload']))})
    assert token_result.status_code == 200
    return token_result.json(), claim


async def _describe(ws):
    await ws.send(json.dumps({'jsonrpc': '2.0', 'id': 'describe', 'method': 'runtime.describe', 'params': {}}))
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if message.get('id') == 'describe':
            assert 'result' in message
            return message['result']


@pytest.mark.asyncio
async def test_public_facade_key_pairing_canonical_identity_ws_and_revocation(public_facade):
    public, (canonical, native, owner, service, _) = public_facade
    health = await public.get('/health')
    assert health.status_code == 200
    assert health.json()['host_id'] == service.store.host_id
    bearer, claim = await _link(public, canonical, native, owner)
    headers = {'Authorization': 'Bearer ' + bearer['access_token']}
    account = await public.get('/api/auth/me', headers=headers)
    assert account.status_code == 200
    assert account.json()['provider'] == 'stub' and account.json()['user_id'] == 'stub-user-1'
    ticket = (await public.post('/api/auth/ws-ticket', headers=headers)).json()['ticket']
    outstanding = (await public.post('/api/auth/ws-ticket', headers=headers)).json()['ticket']
    url = str(public.base_url).rstrip('/').replace('http:', 'ws:') + '/api/ws'
    async with connect(url, subprotocols=['hermes-gateway-v1', 'hermes-gateway-ticket.' + ticket]) as ws:
        await _describe(ws)
        assert (await canonical.delete('/api/device-links/devices/' + claim['device_id'], headers=native())).status_code == 200
        with pytest.raises(ConnectionClosed) as closed:
            while True:
                await asyncio.wait_for(ws.recv(), 10)
        assert closed.value.code == 4401
    assert (await public.get('/api/auth/me', headers=headers)).status_code == 401
    with pytest.raises(InvalidStatus):
        async with connect(url, subprotocols=['hermes-gateway-v1', 'hermes-gateway-ticket.' + outstanding]):
            pass


@pytest.mark.asyncio
async def test_public_facade_cannot_redeem_or_consume_private_mac_grants(public_facade):
    from hermes_cli import web_server as web
    from hermes_constants import get_hermes_home
    public, (canonical, native, owner, _, _) = public_facade
    private_headers = native()
    response = await public.get('/api/device-links', headers={**owner, **private_headers})
    assert response.status_code == 404
    # No forwarding: the original one-use same-user grant is still usable locally.
    assert (await canonical.get('/api/device-links', headers=private_headers)).status_code == 200
    runner = web.app.state.gateway_runner
    private_ticket = runner.session_ticket_store.mint(profile_id=str(get_hermes_home().resolve()),
        subject='uid:synthetic-owner', purpose='interactive')
    protocols = ['hermes-gateway-v1', 'hermes-gateway-ticket.' + private_ticket]
    public_url = str(public.base_url).rstrip('/').replace('http:', 'ws:') + '/api/ws'
    with pytest.raises(InvalidStatus):
        async with connect(public_url, subprotocols=protocols):
            pass
    # Its public attempt never reached the private bootstrap redeemer.
    local_url = str(canonical.base_url).rstrip('/').replace('http:', 'ws:') + '/api/ws'
    async with connect(local_url, subprotocols=protocols) as local:
        await _describe(local)
