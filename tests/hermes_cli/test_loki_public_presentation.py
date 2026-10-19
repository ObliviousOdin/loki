"""Default product copy changes while exact stock migrations and custom identities survive."""

from types import SimpleNamespace

import pytest

from hermes_cli.config import _ensure_default_soul_md
from hermes_cli.default_soul import DEFAULT_SOUL_MD


_PREVIOUS_LOKI_SOUL = (
    "You are Loki, an independent personal AI agent based on Hermes Agent by Nous Research. Be direct: "
    "match the length of your reply to the weight of the ask — a one-line question gets a one-line "
    "answer, and finished work gets a short report of what changed, what's verified, and what's left, "
    "never a replay of the process. No filler (\"Great question,\" \"I'd be happy to\"), no restating the "
    "request back, no re-summarizing what you already said, no narrating tool calls the user can see. "
    "Plain claims over adjectives; when unsure, say so plainly. Agree because it's right, not because "
    "the user said it. Depth is earned — give it when the user asks for detail, teaches, or the stakes "
    "demand it, not by default."
)


@pytest.mark.parametrize("ascii_dash", [False, True])
@pytest.mark.parametrize("customized", [False, True])
def test_previous_loki_stock_soul_migrates_without_rewriting_custom_text(tmp_path, ascii_dash, customized):
    original = _PREVIOUS_LOKI_SOUL.replace("—", "--") if ascii_dash else _PREVIOUS_LOKI_SOUL
    if customized:
        original += "\nMy custom Hermes persona stays exactly as authored."
    soul = tmp_path / "SOUL.md"
    soul.write_text(original, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert soul.read_text(encoding="utf-8") == (original if customized else DEFAULT_SOUL_MD)
    if not customized:
        assert DEFAULT_SOUL_MD.startswith("You are Loki, a personal AI agent.")
        assert "Hermes" not in DEFAULT_SOUL_MD


def test_prompt_help_identifies_loki_and_retains_explicit_upstream_reference_guidance():
    from agent.prompt_builder import HERMES_AGENT_HELP_GUIDANCE, HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS

    for guidance in (HERMES_AGENT_HELP_GUIDANCE, HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS):
        assert guidance.startswith("You run on Loki. ")
        assert "LOKI_*" in guidance
        assert "never run upstream installers" in guidance.lower()
    assert "skill_view(name='hermes-agent')" in HERMES_AGENT_HELP_GUIDANCE
    assert "skill_view(" not in HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS


@pytest.mark.parametrize("width", [25, 90])
@pytest.mark.parametrize("skin_name,custom_name", [("default", None), ("custom", None), ("custom", "Hermes custom")])
def test_compact_banner_uses_loki_defaults_and_preserves_custom_names(monkeypatch, width, skin_name, custom_name):
    from hermes_cli import cli_render

    skin = SimpleNamespace(name=skin_name, get_color=lambda _key, default: default,
                           get_branding=lambda _key, default: custom_name or default)
    monkeypatch.setattr("hermes_cli.skin_engine.get_active_skin", lambda: skin)
    monkeypatch.setattr(cli_render.shutil, "get_terminal_size", lambda: SimpleNamespace(columns=width))
    monkeypatch.setattr(cli_render, "format_banner_version_label", lambda: "Loki vtest")
    monkeypatch.delenv("HERMES_FAST_STARTUP_BANNER", raising=False)

    banner = cli_render._build_compact_banner()

    assert (custom_name or "Loki") in banner
    assert "Nous" not in banner and "NOUS" not in banner
    if custom_name is None:
        assert "Hermes" not in banner and "HERMES" not in banner


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("custom_name", [None, "Hermes custom"])
def test_suspend_notice_uses_loki_fallback_and_preserves_custom_name(monkeypatch, custom_name):
    from hermes_cli.cli_tui_mixin import CLITuiMixin

    writes = []
    signals = []
    skin = SimpleNamespace(get_branding=lambda _key, default: custom_name or default)
    monkeypatch.setattr("hermes_cli.skin_engine.get_active_skin", lambda: skin)
    monkeypatch.setattr("prompt_toolkit.application.run_in_terminal", lambda fn: fn())
    monkeypatch.setattr("hermes_cli.cli_tui_mixin.os.write", lambda _fd, data: writes.append(data.decode()))
    monkeypatch.setattr("hermes_cli.cli_tui_mixin.os.kill", lambda pid, sig: signals.append((pid, sig)))

    CLITuiMixin._tui_handle_ctrl_z(None, SimpleNamespace())

    assert (custom_name or "Loki") in "".join(writes)
    assert len(signals) == 1 and signals[0][0] == 0
