"""Final frontend compilation never touches builder inputs or external source."""
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.bundles.bytecode import MARKER, bake_frontend_bytecode


def test_html_only_frontend_never_spawns_or_claims_a_complete_payload_bake(tmp_path, monkeypatch):
    web = tmp_path / "hermes-agent/hermes_cli/web_dist"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html>fixture</html>", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("HTML-only final merge must not invoke an interpreter")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    assert bake_frontend_bytecode(tmp_path, Path(sys.executable), ["web"]) == {"modules": 0}
    assert not (tmp_path / MARKER).exists()
    assert not list(tmp_path.rglob("__pycache__"))


@pytest.mark.platforms("posix")
def test_external_frontend_python_link_is_refused_before_compiler_io(tmp_path, monkeypatch):
    root = tmp_path / "payload"
    scripts = root / "hermes-agent/hermes_cli/tui_dist/scripts"
    scripts.mkdir(parents=True)
    foreign = tmp_path / "foreign.py"
    foreign.write_bytes(b"foreign source canary; do not compile\n")
    (scripts / "linked.py").symlink_to(foreign)

    def forbidden(*args, **kwargs):
        pytest.fail("external source must be refused before invoking a compiler")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="belong to the payload"):
        bake_frontend_bytecode(root, Path(sys.executable), ["tui"])
    assert foreign.read_bytes() == b"foreign source canary; do not compile\n"
    assert not list(root.rglob("__pycache__"))
    assert not (root / MARKER).exists()
