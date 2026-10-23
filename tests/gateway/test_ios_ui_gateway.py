"""The native UI fixture uses the production auth and canonical listener boundaries."""
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import websockets

from tests.waiting import wait_until

pytestmark = pytest.mark.platforms('macos', 'linux')


@contextmanager
def running_gateway(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    ready = tmp_path / 'ready.json'
    log = tmp_path / 'gateway.log'
    env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'LANG', 'TZ') if key in os.environ}
    with log.open('w') as output:
        process = subprocess.Popen([sys.executable, str(repo / 'apps/ios/UITests/Support/test_gateway.py'),
                                    '--ready-file', str(ready)], cwd=repo, env=env,
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
        try:
            wait_until(lambda: ready.is_file() or process.poll() is not None, timeout=40,
                       what='isolated native test gateway readiness')
            assert process.poll() is None, log.read_text()
            yield json.loads(ready.read_text())
        finally:
            process.terminate()
            try:
                process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            assert process.returncode == 0, log.read_text()


async def login(client, identity='primary'):
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    providers = (await client.get('/api/auth/providers')).json()
    assert any(provider['name'] == 'loki-ui-test' for provider in providers['providers'])
    callback = 'com.loki.ios://auth/callback'
    params = {'provider': 'loki-ui-test', 'client_id': 'loki-ios', 'redirect_uri': callback,
              'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    start = await client.get('/auth/native/authorize', params=params)
    assert start.status_code == 302, start.text
    page = await client.get(start.headers['location'])
    assert 'Local UI test gateway' in page.text
    link = html.unescape(re.search(r'id="continue-test-login" href="([^"]+)"', page.text)[1])
    upstream = await client.get(link + '&identity=' + identity)
    assert upstream.status_code == 302, upstream.text
    returned = await client.get(upstream.headers['location'])
    assert returned.status_code == 302, returned.text
    url = urlsplit(returned.headers['location'])
    assert url._replace(query='').geturl() == callback
    values = parse_qs(url.query)
    assert values['state'] == [state]
    body = {'code': values['code'][0], 'code_verifier': verifier, 'client_id': 'loki-ios', 'redirect_uri': callback}
    token = await client.post('/auth/native/token', json=body)
    assert token.status_code == 200, token.text
    assert (await client.post('/auth/native/token', json=body)).status_code == 400
    client.cookies.clear()
    client.headers['Authorization'] = 'Bearer ' + token.json()['access_token']
    me = await client.get('/api/auth/me')
    assert me.status_code == 200 and me.json()['user_id'] == 'loki-ui-test-' + identity
    return token.json()


async def socket(client, origin):
    ticket = await client.post('/api/auth/ws-ticket')
    assert ticket.status_code == 200, ticket.text
    protocols = ['hermes-gateway-v1', 'hermes-gateway-ticket.' + ticket.json()['ticket']]
    ws = await websockets.connect(origin.replace('http:', 'ws:') + '/api/ws', subprotocols=protocols)
    assert ws.subprotocol == 'hermes-gateway-v1'
    return ws, protocols


class NativePeer:
    def __init__(self, ws):
        self.ws, self.frames, self.counter = ws, [], 0
        self.delivered = set()

    async def rpc(self, method, **params):
        self.counter += 1
        rid = self.counter
        await self.ws.send(json.dumps({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}))
        async with asyncio.timeout(45):
            while True:
                frame = json.loads(await self.ws.recv())
                self.frames.append(frame)
                if frame.get('id') == rid:
                    return frame

    async def event(self, kind, *, session_id):
        async with asyncio.timeout(45):
            while True:
                for index, frame in enumerate(self.frames):
                    event = frame.get('params', {})
                    if (event.get('session_id') == session_id and event.get('type') == 'message.complete'
                            and event.get('payload', {}).get('outcome') == 'failed'):
                        raise AssertionError(f'Test turn failed before {kind}: {event}')
                    if (index not in self.delivered and event.get('type') == kind
                            and event.get('session_id') == session_id):
                        self.delivered.add(index)
                        return event
                frame = json.loads(await self.ws.recv())
                self.frames.append(frame)

    async def create(self):
        result = await self.rpc('session.create', profile='default', title='Bot Chat', hidden=True,
                                follow_profile_config=True, source='ios', request_id='native-ui-test')
        assert 'result' in result, result
        assert result['result']['info']['source'] == 'ios'
        return result['result']['session_id']

    async def submit(self, sid, text):
        result = await self.rpc('prompt.submit', session_id=sid, text=text,
                                input_id=secrets.token_hex(16), submission_id=secrets.token_hex(16))
        assert result.get('result', {}).get('status') == 'queued', result
        return result['result']


@pytest.mark.asyncio
async def test_ui_gateway_native_pkce_ticket_chat_replay_and_identity_boundary(tmp_path):
    with running_gateway(tmp_path) as ready:
        assert ready['test_only'] and urlsplit(ready['origin']).hostname == '127.0.0.1'
        async with httpx.AsyncClient(base_url=ready['origin'], timeout=20) as client:
            assert (await client.get('/api/auth/me')).status_code == 401
            token = await login(client)
            ws, protocols = await socket(client, ready['origin'])
            async with ws:
                with pytest.raises((websockets.exceptions.InvalidStatus, websockets.exceptions.ConnectionClosed)):
                    async with websockets.connect(ready['origin'].replace('http:', 'ws:') + '/api/ws', subprotocols=protocols):
                        raise AssertionError('one-use ticket was replayed')
                native = NativePeer(ws)
                roster = await native.rpc('profiles.list', include_sessions=True)
                assert roster['result']['profiles'][0]['name'] == 'default', roster
                sid = await native.create()
                await native.submit(sid, 'Hello Loki')
                completed = await native.event('message.complete', session_id=sid)
                assert completed['payload']['outcome'] == 'completed'
                snapshot = await native.rpc('session.resume', session_id=sid)
                assert 'local test gateway' in json.dumps(snapshot['result']['messages'])
                assert any(frame.get('params', {}).get('type') == 'message.delta' for frame in native.frames)
                await native.submit(sid, 'Show code')
                await native.event('message.complete', session_id=sid)
                code_snapshot = (await native.rpc('session.resume', session_id=sid))['result']
                code = next(message['content'] for message in code_snapshot['messages']
                            if message.get('role') == 'assistant' and 'struct QuietMoment' in str(message.get('content')))
                assert '\n```swift\nstruct QuietMoment {\n    let message' in code
                assert '\n\n    func begin() {\n        print(message)\n' in code
                replay = await native.rpc('session.events.since', session_id=sid,
                                          replay_epoch='deliberately-wrong-epoch', last_sequence=0)
                assert replay['result']['snapshot_required'] is True
            refreshed = await client.post('/auth/native/refresh', json={
                'refresh_token': token['refresh_token'], 'provider': token['provider']})
            assert refreshed.status_code == 200
        async with httpx.AsyncClient(base_url=ready['origin'], timeout=20) as peer_client:
            await login(peer_client, 'peer')
            peer_ws, _ = await socket(peer_client, ready['origin'])
            async with peer_ws:
                other = NativePeer(peer_ws)
                distinct = await other.rpc('session.create', profile='default', source='ios',
                    request_id='native-ui-test', follow_profile_config=True, hidden=True)
                assert distinct['result']['session_id'] != sid, distinct
                denied = await other.rpc('session.resume', profile='unserved-profile', session_id=sid)
                assert denied['error']['data']['reason'] == 'profile_mismatch', denied


@pytest.mark.asyncio
async def test_ui_gateway_real_pending_controls_and_connector_card(tmp_path):
    with running_gateway(tmp_path) as ready:
        async with httpx.AsyncClient(base_url=ready['origin'], timeout=20) as client:
            await login(client)
            ws, _ = await socket(client, ready['origin'])
            async with ws:
                native = NativePeer(ws)
                sid = await native.create()
                await native.submit(sid, 'Ask a question')
                await native.event('clarify.request', session_id=sid)
            resumed_ws, _ = await socket(client, ready['origin'])
            async with resumed_ws:
                native = NativePeer(resumed_ws)
                snapshot = (await native.rpc('session.resume', session_id=sid))['result']
                prompt = snapshot['prompts'][0]
                answered = await native.rpc('clarify.respond', session_id=sid, prompt_id=prompt['prompt_id'],
                    execution_generation=prompt['execution_generation'], answer='A walk')
                assert answered['result']['status'] == 'resolved', answered
                await native.event('message.complete', session_id=sid)
                await native.submit(sid, 'Show an approval')
                await native.event('approval.request', session_id=sid)
                snapshot = (await native.rpc('session.resume', session_id=sid))['result']
                prompt = snapshot['prompts'][0]
                denied = await native.rpc('approval.respond', session_id=sid, prompt_id=prompt['prompt_id'],
                    execution_generation=prompt['execution_generation'], choice='deny')
                assert denied['result']['status'] == 'resolved', denied
                await native.event('message.complete', session_id=sid)
                await native.submit(sid, 'Connect HubSpot')
                request = await native.event('connection.request', session_id=sid)
                snapshot = (await native.rpc('session.resume', session_id=sid))['result']
                assert snapshot['pending_connection']['op_id'] == request['payload']['op_id']
                skipped = await native.rpc('connection.respond', owner={'type': 'session', 'session_id': sid},
                    op_id=request['payload']['op_id'], result={'targets': [{'name': 'hubspot', 'status': 'skipped'}]})
                assert skipped['result'] == {'status': 'ok', 'settled': True}
                await native.event('message.complete', session_id=sid)
