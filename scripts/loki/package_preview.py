"""Create exact-commit Loki source/install artifacts without wheel-guard bypasses."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.loki.source_assets import stage_pilk_source
VERSION = "0.1.0-alpha.1"
BASELINE = "18c525b669b6ea4ba62e6967d228af21d89aa9d3"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8",
                                   errors="replace", timeout=120).strip()


def package(out: Path, commit: str, *, pilk_source: Path | None = None) -> dict:
    commit = git("rev-parse", "--verify", f"{commit}^{{commit}}")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Package an admitted clean checkout; do not include local work or secrets")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, commit],
                   cwd=ROOT, check=True, timeout=30)
    project = tomllib.loads(git("show", f"{commit}:pyproject.toml"))["project"]
    if project.get("name") != "obliviousodin-loki-agent" or project.get("version") != "0.1.0a1":
        raise ValueError("The admitted tree is not this Loki preview version")
    pinned = json.loads(git("show", f"{commit}:docs/loki/UPSTREAM.json"))
    if pinned.get("commit") != BASELINE:
        raise ValueError("The admitted tree has a different upstream baseline")
    out.mkdir(parents=True, exist_ok=False)
    def source_bytes(path: str) -> bytes:
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT, timeout=30)

    pilk = stage_pilk_source(
        out, lock=source_bytes("uv.lock"),
        license_bytes=source_bytes("notices/pilk-0.2.4/LICENSE"),
        codec_notice=source_bytes("notices/pilk-0.2.4/SILK-NOTICES.txt"), source=pilk_source,
    )
    prefix = f"loki-{VERSION}/"
    metadata = {"product": "Loki", "version": VERSION, "commit": commit,
                "upstream_commit": BASELINE, "repository": "ObliviousOdin/loki",
                "kind": "source-preview", "signed": False,
                "third_party_sources": [pilk],
                "required_native_companion_assets": [f"loki-{VERSION}-source.tar.gz",
                    pilk["source_asset"], pilk["license_asset"], pilk["codec_notice_asset"],
                    "LOKI-PREVIEW.json", "SHA256SUMS"],
                "native_qualification": "See separately published native receipts"}
    raw_tar = out / "source.tar"
    with raw_tar.open("wb") as stream:
        subprocess.run(["git", "archive", "--format=tar", f"--prefix={prefix}", commit],
                       cwd=ROOT, stdout=stream, check=True, timeout=180)
    payload = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
    with tarfile.open(raw_tar, "a") as archive:
        info = tarfile.TarInfo(prefix + "LOKI-PREVIEW.json")
        info.size, info.mtime, info.mode = len(payload), 0, 0o644
        archive.addfile(info, io.BytesIO(payload))
    artifact = out / f"loki-{VERSION}-source.tar.gz"
    with raw_tar.open("rb") as source, artifact.open("wb") as target:
        with gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as zipped:
            shutil.copyfileobj(source, zipped)
    raw_tar.unlink()
    (out / "LOKI-PREVIEW.json").write_bytes(payload)
    for name in ("install.sh", "install.ps1", "install.cmd"):
        (out / name).write_bytes(subprocess.check_output(["git", "show", f"{commit}:scripts/{name}"],
                                                       cwd=ROOT, timeout=30))
    sums = []
    for path in sorted(out.iterdir()):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        sums.append(f"{digest}  {path.name}\n")
    (out / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pilk-source", type=Path,
                        help="Use an existing sdist only after verifying the declared lock hash and size")
    args = parser.parse_args()
    print(json.dumps(package(args.out.resolve(), args.commit, pilk_source=args.pilk_source), indent=2))


if __name__ == "__main__":
    main()
