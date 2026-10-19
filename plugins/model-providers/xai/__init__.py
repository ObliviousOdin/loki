"""xAI (Grok) provider profile."""

from hermes_cli.version_info import get_version_info as get_version_info
from loki_identity import CLIENT_USER_AGENT
from providers import register_provider
from providers.base import ProviderProfile

xai = ProviderProfile(
    name="xai", aliases=("grok", "x-ai", "x.ai"), api_mode="codex_responses", env_vars=("XAI_API_KEY",),
    base_url="https://api.x.ai/v1", auth_type="api_key",
    default_headers={"User-Agent": CLIENT_USER_AGENT},
)

register_provider(xai)
