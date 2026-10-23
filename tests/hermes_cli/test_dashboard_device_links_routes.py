"""Phone bootstrap remains anonymous only for its four bounded public exchanges."""
from fastapi.testclient import TestClient

pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_store',)


def test_device_bootstrap_is_an_explicit_public_bounded_route(monkeypatch):
    from hermes_cli import web_server
    monkeypatch.setattr(web_server.app.state, 'auth_required', True, raising=False)
    monkeypatch.setattr(web_server.app.state, 'device_links_service', None, raising=False)
    with TestClient(web_server.app, base_url='http://localhost') as client:
        response = client.post('/auth/device/challenge', json={
            'device_id': 'device_synthetic00001', 'host_id': 'a' * 64})
        assert response.status_code == 503, response.text
        assert response.json() == {'detail': 'device_links_not_ready'}
        assert client.get('/api/device-links').status_code == 401


def test_anonymous_bootstrap_has_peer_rate_and_body_bounds(monkeypatch):
    from hermes_cli import web_server
    from hermes_cli.dashboard_auth import device_links_routes
    monkeypatch.setattr(web_server.app.state, 'auth_required', True, raising=False)
    monkeypatch.setattr(web_server.app.state, 'device_links_service', None, raising=False)
    monkeypatch.setattr(device_links_routes, '_rates', {})
    body = {'device_id': 'device_synthetic00001', 'host_id': 'a' * 64}
    with TestClient(web_server.app, base_url='http://localhost', follow_redirects=False) as client:
        for _ in range(60):
            assert client.post('/auth/device/challenge', json=body).status_code == 503
        refused = client.post('/auth/device/challenge', json=body)
        assert refused.status_code == 429 and refused.headers['Retry-After'] == '60'
        oversized = client.post('/auth/device/claims', content=b'x' * (65536 + 1),
                                 headers={'Content-Type': 'application/json'})
        assert oversized.status_code == 413
        assert client.post('/auth/device/challenge/extension', json=body).status_code == 302


def test_hidden_phone_verifier_does_not_advertise_interactive_native_login(phone_store, monkeypatch):
    from hermes_cli import web_server
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from hermes_cli.dashboard_auth.device_links_provider import DeviceLinkProvider
    clear_providers()
    register_provider(DeviceLinkProvider(phone_store[0]))
    monkeypatch.setattr(web_server.app.state, 'auth_required', True, raising=False)
    monkeypatch.setattr(web_server.app.state, 'bound_host', 'localhost', raising=False)
    try:
        with TestClient(web_server.app, base_url='http://localhost') as client:
            status = client.get('/api/status')
            assert status.status_code == 200
            assert status.json()['auth_providers'] == ['loki-device']
            assert 'native_pkce' not in status.json()['auth_flows']
            assert client.get('/api/auth/providers').status_code == 503
    finally:
        clear_providers()
