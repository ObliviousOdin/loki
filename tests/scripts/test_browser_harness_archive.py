"""The private source archive must remain reproducible and reject unsafe inputs."""

import importlib.util
import io
from pathlib import Path
import shutil
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[2] / "vendor" / "browser-harness"
SPEC = importlib.util.spec_from_file_location("loki_browser_archive", ROOT / "archive.py")
assert SPEC is not None and SPEC.loader is not None
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


def test_selected_archive_rebuilds_and_rejects_changed_artifact(tmp_path):
    result = archive.check_archive()
    assert result["version"] == "0.1.13+loki.1"
    assert archive.build_archive() == (ROOT / archive.ARCHIVE).read_bytes()
    copied = tmp_path / "vendor"
    shutil.copytree(ROOT, copied)
    path = copied / archive.ARCHIVE
    path.write_bytes(path.read_bytes() + b"unreviewed")
    with pytest.raises(ValueError, match="deterministic corresponding source"):
        archive.check_archive(copied, ROOT.parent.parent)


def test_source_archive_must_be_regular_and_match_official_supplier(tmp_path):
    copied = tmp_path / "vendor"
    shutil.copytree(ROOT, copied)
    original = copied / archive.UPSTREAM_ARCHIVE
    original.write_bytes(original.read_bytes() + b"unreviewed")
    with pytest.raises(ValueError, match="admitted official archive"):
        archive.package_files(copied)
    original.unlink()
    original.symlink_to(ROOT / archive.UPSTREAM_ARCHIVE)
    with pytest.raises(ValueError, match="Symlink package input"):
        archive.package_files(copied)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("package/../escape", tarfile.REGTYPE),
        ("package/drive:C", tarfile.REGTYPE),
        ("package/back\\slash", tarfile.REGTYPE),
        ("package/link", tarfile.SYMTYPE),
        ("package/link", tarfile.LNKTYPE),
        ("package/member", tarfile.REGTYPE),
    ],
)
def test_member_reader_rejects_paths_links_and_duplicates(name, kind):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as output:
        first = tarfile.TarInfo("package/member")
        output.addfile(first, io.BytesIO())
        rejected = tarfile.TarInfo(name)
        rejected.type = kind
        rejected.linkname = "../outside"
        output.addfile(rejected, io.BytesIO())
    with pytest.raises(ValueError):
        archive.source_members(data.getvalue(), "package")
