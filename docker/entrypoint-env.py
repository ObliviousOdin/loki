"""Bind image/public overrides before s6 or shell bootstrap reads internal state."""

import os
import sys
from pathlib import Path


def bind_and_exec(command: list[str]) -> None:
    """Use the same fresh boundary for normal and legacy image startup."""
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from loki_identity import ENV_BOUND, bind_loki_environment

    # An image entry is a fresh boundary, never an already-bound profile child.
    os.environ.pop(ENV_BOUND, None)
    bind_loki_environment()
    os.execv(command[0], command)


def main() -> None:
    dispatcher = str(Path(__file__).resolve().with_name("entrypoint-dispatch.sh"))
    bind_and_exec([dispatcher, *sys.argv[1:]])


if __name__ == "__main__":
    main()
