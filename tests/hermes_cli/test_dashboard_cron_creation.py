"""Durable HTTP creation binds verified identity before the real store/provider transaction."""
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest


class Scheduler:
    name = 'test-only'

    def __init__(self):
        self.fail, self.registered = True, []

    def register_job(self, job):
        self.registered.append(job['id'])
        if self.fail:
            raise RuntimeError('synthetic scheduler outage')

    def on_jobs_changed(self):
        return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    from cron import scheduler_provider
    from hermes_cli import web_server
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(web_server.app.state, 'bound_host', 'gateway.example.test', raising=False)
    monkeypatch.setattr(web_server.app.state, 'bound_port', 443, raising=False)
    monkeypatch.setattr(web_server.app.state, 'auth_required', True, raising=False)
    clear_providers()
    register_provider(StubAuthProvider())
    scheduler = Scheduler()
    monkeypatch.setattr(scheduler_provider, 'resolve_cron_scheduler', lambda: scheduler)
    with TestClient(web_server.app, base_url='https://gateway.example.test', follow_redirects=False) as http:
        yield http, scheduler
    clear_providers()


def bearer(user):
    from tests.hermes_cli.conftest_dashboard_auth import _sign
    return {'Authorization': 'Bearer ' + _sign({'sub': user, 'email': user + '@example.test',
        'name': 'Test user', 'org_id': 'test', 'exp': int(time.time()) + 3600})}


def test_create_retries_after_saved_424_keep_one_job_and_bind_identity(client):
    http, scheduler = client
    body = {'request_id': 'native-create-request-0123456789', 'name': 'Morning',
            'prompt': 'Plan a calm morning', 'schedule': 'every 2h'}
    assert http.get('/api/cron/capabilities').status_code == 401
    headers = bearer('owner')
    assert http.get('/api/cron/capabilities', headers=headers).json() == {'durable_creation': {'version': 1}}
    first = http.post('/api/cron/jobs?profile=default', json=body, headers=headers)
    assert first.status_code == 424, first.text
    job_id = first.json()['detail']['job_id']
    assert first.json()['detail']['job_saved'] is True
    scheduler.fail = False
    retry = http.post('/api/cron/jobs?profile=default', json=body, headers=headers)
    assert retry.status_code == 200 and retry.json()['id'] == job_id, retry.text
    assert scheduler.registered == [job_id, job_id]
    for changed, identity in (({**body, 'prompt': 'Different intent'}, headers), (body, bearer('other'))):
        refused = http.post('/api/cron/jobs?profile=default', json=changed, headers=identity)
        assert refused.status_code == 409 and refused.json()['detail']['reason'] == 'creation_request_conflict'
    assert http.delete('/api/cron/jobs/' + job_id + '?profile=default', headers=headers).status_code == 200
    deleted = http.post('/api/cron/jobs?profile=default', json=body, headers=headers)
    assert deleted.status_code == 409 and deleted.json()['detail']['reason'] == 'creation_target_deleted'
    assert scheduler.registered == [job_id, job_id]


def test_legacy_creation_still_creates_independent_jobs_and_invalid_request_id_is_rejected(client):
    http, scheduler = client
    scheduler.fail = False
    body = {'prompt': 'Legacy creation', 'schedule': 'every 3h', 'paused': True}
    headers = bearer('owner')
    first = http.post('/api/cron/jobs?profile=default', json=body, headers=headers)
    second = http.post('/api/cron/jobs?profile=default', json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()['id'] != second.json()['id']
    invalid = http.post('/api/cron/jobs?profile=default', json={**body, 'request_id': 'short'}, headers=headers)
    assert invalid.status_code == 422
