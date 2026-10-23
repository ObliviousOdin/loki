"""OS-native management, deliberately unavailable to ordinary dashboard/phone credentials."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from hermes_cli.dashboard_auth.device_links_crypto import LinkError
from hermes_cli.dashboard_auth.device_links_routes import Body, service

router = APIRouter(prefix='/api/device-links')


def _native(request, *, require_ready=True):
    grant = getattr(request.state, 'native_http_principal', None)
    if not grant or grant.get('purpose') != 'native-http' or grant.get('capabilities') != frozenset({'http:owner'}):
        raise HTTPException(403, 'os_local_required')
    result = service(request) if require_ready else getattr(request.app.state, 'device_links_service', None)
    from hermes_constants import get_hermes_home
    home = result.store.home if result else str(get_hermes_home().resolve())
    if grant.get('profile_id') != home:
        raise HTTPException(403, 'profile_scope_mismatch')
    return result


def _owner(request):
    from hermes_cli.dashboard_auth.cookies import read_session_cookies
    from hermes_cli.dashboard_auth.middleware import _verify_access_token
    from hermes_cli.dashboard_auth.request_utils import extract_bearer
    from hermes_cli.dashboard_auth.base import ProviderError
    token = extract_bearer(request) or read_session_cookies(request)[0]
    if not token:
        raise HTTPException(409, 'owner_sign_in_required')
    try:
        session = _verify_access_token(request, access_token=token, audit=False)
    except ProviderError:
        raise HTTPException(503, 'owner_sign_in_unavailable') from None
    if session is None or session.device_id:
        raise HTTPException(409, 'owner_sign_in_required')
    return session


def _operation(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except LinkError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get('')
def overview(request: Request):
    result = _native(request, require_ready=False)
    from hermes_cli.dashboard_auth.device_links_config import owner_authorize_base
    from hermes_cli.dashboard_auth.registry import list_login_providers
    owner = None
    try:
        session = _owner(request)
        owner = {'user_id': session.user_id, 'provider': session.provider, 'issuer': session.issuer}
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
    return {'enabled': bool(getattr(request.app.state, 'device_links_enabled', False)),
            'configured': result is not None, 'ready': bool(result and result.transport_ready),
            'transport_verified_at': result.transport_verified_at if result else None,
            'unavailable_reason': (None if result.transport_ready else result.transport_error or 'transport_unverified') if result else 'transport_missing',
            'owner_sign_in_required': owner is None, 'owner': owner,
            **(result.store.list() if result else {'host': None, 'pairings': [], 'claims': [], 'devices': []}),
            'owner_login': {'authorize_base_url': owner_authorize_base(request, result.store.gateway_url if result else ''),
                            'authorize_path': '/auth/native/authorize', 'token_path': '/auth/native/token',
                            'providers': [{'name': p.name, 'display_name': p.display_name,
                                           'supports_password': bool(p.supports_password)}
                                          for p in list_login_providers()]}}


@router.post('/pairings')
def create_pairing(request: Request, body: Body):
    result = _native(request)
    owner = _owner(request)
    try:
        result.verify_transport()
    except LinkError:
        raise HTTPException(503, 'transport_unavailable') from None
    pairing = _operation(result.store.create_pairing, owner)
    try:
        result.registration(pairing)
    except LinkError:
        result.store.cancel(pairing['pairing_id'])
        raise HTTPException(503, 'rendezvous_unavailable') from None
    return pairing


@router.delete('/pairings/{pairing_id}')
def cancel_pairing(request: Request, pairing_id: str):
    result = _native(request)
    _operation(result.store.cancel, pairing_id)
    try:
        result.cancellation(pairing_id)
    except LinkError:
        # Gateway cancellation already makes every public claim refuse; rendezvous expires.
        return {'cancelled': True, 'rendezvous_removed': False}
    return {'cancelled': True, 'rendezvous_removed': True}


class ApprovalBody(Body):
    key_fingerprint: str = Field(max_length=64)
    comparison: str = Field(max_length=16)


@router.post('/claims/{claim_id}/approve')
def approve(request: Request, claim_id: str, body: ApprovalBody):
    result = _native(request)
    return _operation(result.store.settle, claim_id, approve=True, **body.model_dump())


@router.post('/claims/{claim_id}/deny')
def deny(request: Request, claim_id: str, body: Body):
    result = _native(request)
    return _operation(result.store.settle, claim_id, approve=False)


@router.delete('/devices/{device_id}')
def revoke(request: Request, device_id: str):
    result = _native(request)
    _operation(result.store.revoke, device_id)
    from hermes_cli.dashboard_auth.device_links_live import revoke_channels
    revoke_channels(result.store, device_id)
    return {'revoked': True, 'device_id': device_id}
