"""Service identities and cleanup stay within the Loki installation."""

from pathlib import Path

import pytest


def test_gateway_service_and_lock_namespace(tmp_path, monkeypatch):
    from hermes_cli import gateway
    from gateway import status

    home = tmp_path / ".loki"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("HERMES_GATEWAY_LOCK_DIR", raising=False)
    monkeypatch.setattr(gateway, "_native_service_homes", lambda: {home.resolve()})
    assert gateway.get_service_name() == "loki-gateway"
    assert status._get_lock_dir() == tmp_path / "state" / "loki" / "gateway-locks"
    assert gateway._find_legacy_hermes_units() == []


@pytest.mark.platforms("macos")
def test_launchd_and_gui_paths_are_owned(tmp_path, monkeypatch):
    from hermes_cli import gateway
    from hermes_cli.gui_uninstall import desktop_userdata_dir, packaged_gui_app_paths

    home = tmp_path / ".loki"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(gateway, "_native_service_homes", lambda: {home.resolve()})
    assert gateway.get_launchd_label() == "com.obliviousodin.loki.gateway"
    assert desktop_userdata_dir() == tmp_path / "Library" / "Application Support" / "Loki"
    assert Path("/Applications/Loki.app") in packaged_gui_app_paths()
    assert Path("/Applications/Hermes.app") not in packaged_gui_app_paths()


def test_windows_service_ownership_rejects_the_old_product():
    from hermes_cli.gateway_windows import hermes_owns_windows_service

    assert hermes_owns_windows_service("Loki_Gateway", "C:/services/gateway.exe", ())
    assert not hermes_owns_windows_service("Hermes_Gateway", "C:/hermes/gateway.exe", ())
