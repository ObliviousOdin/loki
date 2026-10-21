"""Sealed builds retain dependency bytes without build-machine URL provenance."""

import base64
import csv
import hashlib
import io
import json
import subprocess
from zipfile import ZipFile

import pm
from tests.pm._fixtures import (
    build_worker as build_worker,  # noqa: PLC0414 -- imported pytest fixture
    client as client,  # noqa: PLC0414 -- imported pytest fixture
    isolated_python as isolated_python,  # noqa: PLC0414 -- imported pytest fixture
)


def _wheel(path):
    dist = "local_fixture-1.0.dist-info"
    files = {
        "local_fixture.py": b"VALUE = 'installed runtime canary'\n",
        f"{dist}/METADATA": b"Metadata-Version: 2.4\nName: local-fixture\nVersion: 1.0\nLicense-File: licenses/LICENSE\n",
        f"{dist}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist}/licenses/LICENSE": b"Synthetic supplier license canary\n",
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record)
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", str(len(data))])
    writer.writerow([f"{dist}/RECORD", "", ""])
    with ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr(f"{dist}/RECORD", record.getvalue())


def _assert_record(site, record):
    for name, digest, size in csv.reader(io.StringIO(record, newline="")):
        if not digest:
            assert name.endswith(".dist-info/RECORD")
            continue
        content = (site / name).read_bytes()
        assert int(size) == len(content)
        algorithm, encoded = digest.split("=", 1)
        assert algorithm == "sha256"
        assert base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode() == encoded


def test_actual_offline_pm_build_strips_local_provenance_only_when_sealed(tmp_path, build_worker):
    wheel = tmp_path / "local_fixture-1.0-py3-none-any.whl"
    _wheel(wheel)
    original = wheel.read_bytes()
    records = {}
    for sealed in (False, True):
        out = tmp_path / ("sealed" if sealed else "unsealed")
        python = pm.build_requirements_environment(
            [f"local-fixture @ {wheel.as_uri()}"], out=out, cache=tmp_path / "cache", offline=True,
            sealed=sealed, explicit=True,
        )
        sites = [*out.glob("lib/python*/site-packages"), *out.glob("Lib/site-packages")]
        assert len(sites) == 1
        site = sites[0]
        info = site / "local_fixture-1.0.dist-info"
        direct = info / "direct_url.json"
        if sealed:
            assert not direct.exists(), "sealed metadata still discloses the build-machine archive URL"
        else:
            assert json.loads(direct.read_bytes())["url"] == wheel.as_uri()
        assert (info / "licenses/LICENSE").read_bytes() == b"Synthetic supplier license canary\n"
        records[sealed] = (info / "RECORD").read_bytes()
        _assert_record(site, records[sealed].decode())
        probe = subprocess.run(
            [str(python), "-I", "-B", "-c", "import local_fixture; print(local_fixture.VALUE)"],
            cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30,
        )
        assert probe.stdout.strip() == "installed runtime canary"
    assert records[True] == b"".join(
        line for line in records[False].splitlines(keepends=True) if b"/direct_url.json," not in line
    )
    assert wheel.read_bytes() == original


def test_remote_provenance_and_nonselected_record_bytes_stay_intact(tmp_path):
    from pm.sealed_metadata import prune_local_direct_urls

    site = tmp_path / "venv/lib/python3.14/site-packages"
    local = site / "local_fixture-1.0.dist-info"
    remote = site / "remote_fixture-1.0.dist-info"
    local.mkdir(parents=True)
    remote.mkdir()
    local_url = b'{"url":"file:///private/build/local.whl","archive_info":{}}'
    remote_url = b'{"url":"https://example.invalid/supplier.whl","archive_info":{"hash":"sha256=123"}}\n'
    (local / "direct_url.json").write_bytes(local_url)
    (remote / "direct_url.json").write_bytes(remote_url)
    retained = b'"unrelated,file",sha256=unchanged,1\r\nlocal_fixture-1.0.dist-info/RECORD,,\r\n'
    record = b'local_fixture-1.0.dist-info/direct_url.json,sha256=removed,1\r\n' + retained
    backing = tmp_path / "cache-record-canary"
    backing.write_bytes(record)
    (local / "RECORD").hardlink_to(backing)
    remote_record = b'remote_fixture-1.0.dist-info/direct_url.json,sha256=untouched,1\r\n'
    (remote / "RECORD").write_bytes(remote_record)

    assert prune_local_direct_urls(tmp_path / "venv") == 1

    assert not (local / "direct_url.json").exists()
    assert (local / "RECORD").read_bytes() == retained
    assert backing.read_bytes() == record
    assert (remote / "direct_url.json").read_bytes() == remote_url
    assert (remote / "RECORD").read_bytes() == remote_record
