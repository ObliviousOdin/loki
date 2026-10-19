"""Loki presentation for bundled authored catalogs; custom layers are merged later."""

import re

from hermes_cli.loki_branding import cli_help


# Audited references keep their actual spelling. Format fields remain identifiers;
# runtime arguments never enter this boundary. The wake phrase names a real model.
_PROTECTED = re.compile(r"https?://[^\s<>\"']+|\{[^{}]*\}|Hey Hermes|hermes_tools", re.IGNORECASE)
_MODEL_NOTICE = re.compile(_PROTECTED.pattern + r"|Hermes [34]\b", re.IGNORECASE)
_MODEL_NOTICE_KEY = "cli.banner.hermes_models_not_agentic"


def _brand_literal(text: str) -> str:
    # Bundled translations include inflected and adjacent-script product names
    # (Hermesben, Hermes会…), outside argparse's conservative English boundaries.
    return (cli_help(text).replace("Hermes Agent", "Loki").replace("Hermes", "Loki")
            .replace("hermes", "loki").replace("HERMES", "LOKI"))


def _brand_template(key: str, text: str) -> str:
    protected = _MODEL_NOTICE if key == _MODEL_NOTICE_KEY else _PROTECTED
    pieces = []
    cursor = 0
    for match in protected.finditer(text):
        pieces.extend((_brand_literal(text[cursor:match.start()]), match[0]))
        cursor = match.end()
    pieces.append(_brand_literal(text[cursor:]))
    return "".join(pieces)


def brand_bundled_catalog(catalog: dict[str, str]) -> dict[str, str]:
    """Adapt only the bundled resource layer, before custom overlays/packs or formatting."""
    return {key: _brand_template(key, text) for key, text in catalog.items()}
