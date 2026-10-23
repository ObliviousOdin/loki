"""Operator-registered native callbacks; desktop loopback policy stays separate."""
import re
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException

_CLIENT_ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')
_CHALLENGE = re.compile(r'[A-Za-z0-9_-]{43}')
_STATE = re.compile(r'[A-Za-z0-9._~-]{32,512}')
_APP_SCHEME = re.compile(r'[a-z][a-z0-9+.-]*\.[a-z0-9+.-]+')


def _canonical_callback(raw):
    """An exact registered return with no caller-owned query or parser ambiguity."""
    if (not isinstance(raw, str) or not raw.isascii() or '\\' in raw or '%' in raw
            or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in raw)):
        return False
    try:
        parsed = urlparse(raw)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        return False
    if (not host or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or '?' in raw or '#' in raw or parsed.params or not parsed.path.startswith('/')
            or any(part in {'.', '..'} for part in parsed.path.split('/'))):
        return False
    if parsed.scheme != 'https' and not _APP_SCHEME.fullmatch(parsed.scheme):
        return False
    if parsed.scheme != 'https' and port is not None:
        return False
    authority = f'[{host}]' if ':' in host else host
    authority += f':{port}' if port is not None else ''
    return parsed.netloc == authority and urlunparse(parsed) == raw


def registered_native_clients():
    """Read the selected gateway's YAML; invalid registrations never become a redirect wildcard."""
    from hermes_cli.config import cfg_get, load_config_readonly
    configured = cfg_get(load_config_readonly(), 'dashboard', 'native_auth', 'clients', default={})
    if not isinstance(configured, dict):
        return {}
    clients = {}
    for client_id, registration in configured.items():
        if (not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id)
                or not isinstance(registration, dict)):
            continue
        callbacks = registration.get('redirect_uris')
        if isinstance(callbacks, list) and callbacks and all(_canonical_callback(uri) for uri in callbacks):
            clients[client_id] = tuple(callbacks)
    return clients


def validate_registered_redirect(client_id, redirect_uri, *, code_challenge, state):
    """Registered public clients use an exact callback plus S256 and an unpredictable client state."""
    if (not _canonical_callback(redirect_uri)
            or redirect_uri not in registered_native_clients().get(client_id, ())):
        raise HTTPException(status_code=400, detail='Native client or callback is not registered.')
    if not _CHALLENGE.fullmatch(code_challenge) or not _STATE.fullmatch(state):
        raise HTTPException(status_code=400, detail='Native client requires an S256 challenge and fresh state.')
    return redirect_uri
