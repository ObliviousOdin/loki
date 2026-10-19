"""Operator application roots protected before pytest creates any temporary files."""
from pathlib import Path
import os


def operator_default_state_roots():
    from hermes_state_guard import _real_platform_state_root

    candidates = [_real_platform_state_root(), Path.home() / ".loki", Path.home() / ".hermes"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend(Path(local) / name for name in ("loki", "hermes"))
    roots = []
    for candidate in candidates:
        if candidate is not None:
            try:
                roots.append(candidate.expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                continue
    return tuple(dict.fromkeys(roots))
