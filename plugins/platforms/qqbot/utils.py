"""QQBot shared utilities — User-Agent, HTTP helpers, config coercion."""

from __future__ import annotations

import platform
import sys
from typing import Any, Dict, List

from loki_identity import CLIENT_USER_AGENT, VERSION

from .constants import QQBOT_VERSION


def _get_hermes_version() -> str:
    """Return the Loki package version, retaining the internal helper name."""
    return VERSION


def build_user_agent() -> str:
    """``QQBotAdapter/<qqbot_version> (Python/<py_version>; <os>; Loki/<loki_version>)``."""
    v = sys.version_info
    return (f"QQBotAdapter/{QQBOT_VERSION} (Python/{v.major}.{v.minor}.{v.micro}; "
            f"{platform.system().lower()}; {CLIENT_USER_AGENT})")


def get_api_headers() -> dict[str, str]:
    """Standard QQBot API headers. ``q.qq.com`` requires ``Accept: application/json``
    — without it the server returns a JavaScript anti-bot challenge page."""
    return {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": build_user_agent()}


def coerce_list(value: Any) -> list[str]:
    """Coerce a comma-separated string / list / tuple / set / scalar into a trimmed string list."""
    if value is None:
        return []
    items = value.split(",") if isinstance(value, str) else value if isinstance(value, (list, tuple, set)) else [value]
    return [s for s in (str(item).strip() for item in items) if s]
