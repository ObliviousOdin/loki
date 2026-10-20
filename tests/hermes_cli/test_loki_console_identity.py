"""Loki console commands keep arguments intact and retain legacy compatibility."""

import json
from types import SimpleNamespace

import pytest

from hermes_cli import console_engine, profiles


@pytest.mark.parametrize("prefix", ["loki ", "hermes ", ""])
def test_public_and_legacy_prefix_preserve_arguments(prefix):
    engine = console_engine.HermesConsoleEngine()
    engine.register(("inspect-value",), "inspect-value <value>", "Inspect a value",
                    lambda _engine, args: json.dumps(args))
    result = engine.execute(prefix + 'inspect-value "Hermes user value" NousResearch/Hermes-3')
    assert result.status == "ok"
    assert json.loads(result.output) == ["Hermes user value", "NousResearch/Hermes-3"]


@pytest.mark.parametrize("prefix", ["loki ", "hermes ", ""])
def test_prefix_does_not_bypass_console_shell_restrictions(prefix):
    result = console_engine.HermesConsoleEngine().execute(prefix + "sessions list ; echo secret")
    assert result.status == "error"
    assert "does not run shell syntax" in result.output


def test_console_parser_brands_authored_help_before_default_interpolation(monkeypatch, capsys):
    def register(parser):
        parser.description = "Inspect Hermes settings."
        parser.add_argument("--model", default="NousResearch/Hermes-3 with Hermes user value",
                            help="Hermes model (default: %(default)s)")
    monkeypatch.setattr(console_engine.importlib, "import_module",
                        lambda _name: SimpleNamespace(register=register))
    parser = console_engine._CliSurface("registered", "synthetic_cli", "register").build("inspect", live=False)
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["inspect", "--help"])
    assert exit_info.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert text.startswith("usage: loki inspect")
    assert "Inspect Loki settings." in text
    assert "Loki model (default: NousResearch/Hermes-3 with Hermes user value)" in text


@pytest.mark.parametrize("brand", ["loki", "hermes"])
def test_known_status_footer_is_removed_for_both_command_names(brand):
    output = f"State: ready\n--------\nRun '{brand} doctor' for details\nRun '{brand} setup' to configure\n"
    assert console_engine._strip_console_status_footer(output) == "State: ready"


def test_unrelated_or_mixed_footer_is_preserved():
    output = "State: ready\nRun 'loki doctor' for details\nRun 'hermes setup' to configure\n"
    assert console_engine._strip_console_status_footer(output) == output.rstrip()


@pytest.mark.parametrize("brand", ["loki", "hermes"])
def test_generated_command_summary_is_not_duplicated(brand):
    assert console_engine._clean_summary(f"Run `{brand} profile list`.") == ""
    assert console_engine._clean_summary("Run `Hermes user data`.") == "Run `Hermes user data`."


@pytest.mark.parametrize("name", ["loki", "Loki", "hermes"])
def test_primary_and_legacy_launcher_aliases_are_reserved_without_probing(monkeypatch, name):
    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("reserved names must not inspect installed commands")
    monkeypatch.setattr(profiles.subprocess, "run", unexpected_probe)
    assert profiles.check_alias_collision(name) == f"'{name.lower()}' is a reserved name"
