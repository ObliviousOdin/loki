"""HTTP ownership for the optional durable cron-create consumer."""
from fastapi import HTTPException


def creation_identity(request, request_id):
    if request_id is None:
        return None
    from gateway.session_identity import authenticated_subject
    from hermes_cli.dashboard_auth.base import Session
    session = getattr(getattr(request, 'state', None), 'session', None)
    if not isinstance(session, Session) or not session.user_id:
        raise HTTPException(status_code=403, detail={'reason': 'verified_session_required'})
    return {'request_id': request_id, 'principal_id': authenticated_subject({
        'provider': session.provider, 'issuer': session.issuer, 'user_id': session.user_id})}


def creation_error(exc):
    from cron.job_creation_receipts import CreationConflict
    if isinstance(exc, CreationConflict):
        status = 503 if exc.reason == 'creation_store_unavailable' else 409
        raise HTTPException(status_code=status, detail={'reason': exc.reason}) from exc
