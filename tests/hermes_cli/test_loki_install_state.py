"""Loki onboarding discovers only this product's roots, services and machine markers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hermes_cli import install_state, onboarding_run
from hermes_platform.resolver import known_dirs


@pytest.fixture
def machine(tmp_path, monkeypatch):
    home = tmp_path / "user"
    active = home / ".loki"
    active.mkdir(parents=True)
    for key, value in {
        "HOME": home, "USERPROFILE": home, "LOCALAPPDATA": home / "AppData" / "Local",
        "APPDATA": home / "AppData" / "Roaming", "XDG_STATE_HOME": home / ".local" / "state",
        "XDG_CONFIG_HOME": home / ".config", "HERMES_HOME": active,
    }.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("HERMES_SHARED_AUTH_DIR", raising=False)
    monkeypatch.setattr(known_dirs, "system_gateway_service_definition_globs", tuple)
    # Do not enumerate the actual host's registry, PATH or Scheduled Tasks.
    monkeypatch.setattr(install_state, "_registry_home", tuple)
    monkeypatch.setattr(install_state, "_launcher_root", tuple)
    from hermes_cli import gateway_windows
    monkeypatch.setattr(gateway_windows, "registered_task_launchers", list)
    import hermes_constants
    monkeypatch.setattr(hermes_constants, "_get_platform_default_hermes_home", lambda: active)
    monkeypatch.setattr(install_state, "machine_places", install_state.Places.of_this_machine)
    install_state.probe.cache_clear()
    yield home, active
    install_state.probe.cache_clear()


def test_hermes_history_never_suppresses_loki_onboarding(machine, monkeypatch):
    from hermes_cli import config

    home, active = machine
    foreign = home / ".hermes" / "config.yaml"
    foreign.parent.mkdir()
    content = "model:\n  provider: fixture-hermes-only\nonboarding:\n  run: false\n"
    foreign.write_text(content, encoding="utf-8")
    old_marker = home / "Library" / "Application Support" / "Nous Research" / ".machine"
    old_marker.parent.mkdir(parents=True)
    old_marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "load_config_readonly", dict)

    assert install_state.probe().fresh
    assert onboarding_run.should_run()
    assert onboarding_run.latch_first_install()
    assert config.read_user_config_raw(active / "config.yaml")["onboarding"]["run"] is True
    assert not any(marker.exists() for marker in install_state.machine_places().markers)
    assert foreign.read_text(encoding="utf-8-sig") == content
    assert old_marker.read_text(encoding="utf-8-sig") == "{}"


def test_loki_history_uses_only_its_owned_machine_marker(machine):
    home, active = machine
    (active / "config.yaml").write_text("model:\n  provider: fixture-loki\n", encoding="utf-8")

    state = install_state.probe()

    assert state.existing
    assert state.findings[0].where == active.resolve()
    markers = install_state.machine_places().markers
    assert markers and markers[0].is_file()
    assert all(marker.is_relative_to(home) for marker in markers)
    assert not (home / "Library" / "Application Support" / "Nous Research").exists()


def test_launcher_discovery_requests_loki_and_preserves_protected_path(tmp_path, monkeypatch):
    import hermes_platform.resolver

    launcher = tmp_path / "private" / "loki"
    locate = Mock(return_value=SimpleNamespace(command=(str(launcher),)))
    monkeypatch.setattr(hermes_platform.resolver, "locate_command", locate)
    monkeypatch.setattr(install_state, "_protected_dirs", lambda: (launcher.parent,))

    assert tuple(install_state._launcher_root()) == (launcher.parent,)
    locate.assert_called_once_with("loki")


@pytest.mark.platforms("windows")
def test_registry_home_reads_only_the_loki_override(tmp_path, monkeypatch):
    import winreg
    from unittest.mock import MagicMock

    key = MagicMock()
    query = Mock(return_value=(str(tmp_path / "owned-home"), winreg.REG_SZ))
    monkeypatch.setattr(winreg, "OpenKey", Mock(return_value=key))
    monkeypatch.setattr(winreg, "QueryValueEx", query)

    assert tuple(install_state._registry_home()) == (tmp_path / "owned-home",)
    query.assert_called_once_with(key.__enter__.return_value, "LOKI_HOME")
