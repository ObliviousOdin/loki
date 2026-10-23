"""Normal canonical HTTP/WS authentication, real private native grants, synthetic IdP only."""
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
import httpx
import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tests.hermes_cli.test_dashboard_device_links_store import claim_request


@pytest_asyncio.fixture
async def device_api(monkeypatch):
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.run_runtime import (
        initialize_gateway_runtime, publish_gateway_runtime_ready, start_gateway_runtime_api)
    from gateway.runtime_ownership import process_ownership
    from hermes_cli import web_server as web
    from hermes_cli.config import atomic_config_write
    from hermes_cli.dashboard_auth import clear_providers, native_flow, register_provider
    from hermes_constants import get_hermes_home
    from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider

    home = get_hermes_home().resolve()
    atomic_config_write(home / 'config.yaml', {'dashboard': {
        'public_url': 'https://mac.example.test', 'device_links': {
            'enabled': True, 'gateway_url': 'https://mac.example.test',
            'rendezvous_url': 'https://links.example.test', 'host_name': 'Test Mac'}},
        'auxiliary': {'title_generation': {'enabled': False}}})
    monkeypatch.setenv('LOKI_PHONE_LINK_REGISTRATION_TOKEN', 'synthetic-' + 'x' * 48)
    clear_providers()
    native_flow._reset_for_tests()
    register_provider(StubAuthProvider())
    from hermes_cli.dashboard_auth import device_links_routes
    monkeypatch.setattr(device_links_routes, '_rates', {})
    process_ownership.reserve([home])
    runner = GatewayRunner(GatewayConfig())
    try:
        await initialize_gateway_runtime(runner)
        from gateway.run_bootstrap import _start_gateway_start_control_socket
        assert await _start_gateway_start_control_socket(runner)
        await start_gateway_runtime_api(runner)
        assert await runner.start()
        publish_gateway_runtime_ready(runner)
        origin = runner.session_api.api_origin
        service = web.app.state.device_links_service
        assert service is not None
        registrations = []
        monkeypatch.setattr(service, 'registration', registrations.append)
        monkeypatch.setattr(service, 'cancellation', lambda pairing_id: None)
        monkeypatch.setattr(service, 'verify_transport', lambda: setattr(service, 'transport_verified_at', int(time.time())))
        def native_headers():
            ticket = runner.session_ticket_store.mint(
                profile_id=str(home), subject='uid:synthetic-owner', purpose='native-http')
            return {'X-Hermes-Gateway-Ticket': ticket}
        async with httpx.AsyncClient(base_url=origin, trust_env=False, follow_redirects=False) as client:
            # The existing native broker proves the owner account; no identity fields are supplied.
            verifier = 'synthetic-verifier-' + 'v' * 48
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            start = await client.get('/auth/native/authorize', params={
                'provider': 'stub', 'code_challenge': challenge, 'code_challenge_method': 'S256',
                'redirect_uri': 'http://127.0.0.1:53123/callback', 'state': 's' * 48})
            assert start.status_code == 302, start.text
            callback = urlsplit(start.headers['location'])
            result = await client.get(callback.path + '?' + callback.query)
            assert result.status_code == 302, result.text
            code = parse_qs(urlsplit(result.headers['location']).query)['code'][0]
            result = await client.post('/auth/native/token', json={
                'code': code, 'code_verifier': verifier, 'redirect_uri': 'http://127.0.0.1:53123/callback'})
            assert result.status_code == 200, result.text
            owner = {'Authorization': 'Bearer ' + result.json()['access_token']}
            yield client, native_headers, owner, service, registrations
    finally:
        await runner.stop()
        control = getattr(runner, 'session_control_server', None)
        if control is not None:
            await control.stop()
        process_ownership.close()
        clear_providers()
        native_flow._reset_for_tests()


async def pair(client, native, owner):
    from hermes_cli.dashboard_auth.device_links_crypto import fingerprint, sign, unb64
    created = await client.post('/api/device-links/pairings', json={}, headers={**native(), **owner})
    assert created.status_code == 200, created.text
    key = ec.generate_private_key(ec.SECP256R1())
    body = claim_request(created.json(), key)
    response = await client.post('/auth/device/claims', json=body)
    assert response.status_code == 200, response.text
    claim = response.json()
    approval = {'key_fingerprint': fingerprint(body['device_public_key']), 'comparison': claim['comparison']}
    response = await client.post('/api/device-links/claims/' + claim['claim_id'] + '/approve',
                                 json=approval, headers=native())
    assert response.status_code == 200, response.text
    response = await client.post('/auth/device/poll', json={
        'claim_id': claim['claim_id'], 'claim_token': claim['claim_token']})
    assert response.json()['status'] == 'approved'
    response = await client.post('/auth/device/challenge', json={
        'device_id': claim['device_id'], 'host_id': claim['host_id']})
    assert response.status_code == 200, response.text
    challenge = response.json()
    response = await client.post('/auth/device/token', json={'device_id': claim['device_id'],
        'challenge_id': challenge['challenge_id'], 'signature': sign(key, unb64(challenge['payload']))})
    assert response.status_code == 200, response.text
    return response.json(), claim


@pytest.mark.asyncio
async def test_os_management_verified_existing_owner_and_hidden_verifier(device_api):
    client, native, owner, service, registrations = device_api
    assert (await client.get('/api/device-links', headers=owner)).status_code == 403
    assert (await client.get('/api/device-links', headers={**owner, 'X-Hermes-Gateway-Ticket': 'bad'})).status_code == 401
    assert (await client.get('/api/device-links', headers={**native(), 'Origin': ''})).status_code == 401
    without_owner = await client.get('/api/device-links', headers=native())
    assert without_owner.status_code == 200, without_owner.text
    assert without_owner.json()['owner'] is None and without_owner.json()['owner_sign_in_required'] is True
    verified = await client.get('/api/device-links', headers={**native(), **owner})
    assert verified.status_code == 200, verified.text
    assert verified.json()['owner'] == {'provider': 'stub', 'user_id': 'stub-user-1', 'issuer': ''}
    assert verified.json()['owner_sign_in_required'] is False
    assert (await client.post('/api/device-links/pairings', json={}, headers=native())).status_code == 409
    providers = (await client.get('/api/auth/providers')).json()['providers']
    assert [p['name'] for p in providers] == ['stub']
    assert (await client.get('/auth/login', params={'provider': 'loki-device'})).status_code == 404
    bearer, claim = await pair(client, native, owner)
    headers = {'Authorization': 'Bearer ' + bearer['access_token']}
    identity = await client.get('/api/auth/me', headers=headers)
    assert identity.status_code == 200
    assert identity.json()['provider'] == 'stub' and identity.json()['user_id'] == 'stub-user-1'
    assert (await client.get('/api/device-links', headers=headers)).status_code == 403
    assert (await client.get('/api/device-links', headers={**native(), **headers})).json()['owner_sign_in_required'] is True
    assert len(registrations) == 1 and registrations[0]['host_id'] == service.store.host_id
    status = await client.get('/auth/device/status')
    assert status.json() == {'ready': True, 'host_id': service.store.host_id, 'gateway_url': service.store.gateway_url}
    assert 'no-store' in status.headers['cache-control']
    assert bearer['device_id'] == claim['device_id'] and 'refresh_token' not in bearer


@pytest.mark.asyncio
async def test_revoke_closes_live_canonical_socket_rejects_ticket_and_preserves_other_device(device_api):
    client, native, owner, _, _ = device_api
    bearer, claim = await pair(client, native, owner)
    other, _ = await pair(client, native, owner)
    headers = {'Authorization': 'Bearer ' + bearer['access_token']}
    ticket = (await client.post('/api/auth/ws-ticket', headers=headers)).json()['ticket']
    outstanding = (await client.post('/api/auth/ws-ticket', headers=headers)).json()['ticket']
    url = str(client.base_url).rstrip('/').replace('http:', 'ws:') + '/api/ws'
    async with connect(url, subprotocols=['hermes-gateway-v1', 'hermes-gateway-ticket.' + ticket]) as ws:
        await ws.send(json.dumps({'jsonrpc': '2.0', 'id': 'describe', 'method': 'runtime.describe', 'params': {}}))
        while True:
            message = json.loads(await ws.recv())
            if message.get('id') == 'describe':
                assert 'result' in message, message
                break
        revoked = await client.delete('/api/device-links/devices/' + claim['device_id'], headers=native())
        assert revoked.status_code == 200, revoked.text
        with pytest.raises(ConnectionClosed) as closed:
            while True:
                await ws.recv()
        assert closed.value.code == 4401
    assert (await client.get('/api/auth/me', headers=headers)).status_code == 401
    assert (await client.post('/api/auth/ws-ticket', headers=headers)).status_code == 401
    assert (await client.post('/auth/device/challenge', json={
        'device_id': claim['device_id'], 'host_id': claim['host_id']})).status_code == 400
    with pytest.raises(InvalidStatus):
        async with connect(url, subprotocols=['hermes-gateway-v1', 'hermes-gateway-ticket.' + outstanding]):
            pass
    assert (await client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + other['access_token']})).status_code == 200


@pytest.mark.asyncio
async def test_two_proxy_polling_phones_share_bounded_aggregate_without_direct_peer_starvation(device_api):
    from hermes_cli.dashboard_auth.device_links_crypto import fingerprint, sign, unb64
    client, native, owner, service, _ = device_api
    proxy = {'Origin': service.store.gateway_url}
    pending = []
    for _ in range(2):
        pairing = await client.post('/api/device-links/pairings', json={}, headers={**native(), **owner})
        key = ec.generate_private_key(ec.SECP256R1())
        body = claim_request(pairing.json(), key)
        claim = await client.post('/auth/device/claims', json=body, headers=proxy)
        assert claim.status_code == 200, claim.text
        pending.append((key, body, claim.json()))
    for _ in range(31):
        for _, _, claim in pending:
            response = await client.post('/auth/device/poll', headers=proxy, json={
                'claim_id': claim['claim_id'], 'claim_token': claim['claim_token']})
            assert response.status_code == 200 and response.json()['status'] == 'pending'
    for key, body, claim in pending:
        approved = await client.post('/api/device-links/claims/' + claim['claim_id'] + '/approve',
            json={'key_fingerprint': fingerprint(body['device_public_key']), 'comparison': claim['comparison']},
            headers=native())
        assert approved.status_code == 200, approved.text
        response = await client.post('/auth/device/challenge', headers=proxy, json={
            'device_id': claim['device_id'], 'host_id': claim['host_id']})
        assert response.status_code == 200, response.text
        challenge = response.json()
        response = await client.post('/auth/device/token', headers=proxy, json={
            'device_id': claim['device_id'], 'challenge_id': challenge['challenge_id'],
            'signature': sign(key, unb64(challenge['payload']))})
        assert response.status_code == 200, response.text
    # A same-socket request without the configured proxy Origin retains the independent 60 budget.
    invalid = {'device_id': 'device_unknownsynthetic', 'host_id': service.store.host_id}
    for _ in range(60):
        assert (await client.post('/auth/device/challenge', json=invalid)).status_code == 400
    assert (await client.post('/auth/device/challenge', json=invalid)).status_code == 429
