"""Vendor Git layout discovery and probe policy, independent of the interpreter OS.

Git for Windows 2.56 moved x64 installs from mingw64 to ucrt64:
https://github.com/git-for-windows/build-extra/blob/main/ReleaseNotes.md
Native process execution remains covered by test_git_trampoline_windows_live.py.
"""
import pytest

from hermes_cli import update_cmd_git


@pytest.mark.parametrize("relative", [
    "ucrt64/libexec/git-core/git.exe", "ucrt64/bin/git.exe",
    "mingw64/libexec/git-core/git.exe", "mingw64/bin/git.exe",
    "clangarm64/libexec/git-core/git.exe", "mingw32/libexec/git-core/git.exe",
])
@pytest.mark.parametrize("probe_result", [False, True, None], ids=["healthy", "trampoline", "probe-failed"])
def test_vendor_layout_requires_an_existing_binary_and_a_healthy_probe(tmp_path, monkeypatch, relative, probe_result):
    vendor = tmp_path / "Git"
    binary = vendor / relative
    binary.parent.mkdir(parents=True)
    binary.touch()
    candidates = update_cmd_git._git_for_windows_candidates([vendor])
    assert binary in candidates
    assert vendor / "cmd/git.exe" not in candidates
    assert vendor / "bin/git.exe" not in candidates
    # Standard machine locations are outside this disposable filesystem fixture.
    monkeypatch.setattr(update_cmd_git, "_git_for_windows_candidates", lambda roots: [])
    monkeypatch.setattr(update_cmd_git, "_portable_git_candidates", lambda: candidates)
    probes = []

    def probe(argv):
        probes.append(argv)
        return probe_result

    monkeypatch.setattr(update_cmd_git, "_probe_fork_bomb", probe)
    assert update_cmd_git._locate_real_git() == (binary if probe_result is False else None)
    assert probes == [[str(binary)]]
