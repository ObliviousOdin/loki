"""Prepared catalog resources use the existing package-manager binding.

These execute the assembler and a host Python entrypoint, not Nix evaluation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.scripts.test_agent_build import build_cli, inputs_fixture

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.platforms("posix")
def test_referenced_catalog_binding_reaches_runtime_and_public_override_wins(tmp_path):
    _prepared, data = inputs_fixture(tmp_path)
    output = tmp_path / "referenced output"
    catalog = tmp_path / "immutable catalog"
    catalog.mkdir()
    declaration = (
        "name: honcho\nrepo: https://github.com/ObliviousOdin/loki\n"
        f"sha: {'1' * 40}\nsubdir: optional-plugins/honcho\n"
        "description: Owned memory provider\nmaintainer: ObliviousOdin\ncategory: memory\n"
    )
    (catalog / "honcho.yaml").write_text(declaration, encoding="utf-8")
    foreign = tmp_path / "foreign catalog"
    foreign.mkdir()
    canary = foreign / "honcho.yaml"
    canary.write_bytes(b"foreign catalog must not be selected or changed")
    source = Path(data["code"])
    (source / "entry.py").write_text(
        "import json\nfrom pathlib import Path\n"
        "from loki_identity import bind_loki_environment\n"
        "from hermes_cli.plugin_catalog import get_catalog_dir, load_catalog\n"
        "def main():\n"
        " bind_loki_environment()\n"
        " catalog=get_catalog_dir()\n"
        " entries=load_catalog()\n"
        " print(json.dumps([str(catalog),[[entry.name,entry.repo,entry.subdir] for entry in entries]]))\n",
        encoding="utf-8")
    bindir = tmp_path / "installed commands"
    bindir.mkdir()
    command = bindir / "probe"
    command.write_text(
        f"#!{sys.executable}\nimport sys\nsys.path[:0]=[{str(source)!r},{str(ROOT)!r}]\n"
        "from entry import main\nmain()\n", encoding="utf-8")
    command.chmod(0o755)
    data.update(placement="references", repo="share/hermes-agent", command_dir=str(bindir))
    data["resources"]["plugin-catalog"] = str(catalog)
    built = build_cli(data, output, tmp_path)
    assert built.returncode == 0, built.stdout + built.stderr
    mapping = json.loads((output / "command-map.json").read_text())
    bound = Path(mapping["env"]["HERMES_BUNDLED_PLUGIN_CATALOG"])
    assert bound.is_symlink() and bound.samefile(catalog)
    home = tmp_path / "fresh home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.defpath,
           "HERMES_BUNDLED_PLUGIN_CATALOG": str(foreign),
           **{"LOKI_" + key.removeprefix("HERMES_"): value
              for key, value in mapping["env"].items() if key.startswith("HERMES_")}}
    ran = subprocess.run([str(command)], cwd=tmp_path, env=env, text=True,
                         capture_output=True, timeout=30, check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert json.loads(ran.stdout) == [str(bound), [["honcho", "https://github.com/ObliviousOdin/loki", "optional-plugins/honcho"]]]
    assert canary.read_bytes() == b"foreign catalog must not be selected or changed"
    assert not (home / ".hermes").exists()


def test_catalog_resource_keeps_source_default_when_wrapper_override_is_absent(tmp_path, monkeypatch):
    from hermes_constants import get_bundled_plugin_catalog_dir

    monkeypatch.delenv("HERMES_BUNDLED_PLUGIN_CATALOG", raising=False)
    source = tmp_path / "source plugin catalog"
    assert get_bundled_plugin_catalog_dir(source) == source
