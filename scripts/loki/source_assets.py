"""Stage the exact Pilk source and notices declared by a Loki release tree."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tarfile
import tomllib
from urllib.parse import urlparse
from urllib.request import urlopen

VERSION = "0.2.4"
ARCHIVE = f"pilk-{VERSION}.tar.gz"
LICENSE = f"PILK-{VERSION}-LICENSE.txt"
CODEC_NOTICE = "PILK-SILK-CODEC-NOTICES.txt"


def pilk_pin(lock: bytes) -> dict:
    rows = [row for row in tomllib.loads(lock.decode("utf-8"))["package"] if row["name"] == "pilk"]
    if len(rows) != 1 or rows[0]["version"] != VERSION:
        raise ValueError("Review Pilk source and notices when the locked version changes")
    source = rows[0]["sdist"]
    url, size, digest = source["url"], source["size"], source["hash"]
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org"
            or Path(parsed.path).name != ARCHIVE or parsed.query or parsed.fragment
            or not isinstance(size, int) or not 0 < size <= 16 * 1024 * 1024
            or not digest.startswith("sha256:") or len(digest) != 71):
        raise ValueError("Pilk source must have a bounded HTTPS sdist and SHA-256 lock pin")
    int(digest[7:], 16)
    return {"package": "pilk", "version": VERSION, "url": url,
            "sha256": digest[7:], "bytes": size, "source_asset": ARCHIVE,
            "license_asset": LICENSE, "codec_notice_asset": CODEC_NOTICE}


def _verify_source(data: bytes, pin: dict, license_bytes: bytes, codec_notice: bytes) -> None:
    if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise ValueError("Pilk source does not match the declared lock hash and size")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        license_file = archive.extractfile(f"pilk-{VERSION}/LICENSE")
        codec_file = archive.extractfile(f"pilk-{VERSION}/src/interface/SKP_Silk_SDK_API.h")
        if license_file is None or license_file.read() != license_bytes:
            raise ValueError("Pilk license asset differs from the exact source archive")
        body = codec_notice[codec_notice.index(b"/*"):].strip()
        body = b"\n".join(line.rstrip(b" \t") for line in body.splitlines())
        code = (b"\n".join(line.rstrip(b" \t") for line in codec_file.read().splitlines())
                if codec_file is not None else b"")
        if body not in code:
            raise ValueError("Pilk codec notice differs from the exact source archive")


def stage_pilk_source(out: Path, *, lock: bytes, license_bytes: bytes,
                      codec_notice: bytes, source: Path | None = None) -> dict:
    """Copy verified unmodified bytes; never extract source or execute its build."""
    pin = pilk_pin(lock)
    if source is None:
        with urlopen(pin["url"], timeout=60) as response:
            data = response.read(pin["bytes"] + 1)
    else:
        with source.open("rb") as stream:
            data = stream.read(pin["bytes"] + 1)
    _verify_source(data, pin, license_bytes, codec_notice)
    for name, payload in ((ARCHIVE, data), (LICENSE, license_bytes), (CODEC_NOTICE, codec_notice)):
        with (out / name).open("xb") as target:
            target.write(payload)
    return pin
