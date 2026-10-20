"""Loki's public identity and first-entry environment boundary (stdlib only).

Hermes module names and process-local environment seams remain internal APIs.
Only an explicit Loki launch may translate public ``LOKI_*`` overrides into them.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import TypeVar

PRODUCT_NAME = "Loki"
COMMAND = "loki"
DISTRIBUTION = "obliviousodin-loki-agent"
VERSION = "0.1.0a2"
UPSTREAM_COMMIT = "18c525b669b6ea4ba62e6967d228af21d89aa9d3"
# get_version_info().base_version at the exact upstream pin; independent of Loki releases.
UPSTREAM_SDK_VERSION = "0.22.2"
REPOSITORY = "ObliviousOdin/loki"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
CLIENT_USER_AGENT = f"Loki/{VERSION}"
ENV_BOUND = "__LOKI_ENV_BOUND"
_EnvValue = TypeVar("_EnvValue")


def with_loki_aliases(values: Mapping[str, _EnvValue]) -> dict[str, _EnvValue]:
    """Bridge one explicit config layer; public Loki values take precedence in that layer.

    This never reads process state or rebinds an already selected profile/runtime.
    Keeping both names lets scoped reads and launch-residue scrubbing share provenance.
    """
    return {**values, **{"HERMES_" + key.removeprefix("LOKI_"): value
                       for key, value in values.items() if key.startswith("LOKI_")}}


def default_home(environ: MutableMapping[str, str] | None = None) -> Path:
    """The owned platform directory; never probes or migrates Hermes/Fabric data."""
    env = os.environ if environ is None else environ
    suffix = env.get("LOKI_DATA_DIR_SUFFIX", "")
    if sys.platform == "win32":
        base = env.get("LOCALAPPDATA", "").strip()
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / ("loki" + suffix)
    return Path.home() / (".loki" + suffix)


def bind_loki_environment(environ: MutableMapping[str, str] | None = None) -> None:
    """Bind a fresh process to Loki; children retain their owning profile/runtime.

    The marker is inherited by Loki workers so their internal profile bindings survive
    a second bootstrap. A fresh shell's Hermes activation, home, runtime and secrets
    cannot select Loki's state or dependency store.
    """
    env = os.environ if environ is None else environ
    if env.get(ENV_BOUND) == "1":
        return
    overrides = {key.removeprefix("LOKI_"): value for key, value in list(env.items())
                 if key.startswith("LOKI_")}
    for key in list(env):
        if key.startswith(("HERMES_", "__HERMES_")):
            del env[key]
    for suffix, value in overrides.items():
        env["HERMES_" + suffix] = value
    env["HERMES_HOME"] = env.get("HERMES_HOME", "").strip() or str(default_home(env))
    env[ENV_BOUND] = "1"
