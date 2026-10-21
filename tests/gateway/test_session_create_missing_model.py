"""Missing configuration must not commit a session that recovery cannot restore."""
import json
import socket
from types import SimpleNamespace

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def owner(tmp_path, monkeypatch):
    from gateway import run
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore
    from gateway.session_authority import initialize_session_authority
    from gateway.session_controls import AuthorityConnection

    home = tmp_path / 'profile'
    home.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(run, '_hermes_home', home)
    (home / '.env').write_text('')
    (home / 'config.yaml').write_text(json.dumps({
        'model': '', 'platform_toolsets': {'cli': []},
        'auth': {'adopt_external_logins': False, 'hosted_services': False},
    }))

    def no_network(*_args, **_kwargs):
        pytest.fail('Session configuration must not contact a provider')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    store = SessionStore(home / 'sessions', GatewayConfig())
    runner = SimpleNamespace(session_store=store, _session_db=store._db, adapters={},
                             _draining=False, _cached_agent_for=lambda _route: None)
    runner._adapter_for_source = lambda source: runner.adapters.get(source.platform)
    authority = await initialize_session_authority(runner, profile_id=str(home), instance_id='fixture')
    connection = AuthorityConnection(authority, object(), {'user_id': 'human'})
    store._db.create_session('preserved-session', 'cli')
    try:
        yield connection, home
    finally:
        store._db.close()


def durable_counts(db):
    with db._read_ctx() as conn:
        return {
            'sessions': conn.execute('SELECT count(*) FROM sessions').fetchone()[0],
            'routes': conn.execute('SELECT count(*) FROM gateway_routing').fetchone()[0],
            'policies': conn.execute("SELECT count(*) FROM state_meta WHERE key GLOB 'gateway.local_policy.v1:*'")
                .fetchone()[0],
        }


@pytest.mark.asyncio
@pytest.mark.parametrize('model', ['', {'default': '', 'provider': 'custom', 'base_url': 'http://127.0.0.1:9/v1'}])
async def test_missing_model_refuses_before_any_durable_creation(owner, model):
    connection, home = owner
    config = json.loads((home / 'config.yaml').read_text())
    config['model'] = model
    (home / 'config.yaml').write_text(json.dumps(config))
    db = connection.authority.db
    before = durable_counts(db)
    reply = await connection.dispatch({'id': 1, 'method': 'session.create', 'params': {
        'request_id': 'unconfigured', 'source': 'tui', 'cwd': str(home), 'toolsets': [],
    }})
    after = durable_counts(db)
    error = reply.get('error', {})
    print(json.dumps({'reason': error.get('message'), 'before': before, 'after': after}))
    assert error.get('message') == 'invalid_params', reply
    assert error['data']['field'] == 'model'
    assert error['data']['detail']
    assert after == before
    assert db.get_session('preserved-session') is not None


@pytest.mark.asyncio
async def test_explicit_model_is_accepted_without_a_profile_default(owner):
    connection, home = owner
    from hermes_state_local import local_receipt
    from gateway.session_contract import SessionRef
    from gateway.session_policy import restore_policy

    reply = await connection.dispatch({'id': 2, 'method': 'session.create', 'params': {
        'request_id': 'explicit', 'source': 'tui', 'cwd': str(home), 'toolsets': [],
        'model': 'local-fixture', 'provider': 'custom', 'base_url': 'http://127.0.0.1:9/v1',
    }})
    assert 'result' in reply, reply
    sid = reply['result']['session_id']
    assert restore_policy(local_receipt(connection.authority.db, sid)['policy']).model == 'local-fixture'
    assert json.loads((home / 'config.yaml').read_text())['model'] == ''
    assert connection.authority.agent(SessionRef(connection.authority.profile_id, sid)) is None


@pytest.mark.asyncio
async def test_exact_retry_restores_its_frozen_model_after_the_default_is_cleared(owner):
    connection, home = owner
    config = json.loads((home / 'config.yaml').read_text())
    config['model'] = {'default': 'frozen-fixture', 'provider': 'custom', 'base_url': 'http://127.0.0.1:9/v1'}
    (home / 'config.yaml').write_text(json.dumps(config))
    params = {'request_id': 'retry', 'source': 'tui', 'cwd': str(home), 'toolsets': []}
    first = await connection.dispatch({'id': 3, 'method': 'session.create', 'params': params})
    assert 'result' in first, first
    db = connection.authority.db
    before = durable_counts(db)
    config['model'] = ''
    (home / 'config.yaml').write_text(json.dumps(config))

    retry = await connection.dispatch({'id': 4, 'method': 'session.create', 'params': params})

    assert 'result' in retry, retry
    assert retry['result']['session_id'] == first['result']['session_id']
    assert retry['result']['info']['model'] == 'frozen-fixture'
    assert durable_counts(db) == before
