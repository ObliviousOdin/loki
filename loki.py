"""Loki command entry points, retaining the upstream runtime architecture."""

from loki_identity import bind_loki_environment


def main() -> None:
    bind_loki_environment()
    from hermes_cli.main import main as run
    run()


def agent() -> None:
    bind_loki_environment()
    from agent.legacy_cli import main as run
    run()


def acp() -> None:
    bind_loki_environment()
    from acp_adapter.entry import main as run
    run()


if __name__ == "__main__":
    main()
