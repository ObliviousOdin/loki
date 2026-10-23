"""A real mobile turn's catalog approval, with only the upstream installer replaced."""
import json

import httpx
import pytest

from tests.gateway.test_ios_ui_gateway import NativePeer, login, running_gateway, socket

pytestmark = pytest.mark.platforms('macos', 'linux')


@pytest.mark.asyncio
async def test_native_catalog_card_approval_and_backend_outcome_keep_credentials_private(tmp_path):
    with running_gateway(tmp_path) as ready:
        async with httpx.AsyncClient(base_url=ready['origin'], timeout=20) as client:
            await login(client)
            ws, _ = await socket(client, ready['origin'])
            async with ws:
                native = NativePeer(ws)
                sid = await native.create()
                info = await native.rpc('session.info', session_id=sid)
                assert 'catalog' in info.get('result', {}).get('enabled_toolsets', []), info
                await native.submit(sid, 'Install test support')
                try:
                    request = await native.event('connection.request', session_id=sid)
                except TimeoutError:
                    snapshot = await native.rpc('session.resume', session_id=sid)
                    raise AssertionError(snapshot.get('result', {}).get('messages')) from None
                op = request['payload']
                target = op['targets'][0]
                assert target['kind'] == 'plugin' and target['action'] == 'install', target
                assert target['sha'] == 'a' * 40
                assert target['repo'] == 'https://example.invalid/loki-ui-test-support'
                assert target['required_env'][0]['secret'] is True
                secret = 'synthetic-test-value-do-not-send-to-model'
                approved = await native.rpc('connection.respond', profile='default', owner={'type': 'session', 'session_id': sid},
                    op_id=op['op_id'], result={'targets': [{'name': target['name'], 'status': 'approved', 'env': {
                        'target_profile': 'default', 'agent_half': '1', 'desktop_half': '0', 'enable': '1', 'force': '0',
                        'ref': target['sha'], 'LOKI_UI_TEST_VALUE': secret}}]})
                assert approved.get('result', {}).get('status') == 'ok', approved
                completed = await native.event('message.complete', session_id=sid)
                assert completed['payload']['outcome'] == 'completed'
                snapshot = (await native.rpc('session.resume', profile='default', session_id=sid))['result']
                serialized = json.dumps(snapshot)
                assert secret not in serialized
                assert any('connected' in json.dumps(message) for message in snapshot['messages'] if message['role'] == 'tool')
