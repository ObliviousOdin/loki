"""A source update cannot replace Loki with a bootstrap or upstream Hermes tree."""
from pathlib import Path
import subprocess
import zipfile
from urllib.request import urlretrieve

import pytest

from hermes_cli import update_cmd, update_cmd_commit, update_cmd_zip
from hermes_cli.update_loki_identity import git_identity_refusal, source_identity_refusal
from tests.hermes_cli.loki_update_fixtures import loki_source_files, write_loki_source
from tests.hermes_cli.test_update_target_identity import git, update_tree

__all__ = ["update_tree"]  # Explicitly re-export the shared disposable repository fixture.


def test_future_loki_versions_and_upstream_baselines_are_admitted_without_execution(tmp_path):
    files = loki_source_files("99.0a1")
    files["loki_identity.py"] += b'VERSION="99.0a1"\nUPSTREAM_COMMIT="future"\nraise RuntimeError("do not import targets")\n'
    assert source_identity_refusal(files) is None


def _identity_replacement(before, after):
    return {"loki_identity.py": loki_source_files()["loki_identity.py"].replace(before, after)}


@pytest.mark.parametrize("overrides", [
    {"loki.py": None, "loki_identity.py": None, "pyproject.toml": b'[project]\nname="hermes-agent"\n'},
    {"loki.py": b"value = 1\n"},
    {"loki_identity.py": None},
    _identity_replacement(b'"Loki"', b'"Hermes"'),
    _identity_replacement(b'"ObliviousOdin/loki"', b'"NousResearch/hermes-agent"'),
    _identity_replacement(b'"loki"', b'"hermes"'),
    _identity_replacement(b'"obliviousodin-loki-agent"', b'"hermes-agent"'),
    {"pyproject.toml": loki_source_files()["pyproject.toml"].replace(b'loki:main', b'hermes_cli.main:main')},
    {"loki_identity.py": b"\xff"},
    _identity_replacement(b'"Loki"', b'str("Loki")'),
], ids=["bootstrap-or-upstream", "launcher", "identity", "product", "repository", "command",
        "distribution", "script", "invalid", "computed"])
def test_static_loki_contract_refuses_other_or_unreadable_source(overrides):
    files = loki_source_files()
    files.update(overrides)
    assert source_identity_refusal(files) is not None


@pytest.mark.parametrize("failure", [OSError("read refused"), subprocess.TimeoutExpired("git", 1)])
def test_git_read_errors_fail_closed(tmp_path, monkeypatch, failure):
    def fail(*args):
        raise failure
    monkeypatch.setattr(update_cmd_commit, "read_target_files", fail)
    assert "could not be read" in git_identity_refusal(["git"], tmp_path, "target")


def _foreign_commit(root):
    git(root, "rm", "loki.py", "loki_identity.py")
    (root / "pyproject.toml").write_text('[project]\nname="hermes-agent"\n', encoding="utf-8")
    git(root, "commit", "-qam", "bootstrap without Loki")
    return git(root, "rev-parse", "HEAD")


def test_actual_git_update_refuses_bootstrap_before_stash_checkout_or_rescue(update_tree, capsys):
    t = update_tree
    _foreign_commit(t.origin)
    t.args.channel = "main"
    git(t.clone, "checkout", "-q", "--detach", t.base)
    git(t.clone, "commit", "--allow-empty", "-qm", "unreferenced Loki preview")
    original = git(t.clone, "rev-parse", "HEAD")
    dirty = t.clone / ".gitignore"
    dirty.write_bytes(dirty.read_bytes() + b"# Hermes named user work\n")
    before = dirty.read_bytes()
    refs = git(t.clone, "for-each-ref", "--format=%(refname)", "refs/hermes-update-backups")
    with pytest.raises(SystemExit) as stopped:
        update_cmd._cmd_update_impl(t.args, False)
    assert stopped.value.code == 1
    assert git(t.clone, "rev-parse", "HEAD") == original
    assert git(t.clone, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert dirty.read_bytes() == before
    assert git(t.clone, "stash", "list") == ""
    assert git(t.clone, "for-each-ref", "--format=%(refname)", "refs/hermes-update-backups") == refs
    assert not t.requests
    output = capsys.readouterr().out
    assert "Updating Loki..." in output
    assert "Loki source identity" in output and "install is unchanged" in output
    assert "Updating Hermes Agent" not in output


def test_local_branch_landing_is_refused_before_stashing_even_with_valid_remote(update_tree):
    t = update_tree
    git(t.clone, "checkout", "-q", "main")
    foreign = _foreign_commit(t.clone)
    git(t.clone, "checkout", "-q", "--detach", t.base)
    (t.clone / ".gitignore").write_text("user work\n", encoding="utf-8")
    git(t.clone, "fetch", "-q", "origin")
    with pytest.raises(SystemExit):
        update_cmd._prepare_checkout_for_update(
            ["git"], "main", "HEAD", is_fork=False, assume_yes=True, gateway_mode=False,
            gw_input_fn=None, switch_branch=False, _windows_gateway_resume=None)
    assert git(t.clone, "rev-parse", "HEAD") == t.base
    assert git(t.clone, "rev-parse", "main") == foreign
    assert (t.clone / ".gitignore").read_text() == "user work\n"
    assert git(t.clone, "stash", "list") == ""


def test_commit_point_rechecks_the_actual_git_landing_without_arming_debt(update_tree, monkeypatch):
    t = update_tree
    foreign = _foreign_commit(t.origin)
    git(t.clone, "fetch", "-q", "origin")
    armed = []
    monkeypatch.setattr(update_cmd_commit, "arm_commit_obligations", lambda *a: armed.append(a))
    reason = update_cmd_commit.arm_commit_point(["git"], t.clone, foreign,
                                               pre=t.base, target=foreign, stash=None)
    assert reason and "Loki" in reason
    assert not armed
    assert git(t.clone, "rev-parse", "HEAD") == t.base
    assert not (t.clone / ".git/hermes-update-pull").exists()


@pytest.mark.parametrize("target_kind", ["bootstrap", "valid", "unreadable", "wrong-repository"])
def test_actual_zip_transport_admits_only_loki_before_live_overlay(tmp_path, monkeypatch, target_kind):
    valid = target_kind == "valid"
    live = tmp_path / "live"
    live.mkdir()
    write_loki_source(live)
    (live / "payload.txt").write_text("old user install", encoding="utf-8")
    canary = tmp_path / "Hermes foreign canary"
    canary.write_bytes(b"foreign data unchanged")
    before = {p.name: p.read_bytes() for p in live.iterdir()}
    archive = tmp_path / "target.zip"
    sha = "b" * 40
    with zipfile.ZipFile(archive, "w") as target:
        files = ({"pyproject.toml": b'[project]\nname="hermes-agent"\n'}
                 if target_kind == "bootstrap" else loki_source_files("2.0"))
        if target_kind == "wrong-repository":
            files["loki_identity.py"] = files["loki_identity.py"].replace(
                b"ObliviousOdin/loki", b"NousResearch/hermes-agent")
        for name, data in {**files, "payload.txt": b"new Loki install"}.items():
            target.writestr("loki-main/" + name, data)
        target.comment = sha.encode()
    monkeypatch.setattr("urllib.request.urlretrieve", lambda url, dest: urlretrieve(archive.as_uri(), dest))
    monkeypatch.setattr(update_cmd._m(), "PROJECT_ROOT", live)
    if target_kind == "unreadable":
        read = Path.read_bytes
        def fail_metadata(path):
            if path.name == "loki_identity.py" and path.parent.name == "loki-main":
                raise PermissionError("fixture metadata read failure")
            return read(path)
        monkeypatch.setattr(Path, "read_bytes", fail_metadata)
    armed = []
    monkeypatch.setattr(update_cmd_commit, "arm_commit_obligations", lambda root, expected: armed.append(expected))
    if valid:
        assert update_cmd_zip._download_and_swap_zip("main", "owned fixture", sha) == sha
        assert (live / "payload.txt").read_bytes() == b"new Loki install"
        assert armed == [sha]
    else:
        with pytest.raises(SystemExit) as stopped:
            update_cmd_zip._download_and_swap_zip("main", "owned fixture", sha)
        assert stopped.value.code == 1
        assert {p.name: p.read_bytes() for p in live.iterdir()} == before
        assert not armed
    assert canary.read_bytes() == b"foreign data unchanged"
