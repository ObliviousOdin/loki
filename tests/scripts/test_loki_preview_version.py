"""Loki's Python prerelease maps to a valid native/JavaScript SemVer."""
import pytest

from scripts.releases.commit_build import version_at


@pytest.mark.parametrize(("python_version", "native_version"), [
    ("0.1.0a1", "0.1.0-alpha.1"), ("0.2.0b3", "0.2.0-beta.3"),
    ("1.0.0rc2", "1.0.0-rc.2"), ("1.0.0", "1.0.0"),
])
def test_loki_preview_version_preserves_stage_and_sequence(python_version, native_version):
    document = f'[project]\nname="obliviousodin-loki-agent"\nversion="{python_version}"\n'
    assert version_at(None, "a" * 40, run=lambda *_: document) == native_version


def test_unrelated_projects_do_not_acquire_a_loki_release_channel():
    document = '[project]\nname="other-project"\nversion="0.1.0a1"\n'
    with pytest.raises(ValueError, match="project.version"):
        version_at(None, "a" * 40, run=lambda *_: document)
