"""Loki cleanup must preserve an installed Hermes product beside it."""

from pathlib import Path

import pytest


def test_shell_cleanup_keeps_the_upstream_install(tmp_path, monkeypatch):
    from hermes_cli import uninstall

    rc = tmp_path / ".zshrc"
    upstream = '# Hermes Agent\nexport PATH="$HOME/.hermes/bin:$PATH"\nexport PATH="$HOME/grafana-loki/bin:$PATH"\n'
    owned = '# Loki Agent\nexport PATH="$HOME/.loki/bin:$PATH"\n'
    rc.write_text(upstream + owned, encoding="utf-8")
    monkeypatch.setattr(uninstall, "find_shell_configs", lambda: [rc])
    assert uninstall.remove_path_from_shell_configs() == [rc]
    assert rc.read_text(encoding="utf-8") == upstream


@pytest.mark.platforms("macos")
def test_app_cleanup_preserves_hermes_and_unrelated_loki_names(tmp_path, monkeypatch):
    from hermes_cli.uninstall import remove_desktop_app_leftovers

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    caches = tmp_path / "Library" / "Caches"
    ours = caches / "com.obliviousodin.loki"
    upstream = caches / "com.nousresearch.hermes"
    unrelated = caches / "my-loki-research"
    for path in (ours, upstream, unrelated):
        path.mkdir(parents=True)
        (path / "data").write_text("preserve unless owned", encoding="utf-8")
    assert remove_desktop_app_leftovers(full_uninstall=False) == [ours]
    assert upstream.is_dir()
    assert unrelated.is_dir()
