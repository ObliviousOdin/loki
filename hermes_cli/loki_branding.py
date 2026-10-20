"""Presentation-only branding of inherited, developer-authored CLI help."""

import argparse
import re


class _LiteralHelp(str):
    """Already-authored Loki help with deliberate upstream or protocol references.

    Use this only for static copy, such as an explicit upstream credit or a
    compatibility description. Runtime values belong in argparse format fields.
    """


def literal_help(text: str) -> str:
    """Mark static copy whose upstream or protocol names are intentional."""
    return _LiteralHelp(text)


def cli_help(text: str) -> str:
    """Brand command documentation without changing identifiers or interpolated runtime data."""
    if isinstance(text, _LiteralHelp):
        return text
    text = re.sub(r"(?<![\w./-])Hermes Agent(?![\w/-]|\.\w)", "Loki", text)
    text = re.sub(r"(?<![\w./-])Hermes('s|')?(?![\w/-]|\.\w)",
                  lambda match: "Loki's" if match[1] else "Loki", text)
    text = re.sub(r"(?<![\w./-])hermes(?=\s|$|[`\"',;!?)]|[.:](?![\w<]))", "loki", text)
    text = re.sub(r"\bHERMES_([A-Z0-9_]+)\b", r"LOKI_\1", text)
    return text.replace("~/.hermes", "~/.loki")


def public_env_name(name: str) -> str:
    """Display built-in environment names before user/provider values are interpolated.

    The immutable declaration snapshot predates plugin/provider catalog injection.
    Custom names keep their exact spelling, including any Hermes-prefixed name.
    """
    from hermes_cli.config_defaults import BUILTIN_ENV_VAR_NAMES

    return cli_help(name) if name in BUILTIN_ENV_VAR_NAMES else name


def parser_help_templates(parser) -> None:
    """Brand the help tree before argparse inserts defaults or user values.

    Never adapt rendered help: action defaults, choices, metavar, parser prog,
    and custom format parameters can contain user paths or model identifiers.
    """
    seen = set()

    def visit(current):
        if id(current) in seen:
            return
        seen.add(id(current))
        for name in ("description", "epilog", "usage"):
            value = getattr(current, name, None)
            if isinstance(value, str):
                setattr(current, name, cli_help(value))
        for group in current._action_groups:
            for name in ("title", "description"):
                value = getattr(group, name, None)
                if isinstance(value, str):
                    setattr(group, name, cli_help(value))
        for action in current._actions:
            if isinstance(action.help, str):
                action.help = cli_help(action.help)
            if isinstance(action, argparse._SubParsersAction):
                for choice in action._choices_actions:
                    if isinstance(choice.help, str):
                        choice.help = cli_help(choice.help)
                for child in action.choices.values():
                    visit(child)

    visit(parser)
