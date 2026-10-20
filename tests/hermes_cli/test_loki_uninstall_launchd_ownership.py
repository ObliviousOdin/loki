"""Uninstall may inventory legacy backends but must mutate only Loki-owned jobs."""
import os
import plistlib
import shlex
from pathlib import Path

import pytest

from hermes_cli import main_dashboard, uninstall


@pytest.fixture
def launchd_scope(tmp_path, monkeypatch):
    root = tmp_path / "loki-home"
    profile = root / "profiles" / "hermes-work"
    profile.mkdir(parents=True)
    agent_dir = tmp_path / "LaunchAgents"
    daemon_dir = tmp_path / "LaunchDaemons"
    agent_dir.mkdir()
    daemon_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOKI_HOME", str(root))
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv("__LOKI_ENV_BOUND", "1")
    monkeypatch.setattr("hermes_cli.update_fleet_scope.update_scope_homes", lambda: {root, profile})
    monkeypatch.setattr(main_dashboard, "_launchd_plist_dirs",
                        lambda: [("agent", agent_dir), ("daemon", daemon_dir)])
    booted = []
    monkeypatch.setattr(uninstall.subprocess, "run", lambda argv, **_kw: booted.append(argv))

    def job(label, argv, env, *, daemon=False):
        path = (daemon_dir if daemon else agent_dir) / f"{label}.plist"
        path.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": argv,
                                        "EnvironmentVariables": env}))
        return path

    return root, profile, booted, job


def _owned_jobs(root):
    return {
        "public": ("com.obliviousodin.loki.dashboard", ["loki", "dashboard"],
                   {"LOKI_HOME": str(root)}, False),
        "public-conflicting": ("operator.dashboard", ["loki", "serve"],
                               {"LOKI_HOME": str(root), "HERMES_HOME": str(root.parent / "foreign")}, False),
        "bound-module": ("operator.dashboard", ["python3", "-m", "hermes_cli.main", "serve"],
                         {"__LOKI_ENV_BOUND": "1", "HERMES_HOME": str(root)}, True),
        "profile": ("com.obliviousodin.loki.dashboard.hermes-work",
                    ["/owned/bin/loki", "--profile", "hermes-work", "serve"],
                    {"LOKI_HOME": str(root)}, False),
    }


@pytest.mark.platforms("macos")
@pytest.mark.parametrize("kind", ["public", "public-conflicting", "bound-module", "profile"])
def test_owned_loki_launchd_jobs_are_removed_without_losing_internal_launchers(launchd_scope, kind):
    root, profile, booted, job = launchd_scope
    label, argv, env, daemon = _owned_jobs(root)[kind]
    plist = job(label, argv, env, daemon=daemon)
    assert main_dashboard._parse_dashboard_runtime(shlex.join(argv)) is not None
    assert uninstall.remove_dashboard_launchd_jobs() == [plist]
    assert not plist.exists()
    domains = ["system"] if daemon else [f"gui/{os.getuid()}", f"user/{os.getuid()}"]
    assert booted == [["launchctl", "bootout", f"{domain}/{label}"] for domain in domains]
    assert profile.exists()


def _unproven_jobs(root):
    return {
        "hermes": ("com.user.hermes-dashboard", ["hermes", "dashboard"], {"LOKI_HOME": str(root)}),
        "foreign-label": ("com.foreign.fabric.serve", ["loki", "serve"], {"LOKI_HOME": str(root)}),
        "foreign-public": ("com.obliviousodin.loki.dashboard", ["/foreign/bin/hermes", "serve"],
                           {"__LOKI_ENV_BOUND": "1", "HERMES_HOME": str(root)}),
        "unbound-module": ("operator.dashboard", ["python3", "-m", "hermes_cli.main", "serve"],
                           {"LOKI_HOME": str(root)}),
        "foreign-home": ("com.obliviousodin.loki.dashboard", ["loki", "serve"],
                         {"LOKI_HOME": str(root.parent / "fabric-home"), "HERMES_HOME": str(root)}),
        "unreadable-home": ("operator.dashboard", ["loki", "serve"], {}),
        "relative-home": ("operator.dashboard", ["loki", "serve"], {"LOKI_HOME": "relative/loki-home"}),
        "non-string-home": ("operator.dashboard", ["loki", "serve"], {"LOKI_HOME": [str(root)]}),
        "foreign-bound-module": ("operator.dashboard", ["python3", "-m", "hermes_cli.main", "serve"],
                                 {"__LOKI_ENV_BOUND": "1", "HERMES_HOME": str(root.parent / "hermes-home")}),
    }


@pytest.mark.platforms("macos")
@pytest.mark.parametrize("kind", ["hermes", "foreign-label", "foreign-public", "unbound-module",
                                  "foreign-home", "unreadable-home", "relative-home", "non-string-home",
                                  "foreign-bound-module"])
def test_uninstall_preserves_foreign_or_unproven_plist_bytes_and_never_boots_out(launchd_scope, kind):
    root, _, booted, job = launchd_scope
    label, argv, env = _unproven_jobs(root)[kind]
    plist = job(label, argv, env)
    original = plist.read_bytes()
    assert main_dashboard._parse_dashboard_runtime(shlex.join(argv)) is not None
    assert uninstall.remove_dashboard_launchd_jobs() == []
    assert plist.read_bytes() == original
    assert booted == []
