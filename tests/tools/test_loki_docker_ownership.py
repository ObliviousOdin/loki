"""A protocol double proves Docker lifecycle queries cannot select Hermes resources."""
import datetime
import subprocess

import pytest


@pytest.fixture
def daemon(monkeypatch):
    from tools.environments import docker
    containers = {
        "hermes-old": {"hermes-agent": "1", "hermes-profile": "default", "hermes-task-id": "task", "hermes-egress": "off"},
        "loki-old": {"loki-agent": "1", "hermes-profile": "default", "hermes-task-id": "task", "hermes-egress": "off"},
    }
    removed = []

    def query(command, **kwargs):
        if command[1] == "ps":
            filters = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "--filter"]
            matching = list(containers)
            for clause in filters:
                if clause.startswith("label="):
                    key, value = clause[6:].split("=", 1)
                    matching = [cid for cid in matching if containers[cid].get(key) == value]
            fmt = command[command.index("--format") + 1]
            suffix = "\texited" if "{{.State}}" in fmt else "\told-image" if "{{.Image}}" in fmt else ""
            return subprocess.CompletedProcess(command, 0, "".join(cid + suffix + "\n" for cid in matching), "")
        if command[1] == "inspect":
            stamp = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
            return subprocess.CompletedProcess(command, 0, stamp.isoformat(), "")
        if command[1] == "rm":
            removed.append(command[-1])
            del containers[command[-1]]
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    monkeypatch.setattr(docker, "_docker_query", query)
    return containers, removed


def test_orphan_reaper_removes_only_loki_containers(daemon):
    from tools.environments.docker import reap_orphan_containers
    containers, removed = daemon
    assert reap_orphan_containers(profile_filter="default", docker_exe="docker") == 1
    assert removed == ["loki-old"]
    assert "hermes-old" in containers


def test_reuse_even_without_a_home_filter_selects_only_loki(daemon):
    from tools.environments.docker import DockerEnvironment
    env = DockerEnvironment.__new__(DockerEnvironment)
    env._docker_exe, env._labels = "docker", {}
    assert env._find_reusable_container("task", "default", "off") == ("loki-old", "exited")


def test_image_switch_probe_ignores_foreign_containers(daemon, monkeypatch):
    from hermes_cli import config, sandbox_image_switch
    from tools.environments import docker
    monkeypatch.setattr(config, "load_config_readonly", lambda: {"terminal": {"backend": "docker", "docker_image": "new-image"}})
    monkeypatch.setattr(sandbox_image_switch, "_image_pinned", lambda _: False)
    monkeypatch.setattr(docker, "find_docker", lambda: "docker")
    switch = sandbox_image_switch.pending()
    assert switch.containers == ["loki-old"]
