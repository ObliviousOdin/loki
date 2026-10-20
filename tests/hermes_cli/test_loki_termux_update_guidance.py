"""APT update checks expose owned instructions without starting an installer."""
import asyncio
from types import SimpleNamespace

from hermes_cli.web_routers import actions


def test_apt_check_never_recommends_upgrading_foreign_hermes(monkeypatch, tmp_path):
    monkeypatch.setattr(actions, "_server_path", lambda _name: tmp_path)
    monkeypatch.setattr(actions, "is_commit_build", lambda _root: False)
    monkeypatch.setattr(actions, "_dashboard_local_update_managed_externally", lambda: False)
    monkeypatch.setattr(actions, "detect_install_method", lambda _root: "apt")
    monkeypatch.setattr(actions, "get_version_info", lambda: SimpleNamespace(derived_version="0.1.0a1"))
    result = asyncio.run(actions.check_hermes_update())
    assert result["install_method"] == "apt" and result["can_apply"] is False
    assert result["update_available"] is False
    assert "Loki" in result["message"]
    assert "ObliviousOdin/loki/releases" in result["message"]
    assert "pkg upgrade hermes-agent" not in result["message"]
    assert "ObliviousOdin/loki/releases" in result["update_command"]
