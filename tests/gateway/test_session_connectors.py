"""Native cards operate on the canonical owner, with only the remote connector HTTP stubbed."""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
import pytest_asyncio


class ConnectorService:
    def __init__(self):
        self.connected = threading.Event()
        self.mints = []
        self.homes = []

    def list_connectors(self):
        from hermes_constants import get_hermes_home
        self.homes.append(get_hermes_home())
        return [{'connector': 'hubspot', 'enabled': True, 'connected': self.connected.is_set()}]

    def connections(self, names, **kwargs):
        self.mints.append((names, kwargs))
        return {'results': [{'connector': 'hubspot', 'status': 'initiated',
                             'connection_id': 'ca_hubspot', 'connect_url': 'https://connect.example/hubspot'}]}

    def account_status(self, connection_id, *, timeout):
        assert connection_id == 'ca_hubspot'
        return {'status': 'active' if self.connected.is_set() else 'pending'}


class Frames:
    def __init__(self):
        self.frames = []

    def write(self, frame):
        self.frames.append(frame)
        return True

    def close(self):
        return None


@pytest_asyncio.fixture
async def owner(tmp_path, monkeypatch):
    from gateway import run
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore
    from gateway.session_authority import initialize_session_authority
    from gateway.session_controls import AuthorityConnection
    from tools.connectors import live, managed
    import tools.connectors

    home = tmp_path / 'home'
    home.mkdir()
    (home / 'config.yaml').write_text('model: {default: gpt-5.4}\nplatform_toolsets: {cli: [connections]}\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(run, '_hermes_home', home)
    config = GatewayConfig(multiplex_profiles=True)
    store = SessionStore(tmp_path / 'sessions', config)
    runner = SimpleNamespace(config=config, session_store=store, _session_db=store._db, adapters={},
                             _draining=False, _cached_agent_for=lambda route: None)
    runner._adapter_for_source = lambda source: runner.adapters.get(source.platform)
    authority = await initialize_session_authority(runner, profile_id=str(home), instance_id='test')
    service, frames = ConnectorService(), Frames()
    monkeypatch.setattr(tools.connectors, 'connectors_available', lambda: True)
    monkeypatch.setattr(managed, 'managed_client', lambda **kwargs: service)
    connection = AuthorityConnection(authority, frames, {'user_id': 'human'})
    created = await connection.dispatch({'id': 1, 'method': 'session.create', 'params': {
        'request_id': 'native', 'source': 'ios', 'cwd': str(tmp_path), 'toolsets': ['connections']}})
    assert 'result' in created, created
    sid = created['result']['session_id']
    resumed = await connection.dispatch({'id': 2, 'method': 'session.resume', 'params': {'session_id': sid}})
    assert 'result' in resumed, resumed
    ambient = tmp_path / 'ambient'
    ambient.mkdir()
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    home_token = set_hermes_home_override(str(ambient))
    fixture = SimpleNamespace(authority=authority, connection=connection, sid=sid, home=home, service=service,
                              frames=frames, workers=[])
    try:
        yield fixture
    finally:
        from tools.connectors.contract import SettleReason
        binding = authority.sessions[sid].connection_operation
        if binding is not None:
            binding.operation.settle(SettleReason.interrupt)
        await asyncio.gather(*fixture.workers, return_exceptions=True)
        await connection.close()
        live.reset_for_tests()
        reset_hermes_home_override(home_token)
        store._db.close()


async def call(owner, method, **params):
    return await owner.connection.dispatch({'id': 3, 'method': method, 'params': {
        'owner': {'type': 'session', 'session_id': owner.sid}, **params}})


async def open_card(owner):
    from gateway.local_connections import wire
    from gateway.session_authorities import owner_scope
    from gateway.session_context import clear_session_vars, set_session_vars
    from tests.waiting import async_wait_until
    from tools.connectors.managed import run_managed_action
    from tools.connectors.targets import HostedTarget

    authority = owner.authority
    authority.executing[owner.sid] = 1
    agent = SimpleNamespace(platform='mobile')
    wire(SimpleNamespace(_approval_owner=(authority, owner.sid, 1)), agent)

    def execute():
        with owner_scope(authority):
            tokens = set_session_vars(platform='mobile', source='mobile',
                                      session_key=authority.sessions[owner.sid].route, session_id=owner.sid)
            try:
                return run_managed_action('connect', [HostedTarget('hubspot')], {}, session_id=owner.sid,
                                          tool_call_id='tool_hubspot', connection_callback=agent.connection_callback)
            finally:
                clear_session_vars(tokens)
    worker = asyncio.create_task(asyncio.to_thread(execute))
    owner.workers.append(worker)
    binding = await async_wait_until(lambda: authority.sessions[owner.sid].connection_operation,
                                     what='canonical connection card')
    return binding, worker


@pytest.mark.asyncio
async def test_mobile_tool_card_recovers_and_only_backend_confirms_connection(owner):
    from tests.waiting import async_wait_until
    from tui_gateway.contracts.connectors_operation import ConnectionRequestPayload, ConnectionUpdatePayload

    listing = await call(owner, 'connectors.list')
    assert listing['result']['connectors'][0]['connector'] == 'hubspot', listing
    assert owner.service.homes == [owner.home]
    binding, worker = await open_card(owner)
    operation = binding.operation
    await async_wait_until(lambda: owner.frames.frames, what='connection request delivery')
    request = next(frame['params'] for frame in owner.frames.frames if frame['params']['type'] == 'connection.request')
    ConnectionRequestPayload.model_validate(request['payload'])
    assert request['session_id'] == owner.sid and request['payload']['tool_call_id'] == 'tool_hubspot'
    assert owner.service.mints[0][1].keys() == {'reinitiate', 'alias', 'connection_id'}
    resumed = await owner.connection.dispatch({'id': 4, 'method': 'session.resume', 'params': {'session_id': owner.sid}})
    assert 'result' in resumed, resumed
    assert resumed['result']['pending_connection']['op_id'] == operation.op_id
    forged = await call(owner, 'connection.respond', op_id=operation.op_id,
                        result={'targets': [{'name': 'hubspot', 'status': 'connected'}]})
    assert forged['error']['data']['reason'] == 'invalid_params'
    approved = await call(owner, 'connection.respond', op_id=operation.op_id,
                          result={'targets': [{'name': 'hubspot', 'status': 'approved'}]})
    assert approved['result'] == {'status': 'ok', 'settled': False}
    status = await call(owner, 'connectors.operation.status', op_id=operation.op_id)
    assert status['result']['targets'][0]['state'] == 'initiated' and not worker.done()
    owner.service.connected.set()
    assert (await call(owner, 'connectors.operation.wake', op_id=operation.op_id))['result'] == {'status': 'ok'}
    result = json.loads(await asyncio.wait_for(worker, 10))
    assert result['targets'][0]['state'] == 'connected' and 'connect_url' not in result['targets'][0]
    await async_wait_until(lambda: any(frame['params']['type'] == 'connection.update' and
                                      frame['params']['payload']['settled'] for frame in owner.frames.frames),
                           what='settled connector update')
    updates = [frame['params']['payload'] for frame in owner.frames.frames if frame['params']['type'] == 'connection.update']
    for update in updates:
        ConnectionUpdatePayload.model_validate(update)
        assert update['owner'] == {'type': 'session', 'session_id': owner.sid}
    assert any(update.get('actor') == 'backend_watcher' and update.get('to') == 'connected' for update in updates)
    assert updates[-1]['settled'] is True
    resumed = await owner.connection.dispatch({'id': 5, 'method': 'session.resume', 'params': {'session_id': owner.sid}})
    assert resumed['result']['pending_connection'] is None


@pytest.mark.asyncio
async def test_connector_controls_require_attached_profile_owner_and_current_generation(owner):
    from gateway.session_controls import AuthorityConnection
    from gateway.local_connections import pending_connection
    from tools.connectors.contract import Actor, TargetState

    binding, worker = await open_card(owner)
    op = binding.operation
    stranger = AuthorityConnection(owner.authority, Frames(), {'user_id': 'human'})
    try:
        params = {'owner': {'type': 'session', 'session_id': owner.sid}, 'op_id': op.op_id}
        denied = await stranger.dispatch({'id': 1, 'method': 'connectors.operation.wake', 'params': params})
        assert denied['error']['data']['reason'] == 'permission_denied'
        foreign = await call(owner, 'connectors.operation.wake', op_id=op.op_id, profile='other')
        assert foreign['error']['data']['reason'] == 'profile_mismatch'
        wrong = await call(owner, 'connectors.operation.status', op_id='not-this-operation')
        assert wrong['error']['data']['reason'] == 'unknown_operation'
        op.transition('hubspot', TargetState.expired, Actor.clock)
        other_account = await call(owner, 'connectors.connect', connectors=['hubspot'], alias='another-account')
        assert other_account['error']['data']['reason'] == 'unknown_target'
        retried = await call(owner, 'connectors.connect', connectors=['hubspot'])
        assert retried['result']['op_id'] == op.op_id
        assert retried['result']['targets'][0]['state'] == 'initiated'
        assert owner.service.mints[-1][1] == {
            'reinitiate': True, 'alias': None, 'connection_id': 'ca_hubspot'}
        owner.authority.executing[owner.sid] = 2
        sequence = owner.authority.sessions[owner.sid].event_stream.sequence
        op.transition('hubspot', TargetState.expired, Actor.clock)
        assert owner.authority.sessions[owner.sid].event_stream.sequence == sequence
        stale = await call(owner, 'connection.respond', op_id=op.op_id,
                           result={'targets': [{'name': 'hubspot', 'status': 'skipped'}]})
        assert stale['error']['data']['reason'] == 'stale_generation'
        assert op.target('hubspot').state.value == 'expired'
        assert pending_connection(owner.authority, owner.sid) is None
        owner.authority.executing[owner.sid] = 1
        continued = await call(owner, 'connection.respond', op_id=op.op_id, result={'settled_by': 'continue'})
        assert continued['result'] == {'status': 'ok', 'settled': True}
        assert json.loads(await asyncio.wait_for(worker, 10))['targets'][0]['state'] == 'not_connected'
        await owner.connection.close()
        detached = await call(owner, 'connectors.operation.status', op_id=op.op_id)
        assert detached['error']['data']['reason'] == 'permission_denied'
    finally:
        await stranger.close()
