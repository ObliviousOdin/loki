"""Public transport readiness is checked only on an explicit action, against the pinned host."""
import json

import httpx
import pytest

from hermes_cli.dashboard_auth.device_links_config import DeviceLinkService, https_origin
from hermes_cli.dashboard_auth.device_links_crypto import LinkError
pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_store',)


def test_transport_check_rejects_redirect_wrong_host_and_large_reply(phone_store, monkeypatch):
    import hermes_cli.dashboard_auth.device_links_config as module
    store, _, _ = phone_store
    responses = [httpx.Response(301, json={'service': 'loki-phone-ingress', 'version': 1,
                                         'ready': True, 'host_id': store.host_id}),
                 httpx.Response(200, json={'service': 'loki-phone-ingress', 'version': 1,
                                         'ready': True, 'host_id': 'different'}),
                 httpx.Response(200, content=b'x' * 4097),
                 httpx.Response(200, json={'service': 'loki-phone-ingress', 'version': 1,
                                         'ready': True, 'host_id': store.host_id})]
    seen = []
    def handle(request):
        seen.append(request)
        return responses.pop(0)
    client = httpx.Client
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(handle), **kwargs))
    service = DeviceLinkService(store, 'https://links.example.test', 'synthetic-secret-' + 'x' * 48)
    assert not service.transport_ready and seen == []
    for _ in range(3):
        with pytest.raises(LinkError, match='transport_unavailable'):
            service.verify_transport()
        assert not service.transport_ready and service.transport_verified_at is None
    service.verify_transport()
    assert service.transport_ready
    assert all(str(r.url) == 'https://mac.example.test/health' and 'Authorization' not in r.headers for r in seen)


def test_registration_uses_exact_origin_secret_and_bounded_no_redirect_client(phone_store, monkeypatch):
    import hermes_cli.dashboard_auth.device_links_config as module
    store, owner, _ = phone_store
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(201 if request.method == 'POST' else 204)
    original = httpx.Client
    options = []
    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(module.httpx, 'Client', client)
    secret = 'synthetic-registration-' + 'x' * 48
    service = DeviceLinkService(store, 'https://links.example.test', secret)
    pairing = store.create_pairing(owner)
    service.registration(pairing)
    service.cancellation(pairing['pairing_id'])
    assert [r.method for r in seen] == ['POST', 'DELETE']
    assert json.loads(seen[0].content) == pairing
    assert all(r.headers['Authorization'] == 'Bearer ' + secret for r in seen)
    assert all(c['follow_redirects'] is False and c['trust_env'] is False and c['timeout'] == 8 for c in options)
    assert str(seen[1].url) == 'https://links.example.test/v1/pairings/' + pairing['pairing_id']
    for bad in ('http://mac.example.test', 'https://user:pass@mac.example.test',
                'https://mac.example.test/path', 'https://mac.example.test?redirect=other',
                'https://mac.example.test:9443', 'https://mac.example.test/#x', 'https://@mac.example.test',
                'https://[fe80::1%25en0]'):
        with pytest.raises(LinkError):
            https_origin(bad)


@pytest.mark.parametrize(('configured', 'origin'), [
    ('HTTPS://MAC.Example.Test:443/', 'https://mac.example.test'),
    ('https://mac.example.test/', 'https://mac.example.test'),
    ('https://BÜCHER.example:443/', 'https://xn--bcher-kva.example'),
    ('https://[2001:0db8:0000:0000:0000:0000:0000:0001]:443/', 'https://[2001:db8::1]'),
])
def test_configured_origin_matches_rendezvous_normalized_origin(configured, origin):
    assert https_origin(configured) == origin


def test_configured_host_label_is_canonical_before_registration_and_signature(monkeypatch):
    from fastapi import FastAPI
    from hermes_cli.config import atomic_config_write
    from hermes_cli.dashboard_auth.device_links_config import configure_device_links
    from hermes_cli.dashboard_auth.registry import clear_providers
    from hermes_constants import get_hermes_home
    atomic_config_write(get_hermes_home() / 'config.yaml', {'dashboard': {'device_links': {
        'enabled': True, 'gateway_url': 'HTTPS://MAC.Example.Test:443/',
        'rendezvous_url': 'https://links.example.test/', 'host_name': '  Test Mac  '}}})
    monkeypatch.setenv('LOKI_PHONE_LINK_REGISTRATION_TOKEN', 'synthetic-' + 'x' * 48)
    app = FastAPI()
    try:
        configure_device_links(app)
        service = app.state.device_links_service
        assert service is not None
        assert service.store.host == {**service.store.host, 'host_name': 'Test Mac', 'gateway_url': 'https://mac.example.test'}
        assert service.rendezvous_url == 'https://links.example.test'
    finally:
        clear_providers()
