"""Real key proofs, durable custody and atomic phone grants in isolated homes."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import ec
import pytest

from hermes_cli.dashboard_auth.base import Session
from hermes_cli.dashboard_auth.device_links_crypto import (
    LinkError, b64, claim_payload, fingerprint, public_wire, sign, unb64, verify)
from hermes_cli.dashboard_auth.device_links_store import DeviceLinkStore


@pytest.fixture
def phone_store(tmp_path, monkeypatch):
    import hermes_cli.dashboard_auth.device_links_store as module
    now = [2000000000]
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: now[0]))
    owner = Session('existing-owner', '', 'Owner', '', 'existing-idp', now[0] + 3600,
                    'existing-verified-token', '', 'https://issuer.example.test')
    store = DeviceLinkStore(tmp_path / 'one', gateway_url='https://mac.example.test', host_name='Test Mac')
    return store, owner, now


def claim_request(pairing, key, *, nonce=bytes(range(32)), name='Test iPhone'):
    body = {'pairing_id': pairing['pairing_id'], 'code': pairing['code'], 'client_id': 'loki-ios',
            'device_name': name, 'device_public_key': public_wire(key.public_key()), 'nonce': b64(nonce)}
    return {**body, 'signature': sign(key, claim_payload(body))}


def approve_phone(store, owner, key=None):
    key = key or ec.generate_private_key(ec.SECP256R1())
    pairing = store.create_pairing(owner)
    body = claim_request(pairing, key)
    claim = store.claim(body)
    store.settle(claim['claim_id'], approve=True, key_fingerprint=fingerprint(body['device_public_key']),
                 comparison=claim['comparison'])
    return key, claim


def issue(store, key, claim):
    challenge = store.challenge(claim['device_id'], claim['host_id'])
    return store.token(claim['device_id'], challenge['challenge_id'], sign(key, unb64(challenge['payload'])))


def test_claim_retry_exact_review_and_account_identity_survive_restart(phone_store):
    store, owner, _ = phone_store
    key = ec.generate_private_key(ec.SECP256R1())
    pairing = store.create_pairing(owner)
    body = claim_request(pairing, key)
    claim = store.claim(body)
    retry = store.claim({**body, 'signature': sign(key, claim_payload(body))})
    assert (retry['claim_id'], retry['claim_token']) == (claim['claim_id'], claim['claim_token'])
    metadata = claim['host_metadata']
    verify(store.host_public_key, metadata['signature'], unb64(metadata['payload']))
    decoded = json.loads(unb64(metadata['payload']))
    assert decoded['gateway_url'] == store.gateway_url
    assert decoded['device_id'] == claim['device_id'] and decoded['key_fingerprint'] == fingerprint(body['device_public_key'])
    assert store.poll(claim['claim_id'], claim['claim_token'])['status'] == 'pending'
    with pytest.raises(LinkError, match='claim_changed'):
        store.settle(claim['claim_id'], approve=True, key_fingerprint='different', comparison=claim['comparison'])
    assert store.list()['devices'] == []
    store.settle(claim['claim_id'], approve=True, key_fingerprint=decoded['key_fingerprint'], comparison=claim['comparison'])
    token = issue(store, key, claim)
    assert 'refresh_token' not in token
    reopened = DeviceLinkStore(Path(store.home), gateway_url=store.gateway_url, host_name=store.host_name)
    assert reopened.host == store.host
    session = reopened.verify_token(token['access_token'])
    from gateway.session_identity import authenticated_subject
    identity = lambda s: {'user_id': s.user_id, 'provider': s.provider, 'issuer': s.issuer}
    assert authenticated_subject(identity(session)) == authenticated_subject(identity(owner))
    assert session.device_home == store.home and session.device_id == claim['device_id']
    assert (store.path.stat().st_mode & 0o777) == 0o600
    other = DeviceLinkStore(Path(store.home).parent / 'other', gateway_url=store.gateway_url, host_name=store.host_name)
    assert other.verify_token(token['access_token']) is None


def test_real_key_nonce_host_expiry_and_revocation_fail_closed(phone_store):
    store, owner, now = phone_store
    key, claim = approve_phone(store, owner)
    other_key, other_claim = approve_phone(store, owner)
    challenge = store.challenge(claim['device_id'], claim['host_id'])
    with pytest.raises(LinkError):
        store.challenge(claim['device_id'], 'another-host')
    with pytest.raises(LinkError):
        store.token(claim['device_id'], challenge['challenge_id'], sign(other_key, unb64(challenge['payload'])))
    with pytest.raises(LinkError):
        store.token(claim['device_id'], challenge['challenge_id'], sign(key, b'wrong nonce'))
    good = store.token(claim['device_id'], challenge['challenge_id'], sign(key, unb64(challenge['payload'])))
    with pytest.raises(LinkError):
        store.token(claim['device_id'], challenge['challenge_id'], sign(key, unb64(challenge['payload'])))
    another = issue(store, other_key, other_claim)
    store.revoke(claim['device_id'])
    assert store.verify_token(good['access_token']) is None
    reopened = DeviceLinkStore(Path(store.home), gateway_url=store.gateway_url, host_name=store.host_name)
    assert reopened.verify_token(good['access_token']) is None
    with pytest.raises(LinkError):
        reopened.challenge(claim['device_id'], claim['host_id'])
    assert store.verify_token(another['access_token']) is not None
    assert store.poll(claim['claim_id'], claim['claim_token'])['status'] == 'denied'
    with pytest.raises(LinkError):
        store.challenge(claim['device_id'], claim['host_id'])
    pending = store.challenge(other_claim['device_id'], other_claim['host_id'])
    now[0] += 60
    with pytest.raises(LinkError):
        store.token(other_claim['device_id'], pending['challenge_id'], sign(other_key, unb64(pending['payload'])))
    now[0] += 900
    assert store.verify_token(another['access_token']) is None


def test_concurrent_approval_and_challenge_redemption_issue_once(phone_store):
    store, owner, _ = phone_store
    key = ec.generate_private_key(ec.SECP256R1())
    body = claim_request(store.create_pairing(owner), key)
    claim = store.claim(body)
    def settle(_):
        try:
            return store.settle(claim['claim_id'], approve=True,
                key_fingerprint=fingerprint(body['device_public_key']), comparison=claim['comparison'])
        except LinkError:
            return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(settle, range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(store.list()['devices']) == 1
    challenge = store.challenge(claim['device_id'], claim['host_id'])
    signature = sign(key, unb64(challenge['payload']))
    def redeem(_):
        try:
            return store.token(claim['device_id'], challenge['challenge_id'], signature)
        except LinkError:
            return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(redeem, range(2)))
    assert sum(result is not None for result in results) == 1


def test_code_collision_cancel_wrong_claim_and_expiry_do_not_approve(phone_store, monkeypatch):
    store, owner, now = phone_store
    import hermes_cli.dashboard_auth.device_links_store as module
    with monkeypatch.context() as fixed:
        fixed.setattr(module.secrets, 'choice', lambda alphabet: 'A')
        pairing = store.create_pairing(owner)
        with pytest.raises(LinkError, match='code_collision'):
            store.create_pairing(owner)
    key = ec.generate_private_key(ec.SECP256R1())
    claim = store.claim(claim_request(pairing, key))
    with pytest.raises(LinkError):
        store.claim(claim_request(pairing, ec.generate_private_key(ec.SECP256R1())))
    store.cancel(pairing['pairing_id'])
    assert store.poll(claim['claim_id'], claim['claim_token'])['status'] == 'denied'
    with pytest.raises(LinkError):
        store.settle(claim['claim_id'], approve=True,
            key_fingerprint=fingerprint(public_wire(key.public_key())), comparison=claim['comparison'])
    pairing = store.create_pairing(owner)
    now[0] += 300
    with pytest.raises(LinkError):
        store.claim(claim_request(pairing, key))
    assert store.list()['devices'] == []


def test_wire_fixture_contains_verifiable_cross_language_signatures():
    fixture = json.loads((Path(__file__).resolve().parents[2] / 'docs/loki/phone-link-wire.json').read_text())
    claim = fixture['claim_request']
    assert b64(claim_payload(claim)) == fixture['claim_signed_bytes_base64url']
    verify(claim['device_public_key'], claim['signature'], claim_payload(claim))
    host = fixture['host_metadata_decoded']
    for signed in (fixture['claim_response']['host_metadata'], fixture['challenge_response']):
        verify(host['host_public_key'], signed['signature'], unb64(signed['payload']))
    verify(claim['device_public_key'], fixture['token_request']['signature'],
           unb64(fixture['challenge_response']['payload']))
