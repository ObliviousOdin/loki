"""Public config labels must not rename internal keys, injected providers or user data."""

import pytest

OWNED = "HERMES_EPHEMERAL_SYSTEM_PROMPT"
PUBLIC = "LOKI_EPHEMERAL_SYSTEM_PROMPT"
CUSTOM = "HERMES_USER_PROVIDER_KEY"


def test_public_name_uses_builtin_snapshot_not_mutable_plugin_catalog(monkeypatch):
    from hermes_cli import config_defaults
    from hermes_cli.loki_branding import public_env_name

    monkeypatch.setitem(config_defaults.OPTIONAL_ENV_VARS, CUSTOM, {"description": "Hermes Custom"})
    assert public_env_name(OWNED) == PUBLIC
    assert public_env_name(CUSTOM) == CUSTOM
    assert public_env_name("OPENAI_API_KEY") == "OPENAI_API_KEY"
    assert public_env_name("HERMES_HOME") == "HERMES_HOME"  # Not an optional credential declaration.


def _small_catalog(monkeypatch):
    from hermes_cli import config

    table = {OWNED: {"description": "Owned setting"}, CUSTOM: {"description": "Hermes Provider"}}
    monkeypatch.setattr(config, "OPTIONAL_ENV_VARS", table)
    monkeypatch.setattr(config, "REQUIRED_ENV_VARS", {})
    return config, table


def test_config_check_displays_public_names_but_probes_internal_and_custom_keys(monkeypatch, capsys):
    from hermes_cli import config_check_diagnostics

    config, _ = _small_catalog(monkeypatch)
    probes = []
    monkeypatch.setattr(config, "get_env_value", lambda name: probes.append(name) or ("set" if name == OWNED else None))
    monkeypatch.setattr(config, "check_config_version", lambda **_: (1, 1))
    monkeypatch.setattr(config, "get_missing_config_fields", list)
    monkeypatch.setattr(config, "read_raw_config_readonly", dict)
    monkeypatch.setattr(config_check_diagnostics, "config_check_diagnostics", lambda *_: [])
    config._cmd_config_check(None)
    output = capsys.readouterr().out
    assert f"✓ {PUBLIC}" in output and OWNED not in output
    assert CUSTOM in output
    assert probes == [OWNED, CUSTOM]


def test_missing_env_catalog_keeps_internal_contract(monkeypatch):
    config, table = _small_catalog(monkeypatch)
    monkeypatch.setattr(config, "get_env_value", lambda _: None)
    rows = config.get_missing_env_vars()
    assert [row["name"] for row in rows] == list(table)
    assert rows[1]["description"] == "Hermes Provider"


def test_setup_prompt_displays_owned_name_and_saves_original_key(monkeypatch, capsys):
    from hermes_cli import setup

    prompts, writes = [], []
    monkeypatch.setattr(setup, "prompt", lambda text, **_: prompts.append(text) or "synthetic-only")
    monkeypatch.setattr(setup, "save_env_value", lambda name, value: writes.append((name, value)))
    for name in (OWNED, CUSTOM):
        setup._prompt_and_save_env_var({"name": name}, "saved", "skipped")
    assert prompts == [f"  {PUBLIC}", f"  {CUSTOM}"]
    assert writes == [(OWNED, "synthetic-only"), (CUSTOM, "synthetic-only")]
    assert "saved" in capsys.readouterr().out


def test_optional_migration_displays_alias_but_keeps_result_and_write_key(monkeypatch, capsys):
    config, _ = _small_catalog(monkeypatch)
    monkeypatch.setattr(config, "ENV_VARS_BY_VERSION", {2: [OWNED, CUSTOM]})
    monkeypatch.setattr(config, "get_env_value", lambda _: None)
    offers, writes, prompts = [], [], []
    monkeypatch.setattr(config, "_offer_list", lambda heading, items, question: offers.extend(items) or True)
    monkeypatch.setattr(config, "line_input", lambda text: prompts.append(text) or "synthetic-only")
    monkeypatch.setattr(config, "save_env_value", lambda name, value: writes.append((name, value)))
    result = {"env_added": []}
    config._offer_new_optional_env_vars(1, 2, result)
    output = capsys.readouterr().out
    assert any(row.startswith(PUBLIC + " — ") for row in offers)
    assert any(row == CUSTOM + " — Hermes Provider" for row in offers)
    assert f"Saved {PUBLIC}" in output and f"Saved {OWNED}" not in output
    assert "Hermes Provider" in output
    assert result["env_added"] == sorted([OWNED, CUSTOM])
    assert [name for name, _ in writes] == result["env_added"]
    assert any(PUBLIC in text for text in prompts) and all(OWNED not in text for text in prompts)


def test_quick_setup_required_labels_preserve_source_records(monkeypatch, tmp_path, capsys):
    from hermes_cli import config, setup, setup_quick

    rows = [{"name": name, "description": "Hermes user description", "is_required": True} for name in (OWNED, CUSTOM)]
    monkeypatch.setattr(config, "get_missing_env_vars", lambda **_: rows)
    monkeypatch.setattr(config, "get_missing_config_fields", list)
    monkeypatch.setattr(config, "check_config_version", lambda: (1, 1))
    monkeypatch.setattr(setup, "prompt", lambda *_a, **_k: "")
    monkeypatch.setattr(setup, "_print_setup_summary", lambda *_: None)
    setup_quick._run_quick_setup({}, tmp_path)
    output = capsys.readouterr().out
    assert PUBLIC in output and OWNED not in output
    assert CUSTOM in output and "Hermes user description" in output
    assert [row["name"] for row in rows] == [OWNED, CUSTOM]


def test_config_show_reports_actual_legacy_file_spelling_without_rewriting_value(monkeypatch, capsys):
    from hermes_cli import config, config_show

    monkeypatch.setattr(config, "load_env", lambda: {"HERMES_MAX_ITERATIONS": "Hermes custom value"})
    config_show._show_model_section({"agent": {"max_turns": 7}})
    output = capsys.readouterr().out
    assert "HERMES_MAX_ITERATIONS=Hermes custom value" in output
    assert "loki doctor --fix" in output


@pytest.mark.parametrize("public_value", ["owned synthetic setting", "Hermes user value"])
def test_displayed_public_name_binds_for_fresh_shell_without_adopting_hermes(public_value):
    from loki_identity import bind_loki_environment

    env = {OWNED: "foreign synthetic setting", PUBLIC: public_value}
    bind_loki_environment(env)
    assert env[OWNED] == public_value
