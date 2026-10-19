"""Supervisor identity uses the environment the actual Loki child will bind."""
import pytest

from hermes_cli.gateway_runtime_service_identity import verify_launchd_plist


def _definition(environment):
    return {"Label": "com.obliviousodin.loki.gateway", "ProgramArguments": ["loki", "gateway", "run"],
            "EnvironmentVariables": environment}


def test_fresh_supervisor_uses_public_home_and_ignores_foreign_hermes(tmp_path):
    own, foreign = tmp_path / ".loki", tmp_path / ".hermes"
    verify_launchd_plist(_definition({"LOKI_HOME": str(own), "LOKI_SUPERVISED_CHILD": "1",
                                     "HERMES_HOME": str(foreign)}), "com.obliviousodin.loki.gateway", own)


@pytest.mark.parametrize("environment", [
    {"HERMES_HOME": "own", "HERMES_SUPERVISED_CHILD": "1"},
    {"LOKI_HOME": "foreign", "LOKI_SUPERVISED_CHILD": "1", "HERMES_HOME": "own"},
])
def test_fresh_supervisor_refuses_internal_only_or_foreign_public_identity(tmp_path, environment):
    values = {key: str(tmp_path / value) if value in {"own", "foreign"} else value
              for key, value in environment.items()}
    with pytest.raises(ValueError):
        verify_launchd_plist(_definition(values), "com.obliviousodin.loki.gateway", tmp_path / "own")


def test_explicit_bound_owned_child_keeps_its_internal_profile(tmp_path):
    verify_launchd_plist(_definition({"__LOKI_ENV_BOUND": "1", "HERMES_HOME": str(tmp_path),
                                     "HERMES_SUPERVISED_CHILD": "1", "LOKI_HOME": str(tmp_path / "stale")}),
                        "com.obliviousodin.loki.gateway", tmp_path)


def test_foreign_hermes_record_cannot_claim_a_loki_gateway(monkeypatch):
    from gateway import status

    monkeypatch.setattr(status, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(status, "_get_process_start_time", lambda pid: 1000)
    monkeypatch.setattr(status, "_read_process_cmdline", lambda pid: "hermes gateway run")
    foreign = {"pid": 4242, "kind": "hermes-gateway", "start_time": 1000,
               "argv": ["hermes", "gateway", "run"], "gateway_state": "running"}
    assert status.get_runtime_status_running_pid(foreign) is None
