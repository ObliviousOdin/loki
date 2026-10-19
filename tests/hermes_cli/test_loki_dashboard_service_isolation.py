"""Loki updates must not adopt Hermes/Fabric supervisors or another Loki home."""

from types import SimpleNamespace

import pytest

from hermes_cli import dashboard_procs, main_dashboard, update_cmd_fleet, update_inventory


@pytest.fixture
def owned_home(tmp_path, monkeypatch):
    home = tmp_path / "loki-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("LOKI_HOME", str(home))
    monkeypatch.setenv("__LOKI_ENV_BOUND", "1")
    monkeypatch.setattr("hermes_cli.update_fleet_scope.update_scope_homes", lambda: {home})
    return str(home)


@pytest.mark.parametrize("unit", ["hermes-dashboard.service", "hermes-serve-work.service",
                                  "fabric-dashboard.service", "foreign-fabric-serve.service"])
def test_foreign_managed_unit_is_never_probed_or_restarted(unit, owned_home, monkeypatch):
    monkeypatch.setattr(main_dashboard, "_run_probe", lambda *_a, **_k: pytest.fail("foreign unit was probed"))
    assert main_dashboard._restart_managed_dashboard_service("update", unit, scope_home=owned_home) is False
    assert main_dashboard._try_restart_systemd_service(unit, ownership_home=owned_home) is False
    assert update_cmd_fleet._systemd_unit_owned_by_update(["systemctl", "--user"], unit) is False


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("unit", ["loki-dashboard.service", "operator-dashboard.service"])
@pytest.mark.parametrize("home_kind", ["owned", "foreign", "unreadable"])
def test_managed_unit_requires_live_mainpid_home_proof(unit, home_kind, owned_home, monkeypatch):
    calls = []

    def probe(argv, *, timeout):
        calls.append(argv)
        stdout = (f"{unit} enabled\n" if "list-unit-files" in argv else
                  "4242\n" if "show" in argv else "active\n")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(main_dashboard, "_run_probe", probe)
    home = {"owned": owned_home, "foreign": owned_home + "-foreign", "unreadable": None}[home_kind]
    monkeypatch.setattr(dashboard_procs, "_hermes_home_for_pid", lambda pid: home)
    assert main_dashboard._restart_managed_dashboard_service("update", unit, scope_home=owned_home) is (home_kind == "owned")
    restarts = [argv for argv in calls if "restart" in argv]
    assert restarts == ([["systemctl", "--user", "restart", unit]] if home_kind == "owned" else [])
    assert any("--property=MainPID" in argv for argv in calls)
    assert all(argv[:2] == ["systemctl", "--user"] for argv in calls)


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("restart_managed", [False, True])
@pytest.mark.parametrize("unit", ["hermes-serve.service", "fabric-dashboard.service"])
def test_foreign_supervisor_is_spared_even_with_inherited_loki_home(
    restart_managed, unit, owned_home, monkeypatch,
):
    pid = 4242
    cmd = ["loki", "serve", "--port", "9119"]
    monkeypatch.setattr(dashboard_procs, "_iter_process_table", lambda: [(pid, " ".join(cmd))])
    monkeypatch.setattr("hermes_cli.process_identity.ledger_entries", lambda **_k: [])
    monkeypatch.setattr(dashboard_procs, "_caller_ancestor_pids", lambda: set())
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: {
        "LOKI_HOME": owned_home, "HERMES_HOME": owned_home, "__LOKI_ENV_BOUND": "1",
    })
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: cmd)
    monkeypatch.setattr(main_dashboard, "_restart_managed_dashboard_service", lambda *_a, **_k: False)
    monkeypatch.setattr(main_dashboard, "_loaded_launchd_backend_jobs", list)
    monkeypatch.setattr(main_dashboard, "_get_pid_cgroup_path", lambda _pid: f"/system.slice/{unit}")
    monkeypatch.setattr(main_dashboard, "_pid_unified_cgroup_entries", lambda _pid: iter([f"/system.slice/{unit}"]))
    monkeypatch.setattr(main_dashboard, "_run_probe", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=str(pid)))
    monkeypatch.setattr(dashboard_procs, "_kill_pids_posix", lambda *_a: pytest.fail("foreign backend was stopped"))
    result = dashboard_procs._kill_stale_dashboard_processes(
        restart_managed=restart_managed, scope_home=owned_home,
    )
    assert result == {"matched": [], "killed": [], "failed": []}


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("unit", ["loki-serve-work.service", "operator-dashboard.service"])
def test_captured_owned_custom_service_retains_mainpid_scope_and_restart(unit, owned_home, monkeypatch):
    pid = 4242
    cgroup = f"/user.slice/{unit}"
    calls = []
    monkeypatch.setattr(main_dashboard, "_restart_managed_dashboard_service", lambda *_a, **_k: False)
    monkeypatch.setattr(main_dashboard, "_find_stale_dashboard_pids", lambda **_k: [pid])
    monkeypatch.setattr(main_dashboard, "_loaded_launchd_backend_jobs", list)
    monkeypatch.setattr(main_dashboard, "_get_pid_cgroup_path", lambda _pid: cgroup)
    monkeypatch.setattr(main_dashboard, "_pid_unified_cgroup_entries", lambda _pid: iter([cgroup]))
    monkeypatch.setattr(dashboard_procs, "_hermes_home_for_pid", lambda _pid: owned_home)

    def probe(argv, *, timeout):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=str(pid) if "show" in argv else "")

    monkeypatch.setattr(main_dashboard, "_run_probe", probe)
    monkeypatch.setattr(dashboard_procs, "_kill_pids_posix", lambda pids, killed, failed: killed.extend(pids))
    result = dashboard_procs._kill_stale_dashboard_processes(restart_managed=True, scope_home=owned_home)
    assert result["killed"] == [pid] and result["unrecovered"] == []
    assert calls == [["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
                     ["systemctl", "--user", "restart", unit]]


@pytest.mark.parametrize("label", ["ai.hermes.dashboard", "com.foreign.fabric.serve"])
def test_captured_foreign_launchd_identity_never_kickstarts(label, owned_home, monkeypatch):
    monkeypatch.setattr(main_dashboard, "_run_probe", lambda *_a, **_k: pytest.fail("foreign launchd restart"))
    assert main_dashboard._restart_launchd_job("gui/501", label, 4242, ownership_home=owned_home) is False
    result = dashboard_procs._restart_killed_backends(
        [4242], {}, {}, {}, {4242: owned_home}, pid_launchd={4242: ("gui/501", label, 4242)},
    )
    assert result == [4242]


@pytest.mark.parametrize("home_kind", ["owned", "foreign", "unreadable"])
def test_explicit_custom_launchd_requires_owned_home(home_kind, owned_home, monkeypatch):
    calls = []
    home = {"owned": owned_home, "foreign": owned_home + "-foreign", "unreadable": None}[home_kind]
    monkeypatch.setattr(main_dashboard, "_run_probe", lambda argv, **_k: calls.append(argv) or SimpleNamespace(returncode=0))
    monkeypatch.setattr("hermes_cli.gateway._wait_for_launchd_service_pid", lambda *_a, **_k: True)
    result = main_dashboard._restart_launchd_job("gui/501", "operator.dashboard", 4242, ownership_home=home)
    assert result is (home_kind == "owned")
    assert calls == ([["launchctl", "kickstart", "gui/501/operator.dashboard"]] if home_kind == "owned" else [])


def test_auto_inventory_and_reconciliation_only_claim_loki_families():
    units = ["hermes-dashboard.service", "hermes-serve-work.service", "fabric-serve.service",
             "loki-dashboard.service", "loki-serve-work.service", "loki-dashboardd.service"]
    seen = []
    update_cmd_fleet._for_each_systemd_gateway_unit(
        "\n".join(f"{unit} loaded active running" for unit in units),
        process_unit=seen.append, on_unit_timeout=lambda *_a: pytest.fail("unexpected timeout"),
    )
    assert seen == ["loki-dashboard", "loki-serve-work"]
    assert update_inventory._serve_unit_matches_profile("default", "user/loki-dashboard")
    assert update_inventory._serve_unit_matches_profile("work", "loki-serve-work.service")
    assert not update_inventory._serve_unit_matches_profile("work", "hermes-serve-work.service")
    assert not update_inventory._serve_unit_matches_profile("default", "hermes-dashboard.service")


@pytest.mark.parametrize("entry", ["loki", "/own/bin/loki", r"C:\own\loki.exe", "hermes"])
def test_holder_classifier_recognizes_loki_and_preserves_legacy_safety(entry):
    from hermes_cli.update_cmd_windows import _hermes_holder_subcommand
    assert _hermes_holder_subcommand(f'"{entry}" --profile work serve --port 9119') == "serve"


@pytest.mark.parametrize("entry", ["hermes", "/foreign/bin/hermes", "fabric", "acme-fabric", r"C:\foreign\other-fabric.exe"])
def test_foreign_public_backend_is_not_owned_even_with_loki_environment(entry, owned_home, monkeypatch):
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: {
        "HOME": owned_home, "HERMES_HOME": owned_home, "LOKI_HOME": owned_home, "__LOKI_ENV_BOUND": "1",
    })
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: [entry, "serve"])
    assert dashboard_procs._hermes_home_for_pid(4242) is None
    assert dashboard_procs._pids_owned_by_hermes_home([4242], owned_home) == []


def test_python_script_launcher_does_not_hide_foreign_public_entry(owned_home, monkeypatch):
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: {
        "HERMES_HOME": owned_home, "LOKI_HOME": owned_home, "__LOKI_ENV_BOUND": "1",
    })
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: [
        "python3", "-u", "-X", "utf8", "/foreign/bin/hermes", "serve",
    ])
    assert dashboard_procs._hermes_home_for_pid(4242) is None


@pytest.mark.platforms("windows")
def test_windows_public_default_is_loki(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: {"LOCALAPPDATA": str(tmp_path)})
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: ["loki.exe", "serve"])
    assert dashboard_procs._hermes_home_for_pid(4242) == str(tmp_path / "loki")


@pytest.mark.platforms("posix")
def test_public_suffix_home_does_not_belong_to_unsuffixed_default(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: {
        "HOME": str(tmp_path), "LOKI_DATA_DIR_SUFFIX": "-work", "HERMES_DATA_DIR_SUFFIX": "-foreign",
    })
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: ["loki", "serve"])
    assert dashboard_procs._hermes_home_for_pid(4242) == str(tmp_path / ".loki-work")
    assert dashboard_procs._pids_owned_by_hermes_home([4242], str(tmp_path / ".loki")) == []


def test_public_loki_replays_fresh_home_boundary_and_bound_profile(owned_home, monkeypatch):
    env = {"LOKI_HOME": owned_home, "HERMES_HOME": owned_home + "-foreign"}
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: env)
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: ["loki", "serve"])
    assert dashboard_procs._hermes_home_for_pid(4242) == owned_home
    env.update(__LOKI_ENV_BOUND="1", HERMES_HOME=owned_home + "/profiles/work")
    assert dashboard_procs._hermes_home_for_pid(4242) == owned_home + "/profiles/work"


def test_shared_internal_module_needs_bound_child_or_verified_own_ledger(owned_home, monkeypatch):
    env = {"HERMES_HOME": owned_home, "LOKI_HOME": owned_home}
    monkeypatch.setattr(dashboard_procs, "_pid_environ", lambda _pid: env)
    monkeypatch.setattr(main_dashboard, "_dashboard_cmdline_for_pid", lambda _pid: ["python", "-m", "hermes_cli.main", "serve"])
    monkeypatch.setattr("hermes_cli.process_identity.ledger_entries", lambda **_k: [])
    assert dashboard_procs._hermes_home_for_pid(4242) is None
    def verified_ledger(**kwargs):
        assert kwargs == {"verified_only": True}
        return [{"pid": 4242, "purpose": "serve", "hermes_home": owned_home}]

    monkeypatch.setattr("hermes_cli.process_identity.ledger_entries", verified_ledger)
    assert dashboard_procs._hermes_home_for_pid(4242) == owned_home
    env["__LOKI_ENV_BOUND"] = "1"
    monkeypatch.setattr("hermes_cli.process_identity.ledger_entries", lambda **_k: [])
    assert dashboard_procs._hermes_home_for_pid(4242) == owned_home


@pytest.mark.parametrize("name", ["loki-serve-fabric.service", "loki-dashboard-hermes.service",
                                  "com.obliviousodin.loki.dashboard.fabric"])
def test_owned_namespace_does_not_reject_profile_names(name):
    assert main_dashboard._foreign_backend_service(name) is False


def test_stopped_unit_public_home_declaration_overrides_internal_home(owned_home, monkeypatch):
    from hermes_cli import update_fleet_scope
    monkeypatch.setattr(update_cmd_fleet, "_unit_main_pid", lambda *_a: 0)
    monkeypatch.setattr(update_cmd_fleet, "_systemctl", lambda *_a, **_k: SimpleNamespace(
        returncode=0, stdout=f'HERMES_HOME="{owned_home}" LOKI_HOME="{owned_home}-foreign"',
    ))
    assert update_fleet_scope.systemd_unit_hermes_home(["systemctl", "--user"], "loki-serve") == owned_home + "-foreign"
    assert update_fleet_scope.systemd_unit_in_update_scope(["systemctl", "--user"], "loki-serve") is False


def test_launchd_public_home_declaration_does_not_adopt_foreign_plist(owned_home, monkeypatch, tmp_path):
    import plistlib
    from pathlib import Path
    from hermes_cli import update_fleet_scope
    label = "com.obliviousodin.loki.gateway"
    plist = tmp_path / f"{label}.plist"
    plist.write_bytes(plistlib.dumps({"EnvironmentVariables": {
        "HERMES_HOME": owned_home, "LOKI_HOME": owned_home + "-foreign",
    }}))
    monkeypatch.setattr("hermes_cli.gateway.get_launchd_plist_path", lambda: Path(plist))
    assert update_fleet_scope.launchd_label_foreign_home(label) == owned_home + "-foreign"
