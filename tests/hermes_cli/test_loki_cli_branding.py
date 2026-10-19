"""Inherited CLI documentation uses Loki while provider identifiers stay intact."""

import argparse

import pytest

from hermes_cli.loki_branding import cli_help, literal_help, parser_help_templates


def test_help_brands_commands_and_paths_but_preserves_model_identifiers():
    assert cli_help("Hermes Agent: hermes resume --home HERMES_HOME (~/.hermes)") == (
        "Loki: loki resume --home LOKI_HOME (~/.loki)")
    model = "NousResearch/Hermes-3-Llama-3.1-8B"
    assert cli_help(f"Select {model} via hermes model") == f"Select {model} via loki model"


def test_nested_argparse_help_uses_the_same_presentation_boundary():
    from hermes_cli._parser import HermesArgumentParser

    parser = HermesArgumentParser(prog="loki", description="Hermes Agent")
    subs = parser.add_subparsers()
    child = subs.add_parser("resume", description="Use hermes sessions list to find a session.")
    assert "Loki" in parser.format_help()
    assert "loki sessions list" in child.format_help()
    assert "hermes sessions" not in child.format_help()
    child.add_argument("--label", default="Hermes Agent", help="Display label: %(default)s")
    assert "Display label: Hermes Agent" in child.format_help()


def test_template_adapter_recurses_through_plain_parsers_without_rewriting_values():
    parser = argparse.ArgumentParser(prog="loki", description="Hermes CLI")
    nested = parser.add_subparsers().add_parser("mcp", help="Run Hermes as an MCP server")
    child = nested.add_subparsers().add_parser("serve", description="Run Hermes.")
    child.add_argument("--model", default="NousResearch/Hermes-3-Llama-3.1-8B",
                       help="Hermes model: %(default)s")
    child.add_argument("--label", default="Hermes Agent HERMES_HOME ~/.hermes 100%",
                       help="Display label: %(default)s")
    group = child.add_argument_group("Hermes settings", "Hermes' configuration")
    group.add_argument("--token", choices=["Hermes", "HERMES_HOME"],
                       help="Hermes credential (choices: %(choices)s)")
    parser_help_templates(parser)
    assert parser.description == "Loki CLI"
    assert "Run Loki as an MCP server" in parser.format_help()
    help_text = child.format_help()
    assert "Run Loki." in help_text
    assert "Loki settings" in help_text and "Loki's configuration" in help_text
    assert "Loki model: NousResearch/Hermes-3-Llama-3.1-8B" in help_text
    assert "Display label: Hermes Agent HERMES_HOME ~/.hermes 100%" in help_text
    assert "choices: Hermes, HERMES_HOME" in help_text
    assert child.parse_args(["--model", "Hermes", "--label", "Hermes Agent"]).model == "Hermes"


def test_explicit_upstream_credit_and_protocol_copy_are_preserved():
    credit = literal_help("Based on Hermes Agent by Nous Research")
    assert cli_help(credit) == credit
    assert cli_help(cli_help(credit)) == credit
    parser = argparse.ArgumentParser(description=credit)
    parser_help_templates(parser)
    assert credit in parser.format_help()
    assert cli_help("Hermes uses hermes_cli, hermes-gateway.service and api_server.") == (
        "Loki uses hermes_cli, hermes-gateway.service and api_server.")
    assert cli_help('Use `hermes`, "hermes", or hermes; python -m hermes_cli stays literal. hermes.') == (
        'Use `loki`, "loki", or loki; python -m hermes_cli stays literal. loki.')


@pytest.mark.parametrize("chat", [False, True], ids=["top-level", "chat"])
def test_actual_config_path_is_inserted_after_template_branding(monkeypatch, capsys, chat):
    from hermes_cli import _parser

    path = "/work/My Hermes Agent/Hermes/HERMES_HOME/~/.hermes/config 100%.yaml"
    monkeypatch.setattr(_parser, "_cfg_path", lambda: path)
    parser, _, _ = _parser.build_top_level_parser()
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args((["chat"] if chat else []) + ["--help"])
    assert exit_info.value.code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert f"Ignore {path} and fall back to built-in defaults" in output
    assert "LOKI_ACCEPT_HOOKS" in output
    assert "HERMES_ACCEPT_HOOKS" not in output


@pytest.fixture(scope="module")
def actual_parser():
    from hermes_cli.main import _build_cli_parser

    return _build_cli_parser()[0]


@pytest.mark.parametrize(("command", "expected"), [
    ([], "Loki - AI assistant"),
    (["backup"], "entire Loki configuration"),
    (["import"], "Loki-compatible backup into your Loki home directory"),
    (["import-agent"], "another coding agent's setup into Loki"),
    (["console"], "curated Loki command REPL"),
    (["mcp"], "run Loki as an MCP server"),
    (["mcp", "serve"], "loki mcp serve"),
    (["profile"], "loki profile"),
    (["serve"], "Loki backend server"),
    (["logs"], "loki logs --level WARNING"),
    (["peer"], "compatible agent gateways"),
    (["gui"], "LOKI_DESKTOP_HERMES_ROOT"),
    (["model"], "auth.oauth_clients.nous.client_id"),
    (["verify"], ".loki/environment.json"),
    (["gateway", "migrate-legacy"], "other agent services"),
    (["migrate", "relay"], "LOKI_NEMO_RELAY_PLUGINS_TOML"),
])
def test_actual_recursive_help_uses_loki(actual_parser, capsys, command, expected):
    with pytest.raises(SystemExit) as exit_info:
        actual_parser.parse_args(command + ["--help"])
    assert exit_info.value.code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert expected in output
    if command in (["import"], ["peer"], ["gateway", "migrate-legacy"]):
        assert "Hermes" not in output and "Fabric" not in output
    if command == ["gateway", "migrate-legacy"]:
        assert "loki-agent.service" in output.replace("- ", "-")
        assert "hermes.service" not in output
    if command == ["peer"]:
        assert "api_server" in output and "API_SERVER_KEY" in output
        assert "~/.loki/.env" in output
    if command == ["model"]:
        assert "default: hermes-cli" not in output
    if command == ["backup"]:
        assert "loki-backup-*.zip" in output
        assert "<Loki home>/backups/loki-backup-<timestamp>.zip" in output.replace("- ", "-")
        assert "hermes-backup-" not in output


@pytest.mark.parametrize("flag", ["--loki-root", "--hermes-root"])
def test_desktop_root_flag_keeps_compatibility_and_literal_user_path(actual_parser, flag):
    path = "/workspace/My Hermes Agent/Hermes"
    args = actual_parser.parse_args(["desktop", flag, path])
    assert args.hermes_root == path


def test_legacy_protocols_and_model_filter_examples_remain_literal(actual_parser, capsys):
    for command, literal in [
        (["update"], "hermes:<subcommand>"),
        (["sessions", "prune"], "'hermes'"),
        (["migrate"], "HERMES_NEMO_RELAY_ATIF_*/ATOF_*"),
    ]:
        with pytest.raises(SystemExit) as exit_info:
            actual_parser.parse_args(command + ["--help"])
        assert exit_info.value.code == 0
        assert literal in " ".join(capsys.readouterr().out.split())


def test_help_tree_preserves_real_model_provider_and_user_values(actual_parser):
    model = "NousResearch/Hermes-3-Llama-3.1-8B"
    actual_parser.format_help()
    args = actual_parser.parse_args(["--model", model, "--provider", "custom", "chat", "-q", "Hermes Agent"])
    assert (args.model, args.provider, args.query) == (model, "custom", "Hermes Agent")


@pytest.mark.parametrize("chat", [False, True], ids=["top-level", "chat"])
def test_real_process_home_name_is_not_rebranded_in_help(monkeypatch, capsys, tmp_path, chat):
    from hermes_cli import _parser

    home = tmp_path / "My Hermes Agent" / "Hermes" / "HERMES_HOME" / "100%"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("COLUMNS", "512")
    expected = _parser._cfg_path()
    parser = _parser.build_top_level_parser()[0]
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args((["chat"] if chat else []) + ["--help"])
    assert exit_info.value.code == 0
    assert expected in capsys.readouterr().out
    assert expected.endswith("/My Hermes Agent/Hermes/HERMES_HOME/100%/config.yaml")


def test_noninteractive_setup_names_loki_and_its_commands(capsys):
    from hermes_cli.setup import print_noninteractive_setup_guidance

    print_noninteractive_setup_guidance("a terminal is required")
    output = capsys.readouterr().out
    assert "Loki Setup" in output
    assert "loki config set model.provider custom" in output
    assert "Hermes" not in output


def test_source_version_distinguishes_loki_from_the_pinned_upstream(tmp_path, monkeypatch):
    from hermes_cli import banner, config, steward
    from hermes_cli.version_info import VersionInfo

    monkeypatch.setattr(config, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(steward, "read_install_stamp", lambda _root: {})
    monkeypatch.setattr(banner, "get_version_info", lambda: VersionInfo(
        "0.1.0a1", "0.1.0a1", 0, "c" * 40, "main", "git", dirty=True))
    label = banner.format_banner_version_label()
    assert "Loki v0.1.0a1" in label
    assert "Loki cccccccc" in label
    assert "baseline 18c525b6" in label
    assert "Hermes" not in label
    assert "+?" not in label


def test_banner_recovery_commands_use_loki_and_preserve_server_names():
    from hermes_cli.banner import _banner_left_lines, _mcp_failed_line

    line = _mcp_failed_line("Hermes", "stdio", "401 unauthorized")
    assert "loki mcp login Hermes" in line
    assert "loki mcp test Hermes" in _mcp_failed_line("Hermes", "stdio", "connection failed")
    lines = _banner_left_lines("unknown", "/workspace", None, None, None,
                               accent="blue", dim="grey")
    assert any("run /model or loki setup" in line for line in lines)


def test_preserved_upstream_tags_never_become_loki_release_links(tmp_path, monkeypatch):
    from hermes_cli import banner, source_check

    tag = "v0.22.2"
    project = "hermes-agent"

    def read(args, **_kwargs):
        if args == ["describe", "--tags", "--abbrev=0"]:
            return tag
        assert args == ["show", f"{tag}:pyproject.toml"]
        return f'[project]\nname = "{project}"\n'

    monkeypatch.setattr(source_check, "_git_stdout", read)
    monkeypatch.setattr(banner, "_latest_release_cache", None)
    assert banner.get_latest_release_tag(tmp_path) is None
    project, tag = "obliviousodin-loki-agent", "v0.1.0-alpha.1"
    monkeypatch.setattr(banner, "_latest_release_cache", None)
    assert banner.get_latest_release_tag(tmp_path) == (
        tag, f"https://github.com/ObliviousOdin/loki/releases/tag/{tag}")
