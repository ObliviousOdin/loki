"""Local compiler receipts must not expose build paths in assembled frontends."""
from __future__ import annotations

import pytest

from scripts.build.agent import plant_surfaces


@pytest.mark.parametrize("product", ["tui", "web"])
def test_distribution_copy_retains_runtime_bytes_without_local_build_receipt(tmp_path, product):
    prepared = tmp_path / "build host with private name" / product
    built = prepared / "dist" if product == "tui" else prepared
    built.mkdir(parents=True)
    runtime = "entry.js" if product == "tui" else "index.html"
    (built / runtime).write_bytes(b"runtime product bytes\n")
    if product == "tui":
        (prepared / "package.json").write_bytes(b'{"type":"module"}\n')
    receipt = built / "hermes-build.json"
    receipt.write_text('{"inputs":{"prepared":[{"path":"' + str(prepared) + '"}]}}\n')
    assets = built / "assets"
    assets.mkdir()
    (assets / "NOTICE.txt").write_bytes(b"Required supplier attribution\n")
    (assets / "hermes-build.json").write_bytes(b"A public asset with the same basename\n")
    before = {p.relative_to(prepared): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}
    destination = tmp_path / "relocatable payload"

    plant_surfaces(destination, {product: prepared})

    shipped = destination / "hermes_cli" / ("tui_dist" if product == "tui" else "web_dist")
    assert not (shipped / "hermes-build.json").exists(), "Local input paths are not distribution metadata"
    assert (shipped / runtime).read_bytes() == b"runtime product bytes\n"
    assert (shipped / "assets/NOTICE.txt").read_bytes() == b"Required supplier attribution\n"
    assert (shipped / "assets/hermes-build.json").read_bytes() == b"A public asset with the same basename\n"
    if product == "tui":
        assert (shipped / "package.json").read_bytes() == b'{"type":"module"}\n'
    assert before == {p.relative_to(prepared): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}

    receipt.write_text("later local build provenance")
    plant_surfaces(destination, {product: prepared})
    assert not (shipped / "hermes-build.json").exists()
