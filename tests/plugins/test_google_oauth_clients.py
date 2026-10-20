"""The patched OAuthLib keeps both retained Google client flows working offline."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
import requests


def test_revocation_client_refuses_jsonp_callback():
    """GHSA-hj66-6f7g-4r5v: callers cannot request executable JSONP output."""
    oauth2 = pytest.importorskip("oauthlib.oauth2", reason="Google optional extra")
    client = oauth2.WebApplicationClient("synthetic-client")

    with pytest.raises(TypeError, match="callback"):
        client.prepare_token_revocation_request(
            "https://oauth.example.invalid/revoke", "synthetic-token", callback="callback"
        )


@pytest.fixture(params=["chat", "workspace"])
def google_helper(request, tmp_path, monkeypatch):
    pytest.importorskip("google_auth_oauthlib.flow", reason="Google optional extra")
    monkeypatch.setenv("LOKI_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    if request.param == "chat":
        from plugins.platforms.google_chat import oauth as helper

        args = {"email": "synthetic@example.invalid"}
        client_path = helper._client_secret_path()
        pending_path = helper._pending_auth_path(args["email"])
        token_path = helper._token_path(args["email"])
    else:
        source = (
            Path(__file__).resolve().parents[2]
            / "skills/productivity/google-workspace/scripts/setup.py"
        )
        monkeypatch.syspath_prepend(str(source.parent))
        spec = importlib.util.spec_from_file_location("google_workspace_oauth_compat", source)
        assert spec is not None and spec.loader is not None
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        client_path = tmp_path / "client.json"
        pending_path = tmp_path / "pending.json"
        token_path = tmp_path / "token.json"
        for name, path in (
            ("CLIENT_SECRET_PATH", client_path),
            ("PENDING_AUTH_PATH", pending_path),
            ("TOKEN_PATH", token_path),
        ):
            monkeypatch.setattr(helper, name, path)
        args = {}

    # PM's install/restart boundary has separate coverage. Exercise the real
    # Google Flow -> requests-oauthlib -> OAuthLib stack already in this venv.
    monkeypatch.setattr(helper, "_ensure_deps", lambda: None)
    client_path.write_text(json.dumps({"installed": {
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
        "auth_uri": "https://accounts.example.invalid/auth",
        "token_uri": "https://oauth.example.invalid/token",
    }}))
    return helper, args, pending_path, token_path


@pytest.mark.parametrize("exchange_ok", [True, False], ids=["token", "invalid-grant"])
def test_google_helpers_preserve_pkce_state_and_granted_scopes(
    google_helper, exchange_ok, monkeypatch, capsys,
):
    helper, args, pending_path, token_path = google_helper
    sent = []
    granted_scope = helper.SCOPES[0]

    def send(_session, prepared, **_kwargs):
        # No socket is opened: only the HTTP transport is replaced.
        assert prepared.url == "https://oauth.example.invalid/token"
        assert prepared.method == "POST"
        assert prepared.headers["Authorization"].startswith("Basic ")
        sent.append(parse_qs(prepared.body))
        response = requests.Response()
        response.request = prepared
        response.url = prepared.url
        response.status_code = 200 if exchange_ok else 400
        response._content = json.dumps({
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": granted_scope,
        } if exchange_ok else {"error": "invalid_grant"}).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    helper.get_auth_url(**args)
    authorization = parse_qs(urlparse(capsys.readouterr().out.strip()).query)
    pending_bytes = pending_path.read_bytes()
    pending = json.loads(pending_bytes)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(pending["code_verifier"].encode()).digest()
    ).decode().rstrip("=")
    assert authorization["code_challenge"] == [expected_challenge]
    assert authorization["code_challenge_method"] == ["S256"]
    assert authorization["state"] == [pending["state"]]
    assert authorization["access_type"] == ["offline"]
    assert authorization["prompt"] == ["consent"]

    with pytest.raises(SystemExit) as invalid_state:
        helper.exchange_auth_code("http://localhost:1/?code=synthetic-code&state=wrong", **args)
    assert invalid_state.value.code == 1
    assert sent == []
    assert pending_path.read_bytes() == pending_bytes
    assert not token_path.exists()

    callback = "http://localhost:1/?" + urlencode({
        "code": "synthetic-code", "state": pending["state"], "scope": granted_scope,
    })
    if exchange_ok:
        helper.exchange_auth_code(callback, **args)
        saved = json.loads(token_path.read_text())
        assert saved["type"] == "authorized_user"
        assert saved["scopes"] == [granted_scope]
        assert saved["refresh_token"] == "synthetic-refresh"
        assert not pending_path.exists()
    else:
        with pytest.raises(SystemExit) as rejected:
            helper.exchange_auth_code(callback, **args)
        assert rejected.value.code == 1
        assert pending_path.read_bytes() == pending_bytes
        assert not token_path.exists()

    assert len(sent) == 1
    assert sent[0]["grant_type"] == ["authorization_code"]
    assert sent[0]["code"] == ["synthetic-code"]
    assert sent[0]["code_verifier"] == [pending["code_verifier"]]
    assert sent[0]["redirect_uri"] == [pending["redirect_uri"]]
