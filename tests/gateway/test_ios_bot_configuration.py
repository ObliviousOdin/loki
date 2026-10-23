"""Native bot settings exercise the real authenticated profile adapter boundary."""
import asyncio
import secrets
import httpx
import pytest

from tests.gateway.test_ios_ui_gateway import NativePeer, login, running_gateway, socket
from tests.waiting import async_wait_until

pytestmark = pytest.mark.platforms('macos', 'linux')


async def wait_for_bot(native, name):
    pending = asyncio.create_task(native.rpc('profiles.list', profile='default', include_sessions=False))

    def served():
        nonlocal pending
        if not pending.done():
            return False
        rows = pending.result()
        if any(row['name'] == name for row in rows.get('result', {}).get('profiles', [])):
            return True
        pending = asyncio.create_task(native.rpc('profiles.list', profile='default', include_sessions=False))
        return False

    try:
        await async_wait_until(served, timeout=30, what='new native bot becomes served')
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_native_bot_creation_configuration_and_model_inventory(tmp_path):
    with running_gateway(tmp_path) as ready:
        async with httpx.AsyncClient(base_url=ready['origin'], timeout=20) as client:
            await login(client)
            ws, _ = await socket(client, ready['origin'])
            async with ws:
                native = NativePeer(ws)
                created = await native.rpc('profiles.create', profile='default', name='native-buddy',
                    description='A synthetic UI test bot', no_alias=True, share_auth=True, mirror_credentials=True)
                assert created.get('result', {}).get('name') == 'native-buddy', created
                await wait_for_bot(native, 'native-buddy')
                roster = await native.rpc('profiles.list', profile='native-buddy', include_sessions=True)
                assert 'result' in roster, roster
                assert any(row['name'] == 'native-buddy' for row in roster['result']['profiles']), roster
                bot = next(row for row in roster.get('result', {}).get('profiles', []) if row['name'] == 'native-buddy')
                revision = bot['ui_meta_revisions'].get('hermes-bots', 0)
                saved = await native.rpc('profiles.configure', profile='native-buddy', name='native-buddy',
                    description='Edited from the native consumer', soul='Be calm. This is a test fixture.',
                    ui_meta={'hermes-bots': {'title': 'Native Buddy', 'color': 'sage'}},
                    ui_meta_expected_revisions={'hermes-bots': revision})
                assert saved.get('result', {}).get('applied') == {
                    'ui_meta': True, 'ui_meta_revisions': {'hermes-bots': revision + 1},
                    'description': True, 'soul': True}, saved
                stale = await native.rpc('profiles.configure', profile='native-buddy', name='native-buddy',
                    ui_meta={'hermes-bots': {'title': 'Stale overwrite'}},
                    ui_meta_expected_revisions={'hermes-bots': revision})
                assert stale['result']['applied']['ui_meta'] is False, stale
                assert 'hermes-bots' in stale['result']['applied']['ui_meta_conflicts'], stale
                described = await native.rpc('profiles.describe', profile='native-buddy', name='native-buddy')
                assert described['result']['description'] == 'Edited from the native consumer', described
                assert described['result']['soul'] == 'Be calm. This is a test fixture.'
                root = await native.rpc('profiles.describe', profile='default', name='default')
                assert root['result']['soul'] != described['result']['soul'], root
                inventory = await native.rpc('model.options', profile='native-buddy', include_unconfigured=False,
                                             explicit_only=False)
                assert isinstance(inventory.get('result', {}).get('providers'), list), inventory
                graph = await client.get('/api/learning/graph', params={'profile': 'native-buddy'})
                assert graph.status_code == 200, graph.text
                assert graph.json()['stats']['memory_nodes'] == 0
                await check_created_bot_chat(native)
            await check_memory_owner_and_stale_identity(client)


async def check_created_bot_chat(native):
    created = await native.rpc('session.create', profile='native-buddy', source='ios', title='Bot Chat',
        hidden=True, follow_profile_config=True, request_id='new-bot-chat')
    sid = created['result']['session_id']
    submitted = await native.rpc('prompt.submit', profile='native-buddy', session_id=sid, text='Hello Loki',
                                 input_id=secrets.token_hex(16), submission_id=secrets.token_hex(16))
    assert submitted['result']['status'] == 'queued', submitted
    completed = await native.event('message.complete', session_id=sid)
    assert completed['payload']['outcome'] == 'completed', completed
    snapshot = await native.rpc('session.resume', profile='native-buddy', session_id=sid)
    assert 'local test gateway' in str(snapshot['result']['messages'])
    root = await native.rpc('session.list', profile='default', title='Bot Chat', include_hidden=True, limit=20)
    assert not root['result']['sessions'], root


async def check_memory_owner_and_stale_identity(client):
    graph = (await client.get('/api/learning/graph', params={'profile': 'default'})).json()
    memory = next(node for node in graph['nodes'] if node['kind'] == 'memory')
    assert len(memory['id'].split(':')) == 4
    detail = await client.get('/api/learning/node', params={'id': memory['id'], 'profile': 'default'})
    assert detail.status_code == 200, detail.text
    assert 'LOCAL UI TEST FIXTURE' in detail.json()['content']
    body = {'id': memory['id'], 'content': 'LOCAL UI TEST FIXTURE: Edited from a phone.', 'profile': 'native-buddy'}
    foreign = await client.put('/api/learning/node', params={'profile': 'native-buddy'}, json=body)
    assert foreign.status_code == 400, foreign.text
    body['profile'] = 'default'
    saved = await client.put('/api/learning/node', params={'profile': 'default'}, json=body)
    assert saved.status_code == 200 and saved.json()['ok'] is True, saved.text
    stale = await client.get('/api/learning/node', params={'id': memory['id'], 'profile': 'default'})
    assert stale.status_code == 404, stale.text
    graph = (await client.get('/api/learning/graph', params={'profile': 'default'})).json()
    updated = next(node for node in graph['nodes'] if node['kind'] == 'memory')
    assert updated['id'] != memory['id']
    detail = await client.get('/api/learning/node', params={'id': updated['id'], 'profile': 'default'})
    assert detail.json()['content'] == body['content']
