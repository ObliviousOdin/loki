"""Native payloads expose Loki launchers while legacy manifest readers remain compatible."""

import json

import pytest

from pm.environments import cli_command_name, payload_command_dir


@pytest.mark.parametrize("commands,expected", [
    ({"loki": "bin/loki"}, "loki"),
    ({"hermes": "bin/legacy-hermes"}, "legacy-hermes"),
    ({"loki": "bin/loki", "hermes": "bin/legacy-hermes"}, "loki"),
])
def test_payload_command_names_follow_the_manifest(tmp_path, commands, expected):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "repo": "repo", "venv": "venv", "store": "tools", "runtime": {"commands": commands},
    }), encoding="utf-8")
    assert payload_command_dir(repo) == tmp_path / "bin"
    assert cli_command_name(repo) == expected
