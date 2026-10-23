"""Registered mobile callbacks extend the native PKCE broker without widening desktop returns."""
import base64
import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from hermes_cli import web_server
from hermes_cli.dashboard_auth import clear_providers, register_provider, native_flow
from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider

CALLBACK = 'com.loki.ios://auth/callback'
CLIENT = 'loki-ios'
STATE = 'mobile-state-' + 's' * 32
VERIFIER = 'mobile-verifier-' + 'v' * 48
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()


@pytest.fixture
def mobile_client(tmp_path, monkeypatch):
    from hermes_cli.config import atomic_config_write
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    atomic_config_write(home / 'config.yaml', {'dashboard': {'native_auth': {'clients': {
        CLIENT: {'redirect_uris': [CALLBACK]}}}}})
    clear_providers()
    native_flow._reset_for_tests()
    register_provider(StubAuthProvider())
    monkeypatch.setattr(web_server.app.state, 'bound_host', 'gateway.example.test', raising=False)
    monkeypatch.setattr(web_server.app.state, 'bound_port', 443, raising=False)
    monkeypatch.setattr(web_server.app.state, 'auth_required', True, raising=False)
    with TestClient(web_server.app, base_url='https://gateway.example.test', follow_redirects=False) as client:
        yield client
    clear_providers()
    native_flow._reset_for_tests()


def _authorize(client, **overrides):
    return client.get('/auth/native/authorize', params={
        'provider': 'stub', 'client_id': CLIENT, 'redirect_uri': CALLBACK,
        'code_challenge': CHALLENGE, 'code_challenge_method': 'S256', 'state': STATE, **overrides})


def _login_code(client):
    start = _authorize(client)
    assert start.status_code == 302, start.text
    callback = client.get(start.headers['location'])
    assert callback.status_code == 302, callback.text
    returned = urlparse(callback.headers['location'])
    assert returned._replace(query='').geturl() == CALLBACK
    values = parse_qs(returned.query)
    assert values['state'] == [STATE]
    assert 'hermes_session_at' not in callback.headers.get('set-cookie', '')
    return values['code'][0]


def test_registered_mobile_pkce_login_authenticates_gateway_without_cookies(mobile_client):
    code = _login_code(mobile_client)
    result = mobile_client.post('/auth/native/token', json={
        'code': code, 'code_verifier': VERIFIER, 'client_id': CLIENT, 'redirect_uri': CALLBACK})
    assert result.status_code == 200, result.text
    token = result.json()['access_token']
    mobile_client.cookies.clear()
    headers = {'Authorization': f'Bearer {token}'}
    identity = mobile_client.get('/api/auth/me', headers=headers)
    assert identity.status_code == 200 and identity.json()['user_id'] == 'stub-user-1'
    ticket = mobile_client.post('/api/auth/ws-ticket', headers=headers)
    assert ticket.status_code == 200 and ticket.json()['ttl_seconds'] == 30
    assert ticket.json()['ticket']
    assert mobile_client.post('/auth/native/token', json={
        'code': code, 'code_verifier': VERIFIER, 'client_id': CLIENT, 'redirect_uri': CALLBACK}).status_code == 400


def test_mobile_return_requires_exact_registered_client_uri_and_fresh_state(mobile_client):
    for params in (
        {'client_id': 'unregistered'}, {'client_id': ''},
        {'redirect_uri': 'com.loki.ios://auth/other'},
        {'redirect_uri': CALLBACK + '?state=attacker'},
        {'redirect_uri': CALLBACK + '#fragment'},
        {'redirect_uri': 'https://unregistered.example/callback'},
        {'redirect_uri': 'com.loki.ios://auth/callback/../callback'},
        {'state': ''}, {'state': 'short'}, {'code_challenge': 'not-S256'},
    ):
        result = _authorize(mobile_client, **params)
        assert result.status_code == 400, (params, result.text)


def test_mobile_code_is_bound_to_client_callback_and_pkce_and_consumed_on_failure(mobile_client):
    for bad in ({'client_id': 'other'}, {'redirect_uri': 'com.other.app://auth/callback'},
                {'code_verifier': 'wrong-verifier-' + 'x' * 48}):
        body = {'code': _login_code(mobile_client), 'code_verifier': VERIFIER,
                'client_id': CLIENT, 'redirect_uri': CALLBACK}
        assert mobile_client.post('/auth/native/token', json={**body, **bad}).status_code == 400
        assert mobile_client.post('/auth/native/token', json=body).status_code == 400
