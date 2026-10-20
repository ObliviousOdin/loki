"""Default system-level policy and provenance belong exclusively to Loki."""

from pathlib import Path


def test_managed_policy_probes_only_loki_system_config(monkeypatch):
    from hermes_cli import managed_scope

    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    monkeypatch.setattr(managed_scope, "_under_pytest", lambda: False)
    probed = []
    monkeypatch.setattr(Path, "is_dir", lambda path: probed.append(path) or False)

    assert managed_scope.get_managed_dir() is None
    assert probed == [Path("/etc/loki")]


def test_image_provenance_probes_only_loki_system_marker(monkeypatch):
    from hermes_cli import image_provenance

    probed = []

    def absent(path):
        probed.append(path)
        raise FileNotFoundError(path)

    monkeypatch.setattr(Path, "lstat", absent)

    assert image_provenance.read_image_provenance() is None
    assert probed == [Path("/etc/loki/image-provenance.json")]
