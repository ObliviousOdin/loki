"""``hermes import`` subcommand parser."""

from __future__ import annotations

from typing import Callable

from hermes_cli.loki_branding import literal_help


def build_import_cmd_parser(subparsers, *, cmd_import: Callable) -> None:
    """Attach the ``import`` subcommand to ``subparsers``."""
    import_parser = subparsers.add_parser(
        "import", help=literal_help("Restore a Loki or Hermes backup from a zip file"),
        description=literal_help("Extract a previously created Loki or Hermes backup into your "
        "Loki home directory, restoring configuration, skills, "
        "sessions, and data"))
    import_parser.add_argument("zipfile", help="Path to the backup zip file")
    import_parser.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing files without confirmation")
    import_parser.set_defaults(func=cmd_import)
