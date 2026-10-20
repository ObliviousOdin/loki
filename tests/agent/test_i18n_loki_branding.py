"""Brand bundled authored templates before custom catalogs and runtime values are applied."""

import pytest

from agent import i18n


@pytest.fixture(autouse=True)
def isolated_catalog_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "state"))
    i18n.reset_language_cache()
    yield
    i18n.reset_language_cache()


@pytest.mark.parametrize("lang", ["en", "zh", "hu", "de"])
def test_actual_bundled_copy_brands_product_and_retains_model_and_wakeword(lang):
    assert "Loki" in i18n.t("slash.version.description", lang=lang)
    assert "Hermes" not in i18n.t("gateway.topic.new_header", lang=lang)
    assert "Loki" in i18n.t("gateway.topic.new_header", lang=lang)
    assert "Hey Hermes" in i18n.t("slash.wake.description", lang=lang)
    models = i18n.t("cli.banner.hermes_models_not_agentic", lang=lang)
    assert "Nous Research" in models and "Hermes 3" in models
    assert "Loki" in models and "Hermes Agent" not in models


def test_bundled_templates_precede_formatting_and_english_fallback(tmp_path, monkeypatch):
    (tmp_path / "en.yaml").write_text('greet: "Hermes greets {name}; use HERMES_HOME"\n', encoding="utf-8")
    (tmp_path / "fr.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(i18n, "_locales_dir", lambda: tmp_path)
    name = "Hermes /home/Hermes/.hermes/HERMES_TOKEN"

    rendered = i18n.t("greet", lang="fr", name=name)

    assert rendered == f"Loki greets {name}; use LOKI_HOME"
    assert i18n.t("greet", lang="en") == "Loki greets {name}; use LOKI_HOME"


@pytest.mark.parametrize("layer", ["overlay_layer", "pack_layer"])
def test_custom_catalog_layers_remain_exactly_authored(tmp_path, monkeypatch, layer):
    (tmp_path / "en.yaml").write_text('greet: "Hermes greets {name}"\n', encoding="utf-8")
    monkeypatch.setattr(i18n, "_locales_dir", lambda: tmp_path)
    custom = {"greet": "Custom Hermes keeps HERMES_HOME for {name}"}
    monkeypatch.setattr(i18n.i18n_layers, layer, lambda *_args: custom.copy())

    assert i18n.t("greet", lang="en", name="Hermes") == "Custom Hermes keeps HERMES_HOME for Hermes"
    assert custom == {"greet": "Custom Hermes keeps HERMES_HOME for {name}"}


def test_static_reference_urls_protocol_fields_and_module_identifiers_survive(tmp_path, monkeypatch):
    (tmp_path / "en.yaml").write_text(
        'reference: "Hermes uses .hermes.md and hermes_tools; '
        'see https://example.test/Hermes?agent=hermes and {HERMES_CUSTOM}"\n', encoding="utf-8")
    monkeypatch.setattr(i18n, "_locales_dir", lambda: tmp_path)

    rendered = i18n.t("reference", lang="en", HERMES_CUSTOM="Hermes-model")

    assert rendered == ("Loki uses .loki.md and hermes_tools; "
                        "see https://example.test/Hermes?agent=hermes and Hermes-model")


def test_actual_bundled_context_guidance_names_the_owned_instruction_file():
    for key in ("tips.t172", "tips.t177"):
        text = i18n.t(key, lang="en")
        assert ".loki.md" in text and ".hermes.md" not in text
