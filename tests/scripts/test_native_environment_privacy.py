"""Native environment configuration stays portable without editable build paths."""
from __future__ import annotations

import os

import pytest

from scripts.bundles.payload import seal_environment_config


def test_environment_config_retains_runtime_flags_with_relative_interpreter_home(tmp_path):
    payload = tmp_path / "build host with spaces/payload"
    python = payload / "tools/python/bin/python"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"interpreter fixture")
    environment = payload / "venv"
    environment.mkdir()
    cfg = environment / "pyvenv.cfg"
    paths = ("home", "executable", "base-executable", "base-prefix", "base-exec-prefix", "command")
    cfg.write_text("\n".join(f"{key} = {tmp_path}/private source" for key in paths)
                   + "\nversion_info = 3.14.0\ninclude-system-site-packages = false\nrelocatable = true\n")

    seal_environment_config(payload, python, "venv")

    fields = dict(line.split(" = ", 1) for line in cfg.read_text(encoding="utf-8-sig").splitlines())
    assert fields == {"home": os.path.relpath(python.parent, environment), "version_info": "3.14.0",
                      "include-system-site-packages": "false", "relocatable": "true"}
    moved = tmp_path / "installed elsewhere"
    payload.rename(moved)
    assert ((moved / "venv") / fields["home"]).resolve() == moved / "tools/python/bin"
    assert str(tmp_path) not in (moved / "venv/pyvenv.cfg").read_text(encoding="utf-8-sig")


def test_environment_config_rejects_interpreter_outside_payload_without_rewriting(tmp_path):
    payload = tmp_path / "payload"
    (payload / "venv").mkdir(parents=True)
    cfg = payload / "venv/pyvenv.cfg"
    cfg.write_bytes(b"home = preserve original\n")
    python = tmp_path / "foreign-python"
    python.write_bytes(b"foreign canary")
    with pytest.raises(ValueError, match="belong to the payload"):
        seal_environment_config(payload, python, "venv")
    assert cfg.read_bytes() == b"home = preserve original\n"
    assert python.read_bytes() == b"foreign canary"
