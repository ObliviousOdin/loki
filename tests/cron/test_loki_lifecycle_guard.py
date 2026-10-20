"""Loki's public commands and services retain the inherited hard lifecycle block."""
import pytest

from cron import lifecycle_guard as guard


@pytest.mark.parametrize("command", [
    "loki gateway restart",
    "loki.exe gateway stop",
    "loki.cmd gateway uninstall",
    "systemctl --user restart loki-gateway.service",
    "launchctl bootout gui/501/com.obliviousodin.loki.gateway",
    "launchctl kick\"start\" -k gui/501/com.obliviousodin.loki.gateway.work",
    "label=com.obliviousodin.loki.gateway; launchctl disable gui/501/$label",
    "pkill -f 'loki gateway run'",
    "pkill -f 'python loki.py gateway run'",
])
def test_loki_commands_are_blocked_before_cron_creation(command):
    assert guard.contains_gateway_lifecycle_command(command)
    with pytest.raises(guard.GatewayLifecycleBlocked):
        guard.check_gateway_lifecycle(command)


@pytest.mark.parametrize("brand", ["hermes", "loki", "loki.exe"])
def test_profile_commands_block_only_the_current_gateway(monkeypatch, brand):
    monkeypatch.setattr(guard, "_current_profile_name", lambda: "work")
    assert guard.contains_gateway_lifecycle_command(f"{brand} -p work gateway restart")
    assert not guard.contains_gateway_lifecycle_command(f"{brand} -p sibling gateway restart")


@pytest.mark.parametrize("command", [
    "loki gateway status",
    "loki gateway start",
    "launchctl print gui/501/com.obliviousodin.loki.gateway",
    "launchctl disable gui/501/com.obliviousodin.loki.update-checker",
    "/docs/loki gateway restart-notes.md",
])
def test_non_lifecycle_loki_operations_remain_available(command):
    assert not guard.contains_gateway_lifecycle_command(command)
