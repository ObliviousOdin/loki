"""Owned filesystem identities for browser-harness subprocesses."""

import hashlib
import os
import stat
from pathlib import Path

from hermes_constants import get_hermes_home


def harness_subprocess_env(env: dict) -> dict:
    """Namespace driver state by Loki profile and session before every CLI launch."""
    from tools.browser_tool import _socket_safe_tmpdir

    home = get_hermes_home() / "cache" / "browser-harness"
    name = str(env.get("BU_NAME") or "default")
    identity = hashlib.sha256(f"{home}\0{name}".encode()).hexdigest()[:16]
    runtime = Path(_socket_safe_tmpdir()) / f"bh-{identity}"
    runtime.mkdir(mode=0o700, exist_ok=True)
    info = runtime.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())):
        raise RuntimeError(f"Refusing unowned Loki browser harness runtime: {runtime}")
    if os.name != "nt":
        runtime.chmod(0o700)
    return {
        **env,
        "BH_HOME": str(home), "BROWSER_HARNESS_HOME": str(home),
        "BH_CONFIG_DIR": str(home / "config"),
        "BH_RUNTIME_DIR": str(runtime), "BH_RUNTIME_DIR_SHARED": "0",
        "BH_TMP_DIR": str(home / "tmp"), "BH_TMP_DIR_SHARED": "1",
        "BH_AGENT_WORKSPACE": env.get("BH_AGENT_WORKSPACE") or str(home / "workspace"),
    }
