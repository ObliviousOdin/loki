"""Bounded Home Assistant REST calls with no redirects, proxies, or write retries."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ENTITY = re.compile(r"^(light|switch)\.[a-z0-9_]+$")


class HomeError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Settings:
    url: str
    entities: tuple[str, ...]
    control: bool


def settings(ctx) -> Settings:
    raw = ctx.get_config("url", "")
    entities = ctx.get_config("allowed_entities", [])
    control = ctx.get_config("allow_control", False)
    if not isinstance(raw, str) or not isinstance(entities, list) or type(control) is not bool:
        raise HomeError("invalid_configuration", "Check the address, entity list, and control setting.")
    if len(entities) > 50 or any(not isinstance(e, str) or not ENTITY.fullmatch(e) for e in entities):
        raise HomeError("invalid_configuration", "Allow up to 50 exact light.* or switch.* entity IDs.")
    url = raw.strip().rstrip("/")
    if url:
        try:
            parsed = urlsplit(url)
            port = parsed.port
            host = parsed.hostname or ""
            local = host == "localhost" or host.endswith(".local")
            try:
                address = ipaddress.ip_address(host)
                local = address.is_private or address.is_loopback
            except ValueError:
                pass
            if (parsed.scheme not in ("http", "https") or not host or parsed.username is not None
                    or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                    or (parsed.scheme == "http" and not local) or port == 0
                    or any(c.isspace() or ord(c) < 32 for c in url)):
                raise ValueError
        except ValueError:
            raise HomeError("invalid_configuration", "Use an HTTPS base URL or a local HTTP base URL without credentials or a path.") from None
    return Settings(url, tuple(dict.fromkeys(entities)), control)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, config: Settings, token: str):
        self.config = config
        self.token = token

    def request(self, path: str, *, body: dict | None = None):
        method = "POST" if body is not None else "GET"
        request = Request(self.config.url + "/api/" + path, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
                data = response.read(131073)
            if len(data) > 131072:
                raise ValueError
            return json.loads(data)
        except HTTPError as exc:
            status = "authentication_required" if exc.code in (401, 403) else "error"
            if body is not None and exc.code >= 500:
                status = "outcome_unknown"
            if exc.code == 404:
                status = "unavailable"
            raise HomeError(status, "Home Assistant rejected the request. Check access and the entity ID.") from None
        except (URLError, TimeoutError, OSError):
            status = "outcome_unknown" if body is not None else "offline"
            raise HomeError(status, "No response from Home Assistant. Do not retry a device change automatically.") from None
        except (ValueError, TypeError):
            status = "outcome_unknown" if body is not None else "error"
            raise HomeError(status, "Home Assistant returned an unexpected response.") from None

    def state(self, entity: str) -> dict:
        row = self.request("states/" + entity)
        if not isinstance(row, dict) or row.get("entity_id") != entity or not isinstance(row.get("state"), str):
            raise HomeError("error", "Home Assistant returned an unexpected entity response.")
        attrs = row.get("attributes")
        name = attrs.get("friendly_name", entity) if isinstance(attrs, dict) else entity
        return {"entity_id": entity, "name": str(name)[:150], "state": row["state"][:100]}
