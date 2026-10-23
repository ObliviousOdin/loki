"""Phone setup uses its launch-home secrets and one browser origin for upstream OAuth."""
import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_http',)


def _configure(home, *, public_url=''):
    from hermes_cli.config import atomic_config_write
    atomic_config_write(home / 'config.yaml', {'dashboard': {
        'public_url': public_url, 'device_links': {
            'enabled': True, 'gateway_url': 'https://phone.example.test',
            'rendezvous_url': 'https://links.example.test', 'host_name': 'Test Mac'}}})


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_scope", [False, True])
async def test_multiplex_gateway_mount_reads_own_dotenv_without_borrowing_foreign_scope(monkeypatch, tmp_path, foreign_scope):
    from agent.secret_scope import (
        current_secret_scope, reset_secret_scope, set_secret_scope)
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.run_runtime import initialize_gateway_runtime, start_gateway_runtime_api
    from gateway.runtime_ownership import process_ownership
    from hermes_cli import web_server as web
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from hermes_constants import get_hermes_home
    from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider

    home = get_hermes_home().resolve()
    _configure(home)
    (home / '.env').write_text('LOKI_PHONE_LINK_REGISTRATION_TOKEN=synthetic-own-' + 'x' * 48 + '\n')
    monkeypatch.setenv('LOKI_PHONE_LINK_REGISTRATION_TOKEN', 'synthetic-ambient-' + 'y' * 48)
    foreign = {'LOKI_PHONE_LINK_REGISTRATION_TOKEN': 'synthetic-foreign-' + 'z' * 48}
    token = set_secret_scope(foreign if foreign_scope else None, profile_home=str(tmp_path / 'foreign'))
    clear_providers()
    register_provider(StubAuthProvider())
    process_ownership.reserve([home])
    runner = GatewayRunner(GatewayConfig(multiplex_profiles=True))
    try:
        await initialize_gateway_runtime(runner)
        await start_gateway_runtime_api(runner)
        service = web.app.state.device_links_service
        assert service is not None
        assert service.store.home == str(home)
        assert service._registration_secret == 'synthetic-own-' + 'x' * 48
        assert current_secret_scope() == (foreign if foreign_scope else None)
    finally:
        await runner.stop()
        process_ownership.close()
        clear_providers()
        reset_secret_scope(token)


def test_missing_own_secret_does_not_use_foreign_scope_or_multiplex_ambient(monkeypatch, tmp_path):
    from agent.secret_scope import (
        current_secret_scope, reset_secret_scope, set_multiplex_active, set_secret_scope)
    from hermes_cli.dashboard_auth.device_links_config import configure_device_links
    from hermes_cli.dashboard_auth import clear_providers
    from hermes_constants import get_hermes_home
    _configure(get_hermes_home())
    foreign = {'LOKI_PHONE_LINK_REGISTRATION_TOKEN': 'synthetic-foreign-' + 'z' * 48}
    token = set_secret_scope(foreign, profile_home=str(tmp_path / 'foreign'))
    set_multiplex_active(True)
    monkeypatch.setenv('LOKI_PHONE_LINK_REGISTRATION_TOKEN', 'synthetic-ambient-' + 'y' * 48)
    app = FastAPI()
    try:
        configure_device_links(app)
        assert app.state.device_links_service is None
        assert app.state.device_links_error == 'registration_secret_missing'
        assert current_secret_scope() == foreign
    finally:
        clear_providers()
        set_multiplex_active(False)
        reset_secret_scope(token)


@pytest.mark.asyncio
@pytest.mark.parametrize('public_url', ['', 'https://mac.example.test'])
async def test_owner_browser_base_keeps_pkce_cookie_and_token_redemption_local(device_api, public_url):
    from hermes_cli import web_server as web
    from hermes_cli.config import atomic_config_write, load_config
    from hermes_constants import get_hermes_home
    client, native, _, service, _ = device_api
    service.store.gateway_url = 'https://phone.example.test'
    config = load_config()
    config['dashboard']['public_url'] = public_url
    atomic_config_write(get_hermes_home() / 'config.yaml', config)
    response = await client.get('/api/device-links', headers=native())
    assert response.status_code == 200
    base = response.json()['owner_login']['authorize_base_url']
    assert base == (public_url or str(client.base_url).rstrip('/'))
    verifier = 'v' * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    with TestClient(web.app, base_url=base, follow_redirects=False) as browser:
        start = browser.get('/auth/native/authorize', params={
            'provider': 'stub', 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'redirect_uri': 'http://127.0.0.1:53123/callback', 'state': 's' * 48})
        assert start.status_code == 302
        callback = browser.get(start.headers['location'])
        assert callback.status_code == 302, callback.text
        code = parse_qs(urlsplit(callback.headers['location']).query)['code'][0]
    redeemed = await client.post('/auth/native/token', json={
        'code': code, 'code_verifier': verifier, 'redirect_uri': 'http://127.0.0.1:53123/callback'})
    assert redeemed.status_code == 200
    overview = await client.get('/api/device-links', headers={
        **native(), 'Authorization': 'Bearer ' + redeemed.json()['access_token']})
    assert overview.status_code == 200
    assert overview.json()['owner_sign_in_required'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(('public_url', 'expected'), [
    ('https://private.example.test/hermes/', 'https://private.example.test/hermes'),
    ('https://phone.example.test', None),
    ('https://phone.example.test/hermes', None),
    ('https://user:password@private.example.test', None),
    ('https://private.example.test?next=elsewhere', None),
    ('http://private.example.test', None),
])
async def test_owner_browser_base_preserves_prefix_and_refuses_unsafe_or_phone_ingress(device_api, public_url, expected):
    from hermes_cli.config import atomic_config_write, load_config
    from hermes_constants import get_hermes_home
    client, native, _, service, _ = device_api
    # The actual facade origin is distinct from the old private dashboard origin.
    service.store.gateway_url = 'https://phone.example.test'
    config = load_config()
    config['dashboard']['public_url'] = public_url
    atomic_config_write(get_hermes_home() / 'config.yaml', config)
    response = await client.get('/api/device-links', headers=native())
    assert response.status_code == 200
    assert response.json()['owner_login']['authorize_base_url'] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('phone_is_public_url', [False, True])
async def test_password_owner_uses_local_browser_even_with_private_or_unavailable_oauth_base(device_api, phone_is_public_url):
    from hermes_cli import web_server as web
    from hermes_cli.dashboard_auth import register_provider
    from tests.hermes_cli.test_dashboard_auth_password_login import PasswordProvider
    client, native, _, service, _ = device_api
    if not phone_is_public_url:
        service.store.gateway_url = 'https://phone.example.test'
    register_provider(PasswordProvider())
    overview = (await client.get('/api/device-links', headers=native())).json()
    login = overview['owner_login']
    assert login['authorize_base_url'] == (None if phone_is_public_url else 'https://mac.example.test')
    assert next(p for p in login['providers'] if p['name'] == 'testpw')['supports_password'] is True
    verifier = 'v' * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    with TestClient(web.app, base_url=str(client.base_url), follow_redirects=False) as browser:
        start = browser.get('/auth/native/authorize', params={
            'provider': 'testpw', 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'redirect_uri': 'http://127.0.0.1:53123/callback', 'state': 's' * 48})
        assert start.status_code == 302 and start.headers['location'] == '/login'
        assert browser.get('/login').status_code == 200
        completed = browser.post('/auth/password-login', json={
            'provider': 'testpw', 'username': 'admin', 'password': 'hunter2'})
        assert completed.status_code == 200
        code = parse_qs(urlsplit(completed.json()['next']).query)['code'][0]
    token = await client.post('/auth/native/token', json={
        'code': code, 'code_verifier': verifier, 'redirect_uri': 'http://127.0.0.1:53123/callback'})
    assert token.status_code == 200
    verified = await client.get('/api/device-links', headers={
        **native(), 'Authorization': 'Bearer ' + token.json()['access_token']})
    assert verified.status_code == 200 and verified.json()['owner']['provider'] == 'testpw'
