"""Exercise actual startup/refusal output without credentials or a model request."""

import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("reply", ["n", "no"])
def test_declining_first_run_names_the_installed_command(monkeypatch, capsys, reply):
    from hermes_cli import main, setup

    monkeypatch.setattr(setup, "is_interactive_stdin", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: reply)
    with pytest.raises(SystemExit) as exit_info:
        main._first_run_setup_guard(SimpleNamespace())
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "Loki isn't configured yet" in output
    assert "You can run 'loki setup' at any time to configure." in output
    assert "hermes setup" not in output


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_interrupted_first_run_retains_refusal_and_owned_remedy(monkeypatch, capsys, interruption):
    from hermes_cli import main, setup

    def interrupt(_prompt):
        raise interruption

    monkeypatch.setattr(setup, "is_interactive_stdin", lambda: True)
    monkeypatch.setattr("builtins.input", interrupt)
    with pytest.raises(SystemExit) as exit_info:
        main._first_run_setup_guard(SimpleNamespace())
    assert exit_info.value.code == 1
    assert "You can run 'loki setup'" in capsys.readouterr().out


@pytest.mark.parametrize("reply", ["", "y", "yes"])
def test_accepting_first_run_still_dispatches_setup(monkeypatch, capsys, reply):
    from hermes_cli import main, setup

    args = SimpleNamespace()
    calls = []
    monkeypatch.setattr(setup, "is_interactive_stdin", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: reply)
    monkeypatch.setattr(main, "cmd_setup", calls.append)
    main._first_run_setup_guard(args)
    assert calls == [args]
    assert "at any time" not in capsys.readouterr().out


def test_noninteractive_first_run_does_not_prompt_or_claim_ready(monkeypatch, capsys):
    from hermes_cli import main, setup

    monkeypatch.setattr(setup, "is_interactive_stdin", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("must not prompt"))
    with pytest.raises(SystemExit) as exit_info:
        main._first_run_setup_guard(SimpleNamespace())
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "loki setup" in output
    assert "No interactive TTY detected" in output
    assert "hermes setup" not in output


def test_tty_refusal_brands_command_without_rewriting_argument(monkeypatch, capsys):
    from hermes_cli import main

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as exit_info:
        main._require_tty("Hermes user command")
    assert exit_info.value.code == 1
    assert "'loki Hermes user command' requires an interactive terminal" in capsys.readouterr().err


def test_process_title_uses_loki_without_renaming_internal_modules(monkeypatch):
    from hermes_cli import main

    calls = []
    monkeypatch.setitem(sys.modules, "setproctitle", SimpleNamespace(setproctitle=calls.append))
    main._set_process_title()
    assert calls == ["loki"]
