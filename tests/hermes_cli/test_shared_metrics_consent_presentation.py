"""Classic CLI telemetry consent names Loki and distinguishes consent from transmission."""

import pytest


def test_first_offer_defaults_off_and_explains_the_missing_collector(monkeypatch, capsys):
    from hermes_cli.config import read_raw_config
    from hermes_cli.observability import shared_metrics_consent as consent
    from hermes_cli.observability.shared_metrics_send_config import resolve_send_config

    shown = {}

    def press_enter(question, choices, **kwargs):
        shown.update(question=question, choices=choices, **kwargs)
        return kwargs["selected"]

    monkeypatch.setattr("hermes_cli.curses_ui.curses_radiolist", press_enter)
    monkeypatch.setattr("hermes_cli.curses_ui.flush_stdin", lambda: None)

    assert consent.offer_consent() is True

    assert shown["question"] == "Help improve Loki?"
    assert shown["choices"][shown["selected"]] == "No thanks"
    assert "configured collector" in shown["choices"][0]
    assert "no default collector" in shown["description"]
    assert "https://github.com/ObliviousOdin/loki/" in shown["description"]
    assert "Nous" not in shown["description"]
    assert "hermes setup" not in shown["description"]
    state = consent.consent_state(read_raw_config())
    assert state == {"enabled": False, "send": False, "decided": True, "reask": False}
    assert resolve_send_config(read_raw_config()).send is False
    assert "loki setup telemetry" in capsys.readouterr().out


@pytest.mark.parametrize("choice,reask", [(0, False), (1, False), (-1, False), (-1, True)])
def test_offer_outcomes_use_loki_and_never_claim_an_upload(monkeypatch, capsys, choice, reask):
    from hermes_cli.config import read_raw_config
    from hermes_cli.observability import shared_metrics_consent as consent
    from hermes_cli.observability.shared_metrics_send_config import resolve_send_config

    monkeypatch.setattr("hermes_cli.curses_ui.curses_radiolist", lambda *args, **kwargs: choice)
    monkeypatch.setattr("hermes_cli.curses_ui.flush_stdin", lambda: None)

    answered = consent.offer_consent(reask=reask)

    output = capsys.readouterr().out
    assert "loki setup telemetry" in output
    assert "Hermes" not in output
    assert "Nous" not in output
    assert answered is (choice >= 0 or reask)
    assert resolve_send_config(read_raw_config()).send is False
    if choice == 0:
        assert consent.consent_state(read_raw_config())["send"] is True
        assert "consent saved" in output
        assert "configured collector is required" in output


def test_setup_telemetry_explains_upload_consent_without_a_default_destination(monkeypatch, capsys):
    from hermes_cli.config import read_raw_config
    from hermes_cli.observability.shared_metrics_send_config import resolve_send_config
    from hermes_cli.setup import setup_telemetry

    questions = []

    def allow(question, default):
        questions.append(question)
        return True

    monkeypatch.setattr("hermes_cli.setup.prompt_yes_no", allow)
    config = {}

    setup_telemetry(config)

    assert questions == ["Enable local shared metrics?", "Allow uploads to your configured collector?"]
    assert config["telemetry"]["shared_metrics"]["send"] is True
    assert resolve_send_config(read_raw_config()).send is False
    output = capsys.readouterr().out
    assert "no default collector" in output
    assert "Upload consent saved" in output
    assert "configured collector is required" in output
    assert "Nous" not in output
