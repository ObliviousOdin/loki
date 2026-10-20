"""The real swap uses the build's declared Loki variant, leaving other bundles alone."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("display_name", ["Loki", "Loki Source", "Loki Light", "Loki Source abc1234", "Hermes"])
def test_swap_selects_declared_owned_bundle(tmp_path, display_name):
    script = Path(__file__).resolve().parents[3] / "scripts/desktop-update/posix.sh"
    source = script.read_text(encoding="utf-8")
    real_swap = source[source.index("mac_swap() {"):source.index("\ndeliver_outcome() {")]
    assert shutil.which("node"), "the desktop build runtime must supply Node"
    install = tmp_path / "checkout"
    desktop = install / "apps/desktop"
    release = desktop / "release/mac-arm64"
    release.mkdir(parents=True)
    (desktop / "product-identity.cjs").write_text(
        "module.exports = {displayName: " + json.dumps(display_name) + "};\n", encoding="utf-8")
    built = release / (display_name + ".app")
    built.mkdir()
    (built / "version").write_text("new", encoding="utf-8")
    foreign = release / "Hermes.app"
    foreign.mkdir(exist_ok=True)
    (foreign / "preserve").write_text("foreign", encoding="utf-8")
    target = tmp_path / "Applications/owned.app"
    target.mkdir(parents=True)
    (target / "version").write_text("old", encoding="utf-8")
    copy = tmp_path / "copy-bundle"
    copy.write_text('#!/bin/sh\nexec cp -R "$1" "$2"\n', encoding="utf-8")
    copy.chmod(0o755)
    harness = real_swap + "\n" + "\n".join([
        'run_bounded() { shift; "$@"; }',
        'publish_stage() { :; }; mac_bundle_recover() { :; }; swap_checkpoint() { :; }',
        'add_warning() { printf "%s\\n" "$*" >&2; }; log() { :; }',
        'FINAL_CODE=0 APP_REBUILD_FAILED=0',
        'INSTALL_ROOT=' + shlex.quote(str(install)),
        'RELAUNCH_TARGET=' + shlex.quote(str(target)),
        'MAC_DITTO=' + shlex.quote(str(copy)),
        'mac_swap',
    ])
    driver = tmp_path / "swap-fixture.sh"
    driver.write_text(harness, encoding="utf-8")
    result = subprocess.run(["/bin/bash", str(driver)], cwd=tmp_path, env=os.environ.copy(),
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "version").read_text(encoding="utf-8") == ("old" if display_name == "Hermes" else "new")
    assert (foreign / "preserve").read_text(encoding="utf-8") == "foreign"
    assert not target.with_name(target.name + ".old").exists()
    assert not target.with_name(target.name + ".new").exists()
