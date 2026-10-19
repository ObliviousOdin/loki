"""Bundled startup copy uses Loki commands and explains optional OAuth requirements."""

import pytest

from agent.i18n import SUPPORTED_LANGUAGES, t


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_startup_requirements_and_commands_across_bundled_languages(language):
    requirements = t("cli.startup.first_run_pick_provider", lang=language)
    assert "your own API key or local provider" in requirements
    assert "your account and a Loki-authorized client" in requirements
    for key in (
        "run_model_or_setup", "first_run_skipped", "first_run_cancelled",
        "run_model_to_retry", "provider_setup_incomplete",
    ):
        copy = t(f"cli.startup.{key}", lang=language)
        assert "loki model" in copy
        assert "hermes model" not in copy
        assert "hermes setup" not in copy
    notice = t("cli.startup.sign_in_was_lost", lang=language, provider="Nous Research", reason="Hermes-3")
    assert "Nous Research" in notice
    assert "Hermes-3" in notice
    assert "loki auth add Nous Research" in notice
