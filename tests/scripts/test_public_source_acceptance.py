"""Published-source admission is independent of installer execution and user state."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import signal
import subprocess
import sys

import pytest

from scripts.loki import public_source_acceptance as acceptance
from tests.waiting import wait_until


COMMIT = "1" * 40
BASELINE = "2" * 40
TAG = "v0.1.0-alpha.2"


def released_source():
    release = {"id": 123, "tag_name": TAG, "draft": False, "prerelease": True}
    metadata = {"product": "Loki", "version": "0.1.0-alpha.2", "commit": COMMIT,
                "repository": acceptance.REPOSITORY, "kind": "source-preview",
                "signed": False, "upstream_commit": BASELINE}
    project = {"name": "obliviousodin-loki-agent", "version": "0.1.0a2"}
    baseline = {"commit": BASELINE}
    comparison = {"status": "ahead", "behind_by": 0, "base_commit": {"sha": COMMIT},
                  "merge_base_commit": {"sha": COMMIT}}
    return release, metadata, project, baseline, comparison


def test_published_alpha_must_bind_its_tag_source_version_and_main_ancestry():
    source = released_source()
    acceptance.validate_release(*source, tag=TAG, commit=COMMIT, peeled=COMMIT)
    for index, key, invalid in (
        (0, "draft", True), (0, "tag_name", "v0.1.0-alpha.1"),
        (1, "repository", "foreign/loki"), (1, "commit", "3" * 40),
        (1, "upstream_commit", "3" * 40), (2, "version", "0.1.0a1"),
        (4, "behind_by", 1), (4, "merge_base_commit", {"sha": "3" * 40}),
    ):
        changed = deepcopy(source)
        changed[index][key] = invalid
        with pytest.raises(ValueError):
            acceptance.validate_release(*changed, tag=TAG, commit=COMMIT, peeled=COMMIT)
    with pytest.raises(ValueError):
        acceptance.validate_release(*source, tag=TAG, commit=COMMIT, peeled="3" * 40)


@pytest.mark.parametrize("tampered", [False, True], ids=["exact-installer", "different-source"])
def test_acquisition_matches_release_hashes_and_immutable_installer(tmp_path, monkeypatch, tampered):
    release, metadata, project, baseline, comparison = released_source()
    installer = b"#!/bin/sh\nexit 0\n"
    payload = {"install.sh": installer, "LOKI-PREVIEW.json": json.dumps(metadata).encode()}
    payload["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in payload.items()
    ).encode()
    release["assets"] = [{"name": name, "size": len(data),
                          "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
                          "browser_download_url": f"https://github.com/{acceptance.REPOSITORY}/releases/download/{TAG}/{name}"}
                         for name, data in payload.items()]
    prefix = f"https://raw.githubusercontent.com/{acceptance.REPOSITORY}/{COMMIT}"
    responses = {
        f"{acceptance.API}/releases/tags/{TAG}": json.dumps(release).encode(),
        f"{acceptance.API}/git/ref/tags/{TAG}": json.dumps({"object": {"type": "commit", "sha": COMMIT}}).encode(),
        f"{acceptance.API}/compare/{COMMIT}...main": json.dumps(comparison).encode(),
        f"{prefix}/pyproject.toml": f"[project]\nname='{project['name']}'\nversion='{project['version']}'\n".encode(),
        f"{prefix}/docs/loki/UPSTREAM.json": json.dumps(baseline).encode(),
        f"{prefix}/scripts/install.sh": installer + (b"# changed\n" if tampered else b""),
        **{f"https://github.com/{acceptance.REPOSITORY}/releases/download/{TAG}/{name}": data
           for name, data in payload.items()},
    }
    requested = []

    def fetch(url, target):
        requested.append(url)
        target.write_bytes(responses[url])

    monkeypatch.setattr(acceptance, "fetch", fetch)
    if tampered:
        with pytest.raises(ValueError, match="differs from immutable source"):
            acceptance.acquire(tmp_path, TAG, COMMIT, "install.sh")
    else:
        result = acceptance.acquire(tmp_path, TAG, COMMIT, "install.sh")
        assert result["declared_version"] == "0.1.0a2"
        assert result["asset_sha256"]["install.sh"] == hashlib.sha256(installer).hexdigest()
        assert result["hash_verification_not_signing"] is True
    assert all(url.startswith("https://") for url in requested)


def test_child_environment_and_canaries_have_no_inherited_application_or_credentials(tmp_path):
    home = tmp_path / "Fresh User Profile With Spaces"
    host = {**os.environ, "LOKI_HOME": "foreign", "HERMES_HOME": "foreign",
            "LOKI_REPO_URL": "foreign", "__LOKI_ENV_BOUND": "1", "PYTHONPATH": "foreign",
            "GH_TOKEN": "synthetic-secret", "OPENAI_API_KEY": "synthetic-secret"}
    env = acceptance.clean_environment(home, host, windows=os.name == "nt")
    assert env["HOME"] == env["USERPROFILE"] == str(home)
    assert not any(key.startswith(("LOKI_", "HERMES_", "UV_", "PM_")) for key in env)
    assert not {"GH_TOKEN", "OPENAI_API_KEY", "__LOKI_ENV_BOUND", "PYTHONPATH"} & env.keys()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    canary = foreign / "canary"
    canary.write_bytes(b"preserve exact synthetic bytes")
    before = acceptance.foreign_snapshot([foreign])
    canary.write_bytes(b"changed")
    assert acceptance.foreign_snapshot([foreign]) != before


@pytest.mark.parametrize("url", ["http://github.com/owned", "https://github.com.evil.invalid/a",
                                 "https://token@github.com/a", "https://github.com:444/a"])
def test_download_redirect_admission_refuses_untrusted_or_credentialed_urls(url):
    with pytest.raises(ValueError):
        acceptance.validate_url(url)


def test_checksum_manifest_refuses_duplicate_and_path_entries():
    row = "a" * 64 + "  install.sh\n"
    assert acceptance.checksum_rows(row) == {"install.sh": "a" * 64}
    for contents in (row + row, "a" * 64 + "  ../install.sh\n", "a" * 63 + "  install.sh\n"):
        with pytest.raises(ValueError):
            acceptance.checksum_rows(contents)


def test_runner_path_cleanup_preserves_exact_value_even_when_install_fails(tmp_path, monkeypatch):
    original = "C:\\Tools;C:\\User's 日本語\\bin\nwith newline"
    calls, receipt = [], {}

    def command_boundary(command, env, root, label, **options):
        calls.append((label, options))
        if label == "original-user-path":
            return json.dumps(original)
        assert label == "restore-user-path" and options["cleanup"] is True
        # The real native command receives ASCII JSON rather than a shell-
        # interpolated path; the native registry API is exercised only hosted.
        assert options["stdin"].isascii()
        return options["stdin"]

    monkeypatch.setattr(acceptance, "run", command_boundary)
    with pytest.raises(RuntimeError, match="installer failed"):
        with acceptance.runner_user_path({"SYSTEMROOT": str(tmp_path)}, tmp_path, receipt):
            raise RuntimeError("installer failed")
    assert [label for label, _ in calls] == ["original-user-path", "restore-user-path"]
    assert json.loads(calls[-1][1]["stdin"]) == original
    assert receipt == {"runner_user_path_restored": True}


@pytest.mark.platforms("posix")
def test_owned_command_is_reaped_after_forced_termination(tmp_path):
    ready = tmp_path / "ready"
    body = ("import pathlib,signal,threading;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            f"pathlib.Path({str(ready)!r}).write_bytes(b'ready');threading.Event().wait()")
    child = subprocess.Popen([sys.executable, "-I", "-c", body], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    try:
        wait_until(ready.exists, timeout=10, what="owned child TERM refusal readiness")
        acceptance.stop_owned(child)
        assert child.returncode == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


@pytest.mark.parametrize("key,value", [("GITHUB_EVENT_NAME", "push"),
                                      ("GITHUB_REF", "refs/heads/unreviewed"),
                                      ("RUNNER_ENVIRONMENT", "self-hosted")])
def test_execution_refuses_unowned_dispatch_before_creating_state(tmp_path, monkeypatch, key, value):
    out = tmp_path / "not-created"
    monkeypatch.setattr(sys, "argv", ["accept", "--tag", TAG, "--commit", COMMIT,
                                     "--out", str(out), "--execute"])
    environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": acceptance.REPOSITORY,
                   "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                   "RUNNER_ENVIRONMENT": "github-hosted", key: value}
    for name, entry in environment.items():
        monkeypatch.setenv(name, entry)
    with pytest.raises(SystemExit) as error:
        acceptance.main()
    assert error.value.code == 2 and not out.exists()


def test_failed_acceptance_retains_only_allowlisted_error_metadata(tmp_path, monkeypatch, capsys):
    out = tmp_path / "receipt"
    monkeypatch.setattr(sys, "argv", ["accept", "--tag", TAG, "--commit", COMMIT,
                                     "--out", str(out), "--execute"])
    for key, value in {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": acceptance.REPOSITORY,
                       "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                       "RUNNER_ENVIRONMENT": "github-hosted"}.items():
        monkeypatch.setenv(key, value)
    # Metadata-only test allocates a tiny receipt and never starts installation.
    monkeypatch.setattr(acceptance.shutil, "disk_usage", lambda _: type("Usage", (), {"free": acceptance.MIN_FREE})())

    def fail(*_):
        raise acceptance.CommandFailure("config-set", "nonzero-exit")

    monkeypatch.setattr(acceptance, "execute", fail)
    assert acceptance.main() == 1
    result = json.loads((out / "PUBLIC-SUMMARY.json").read_text(encoding="utf-8-sig"))
    assert result["status"] == "failed" and result["failed_check"] == "config-set"
    assert result["command_outcome"] == "nonzero-exit"
    assert str(tmp_path) not in capsys.readouterr().out
