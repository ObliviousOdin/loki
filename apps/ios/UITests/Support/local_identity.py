"""Synthetic upstream identity provider for the isolated loopback UI gateway only."""
from dataclasses import replace
import html
import secrets
import time
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from hermes_cli.dashboard_auth.base import (
    DashboardAuthProvider, InvalidCodeError, LoginStart, RefreshExpiredError, Session,
)


class LocalIdentity(DashboardAuthProvider):
    name = 'loki-ui-test'
    display_name = 'Loki UI Test — local synthetic identity'

    def __init__(self):
        self.attempts, self.codes, self.tokens, self.refreshes = {}, {}, {}, {}

    def start_login(self, *, redirect_uri):
        state, verifier, attempt = (secrets.token_urlsafe(32) for _ in range(3))
        self.attempts[attempt] = (redirect_uri, state, verifier, time.time() + 300)
        origin = urlsplit(redirect_uri)
        url = f'{origin.scheme}://{origin.netloc}/auth/login/loki-ui-test?attempt={attempt}'
        return LoginStart(url, {'hermes_session_pkce': f'state={state};verifier={verifier}'})

    def complete_login(self, *, code, state, code_verifier, redirect_uri):
        pending = self.codes.pop(code, None)
        if pending is None:
            raise InvalidCodeError('Unknown test identity code')
        expected_uri, expected_state, expected_verifier, expires, user = pending
        if (time.time() >= expires or state != expected_state or code_verifier != expected_verifier
                or redirect_uri != expected_uri):
            raise InvalidCodeError('Test identity request does not match')
        return self._issue(user)

    def _issue(self, user):
        session = Session(user, f'{user}@example.test', 'Local UI Test User', 'test-only', self.name,
                          int(time.time()) + 3600, secrets.token_urlsafe(48), secrets.token_urlsafe(48))
        self.tokens[session.access_token] = session
        self.refreshes[session.refresh_token] = user
        return session

    def verify_session(self, *, access_token):
        session = self.tokens.get(access_token)
        return replace(session, refresh_token='') if session is not None and session.expires_at > time.time() else None

    def refresh_session(self, *, refresh_token):
        user = self.refreshes.pop(refresh_token, None)
        if user is None:
            raise RefreshExpiredError('Unknown test refresh token')
        return self._issue(user)

    def revoke_session(self, *, refresh_token):
        self.refreshes.pop(refresh_token, None)

    def install(self, app):
        router = APIRouter()

        @router.get('/auth/login/loki-ui-test', include_in_schema=False)
        async def identity_page(attempt: str):
            if attempt not in self.attempts or self.attempts[attempt][3] <= time.time():
                raise HTTPException(400, 'Restart test sign-in')
            target = html.escape('/auth/login/loki-ui-test/continue?' + urlencode({'attempt': attempt}))
            return HTMLResponse('<!doctype html><meta name="viewport" content="width=device-width">'
                '<title>Loki local UI test</title><main style="font:20px system-ui;padding:32px">'
                '<h1>Local UI test gateway</h1><p>This signs in a synthetic test user. '
                'No real identity, vendor account, or model is connected.</p>'
                f'<a id="continue-test-login" href="{target}">Continue as test user</a></main>',
                headers={'Cache-Control': 'no-store'})

        @router.get('/auth/login/loki-ui-test/continue', include_in_schema=False)
        async def complete(attempt: str, identity: str = 'primary'):
            pending = self.attempts.pop(attempt, None)
            if pending is None or pending[3] <= time.time() or identity not in {'primary', 'peer'}:
                raise HTTPException(400, 'Restart test sign-in')
            code = secrets.token_urlsafe(32)
            self.codes[code] = (*pending, f'loki-ui-test-{identity}')
            callback, state, _, _ = pending
            return RedirectResponse(callback + '?' + urlencode({'code': code, 'state': state}), status_code=302)
        # The dashboard's final SPA catch-all already exists when the support launcher imports it.
        app.router.routes[0:0] = router.routes
