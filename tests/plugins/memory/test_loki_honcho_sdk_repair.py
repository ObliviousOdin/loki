"""The optional provider repairs declared SDK dependencies through the existing PM."""
import importlib
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from plugins.memory import _load_package


@pytest.fixture
def repair_cli(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[3] / "optional-plugins/honcho"
    package = _load_package(source, "honcho")
    assert package is not None
    command = importlib.import_module(package.__name__ + ".cli")
    monkeypatch.setitem(sys.modules, "honcho", None)
    monkeypatch.setattr(command, "_prompt", lambda *_args, **_kwargs: "y")
    monkeypatch.setattr("pm.paths.repo_root", lambda: tmp_path)
    return command


def test_existing_sdk_does_not_prompt_or_sync(repair_cli, monkeypatch):
    monkeypatch.setitem(sys.modules, "honcho", SimpleNamespace())
    monkeypatch.setattr(repair_cli, "_prompt", lambda *_args, **_kwargs: pytest.fail("SDK is ready"))
    monkeypatch.setattr("pm.client.sync_venv", lambda **_kwargs: pytest.fail("SDK is ready"))
    assert repair_cli._ensure_sdk_installed() is True


def test_declined_sdk_repair_leaves_environment_unchanged(repair_cli, monkeypatch, capsys):
    monkeypatch.setattr(repair_cli, "_prompt", lambda *_args, **_kwargs: "n")
    monkeypatch.setattr("pm.client.sync_venv", lambda **_kwargs: pytest.fail("repair was declined"))
    assert repair_cli._ensure_sdk_installed() is False
    assert "loki plugins enable honcho" in capsys.readouterr().out


def test_approved_sdk_repair_syncs_current_plugin_selection_and_adopts(repair_cli, monkeypatch, tmp_path):
    calls = []

    def sync(**kwargs):
        calls.append(("sync", kwargs))

    def adopt(root):
        calls.append(("adopt", root))
        monkeypatch.setitem(sys.modules, "honcho", SimpleNamespace())
        return True

    monkeypatch.setattr("pm.client.sync_venv", sync)
    monkeypatch.setattr("pm.environments_adopt.adopt_selected", adopt)
    assert repair_cli._ensure_sdk_installed() is True
    assert calls == [("sync", {"explicit": True, "repair": True}), ("adopt", tmp_path)]


def test_sdk_repair_failure_is_not_reported_ready_or_logged_with_secrets(repair_cli, monkeypatch, caplog, capsys):
    from pm.package import InstallError

    secret = "synthetic-provider-secret-do-not-log"

    def fail(**_kwargs):
        raise InstallError("venv", secret)

    monkeypatch.setattr("pm.client.sync_venv", fail)
    with caplog.at_level(logging.ERROR):
        assert repair_cli._ensure_sdk_installed() is False
    output = capsys.readouterr().out
    assert "loki plugins enable honcho" in output
    assert secret not in output + caplog.text
    assert any(record.exc_info and record.exc_info[2] for record in caplog.records)


def test_sdk_repair_requires_restart_when_generation_cannot_be_adopted(repair_cli, monkeypatch, capsys):
    monkeypatch.setattr("pm.client.sync_venv", lambda **_kwargs: None)
    monkeypatch.setattr("pm.environments_adopt.adopt_selected", lambda _root: False)
    assert repair_cli._ensure_sdk_installed() is False
    assert "Restart Loki" in capsys.readouterr().out


def test_sdk_repair_checks_import_before_announcing_ready(repair_cli, monkeypatch, capsys):
    monkeypatch.setattr("pm.client.sync_venv", lambda **_kwargs: None)
    monkeypatch.setattr("pm.environments_adopt.adopt_selected", lambda _root: True)
    assert repair_cli._ensure_sdk_installed() is False
    assert "loki plugins enable honcho" in capsys.readouterr().out
