"""The only unauthenticated phone bootstrap: bounded claims and key-proven renewal."""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from hermes_cli.dashboard_auth.device_links_crypto import LinkError

router = APIRouter()
_NO_STORE = {'Cache-Control': 'no-store'}
_lock = threading.Lock()
_rates: dict[tuple[str, str], tuple[int, int]] = {}


def service(request):
    result = getattr(request.app.state, 'device_links_service', None)
    runner = getattr(request.app.state, 'gateway_runner', None)
    descriptor = getattr(runner, 'session_runtime_descriptor', {})
    if result is None or descriptor.get('state') != 'ready' or getattr(runner, '_draining', True):
        raise HTTPException(503, 'device_links_not_ready')
    return result


def limit(request):
    """Per-socket-peer and process-wide budgets; no untrusted forwarded address parsing."""
    now = int(time.time()) // 60
    peer = request.client.host if request.client else ''
    socket_peer = request.scope.get('hermes.gateway_socket_peer')
    configured = getattr(request.app.state, 'device_links_service', None)
    proxy = (configured is not None and socket_peer and socket_peer[0] in ('127.0.0.1', '::1')
             and request.headers.getlist('origin') == [configured.store.gateway_url])
    peer_key, peer_maximum = (('proxy', configured.store.host_id), 600) if proxy else (('peer', peer), 60)
    with _lock:
        for key in [key for key, (window, _) in _rates.items() if window < now]:
            _rates.pop(key)
        if len(_rates) > 4096:
            raise HTTPException(429, 'rate_limited', headers={'Retry-After': '60'})
        for key, maximum in ((peer_key, peer_maximum), (('global', '*'), 600)):
            window, count = _rates.get(key, (now, 0))
            if window == now and count >= maximum:
                raise HTTPException(429, 'rate_limited', headers={'Retry-After': '60'})
            _rates[key] = (now, count + 1 if window == now else 1)


def invoke(request, operation, *args, **kwargs):
    limit(request)
    try:
        return getattr(service(request).store, operation)(*args, **kwargs)
    except LinkError:
        raise HTTPException(400, 'invalid_or_expired', headers=_NO_STORE) from None


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ClaimBody(Body):
    pairing_id: str = Field(max_length=128)
    code: str = Field(max_length=32)
    client_id: str = Field(max_length=32)
    device_name: str = Field(max_length=120)
    device_public_key: str = Field(max_length=128)
    nonce: str = Field(max_length=64)
    signature: str = Field(max_length=128)


class PollBody(Body):
    claim_id: str = Field(max_length=128)
    claim_token: str = Field(max_length=128)


class ChallengeBody(Body):
    device_id: str = Field(max_length=128)
    host_id: str = Field(max_length=128)


class TokenBody(Body):
    device_id: str = Field(max_length=128)
    challenge_id: str = Field(max_length=128)
    signature: str = Field(max_length=128)


@router.post('/auth/device/claims')
def claim(request: Request, body: ClaimBody):
    return invoke(request, 'claim', body.model_dump())


@router.post('/auth/device/poll')
def poll(request: Request, body: PollBody):
    return invoke(request, 'poll', body.claim_id, body.claim_token)


@router.post('/auth/device/challenge')
def challenge(request: Request, body: ChallengeBody):
    return invoke(request, 'challenge', body.device_id, body.host_id)


@router.post('/auth/device/token')
def token(request: Request, body: TokenBody):
    result = invoke(request, 'token', body.device_id, body.challenge_id, body.signature)
    from fastapi.responses import JSONResponse
    return JSONResponse(result, headers=_NO_STORE)


@router.get('/auth/device/status')
def status(request: Request):
    from fastapi.responses import JSONResponse
    store = service(request).store
    return JSONResponse({'ready': True, 'host_id': store.host_id, 'gateway_url': store.gateway_url}, headers=_NO_STORE)
