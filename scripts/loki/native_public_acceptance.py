"""Download and exercise an already published unsigned preview without rebuilding it."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.loki import native_preview as preview
from scripts.loki.public_source_acceptance import API, checksum_rows, fetch, validate_release


def read_metadata(url: str, path: Path) -> dict:
    fetch(url, path)
    return json.loads(path.read_bytes())


def public_release(output: Path, *, release_id: int, commit: str, version: str) -> dict:
    release = read_metadata(f"{API}/releases/{release_id}", output / "release.json")
    tag = "v" + version
    ref = read_metadata(f"{API}/git/ref/tags/{quote(tag, safe='')}", output / "tag.json")["object"]
    for index in range(4):
        if ref["type"] == "commit":
            break
        if ref["type"] != "tag" or not re.fullmatch(r"[a-f0-9]{40}", ref["sha"]):
            raise ValueError("Unsupported published tag")
        ref = read_metadata(f"{API}/git/tags/{ref['sha']}", output / f"tag-{index}.json")["object"]
    if (release.get("id") != release_id or release.get("url") != f"{API}/releases/{release_id}"
            or release.get("draft") is not False or release.get("prerelease") is not True
            or release.get("tag_name") != tag or ref.get("type") != "commit" or ref.get("sha") != commit):
        raise ValueError("Exact published owned prerelease and source tag required")
    return release


def download_asset(release: dict, name: str, output: Path) -> Path:
    # Validate the basename before joining it to the owned output directory.
    checksum_rows("0" * 64 + "  " + name)
    rows = [row for row in release["assets"] if row.get("name") == name]
    if len(rows) != 1:
        raise ValueError("Required public asset missing or duplicated")
    row = rows[0]
    url = f"https://github.com/{preview.REPOSITORY}/releases/download/{quote(release['tag_name'], safe='')}/{name}"
    if (row.get("browser_download_url") != url or type(row.get("size")) is not int
            or not 0 < row["size"] < preview.MAX_ASSET
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", str(row.get("digest", "")))):
        raise ValueError("Exact owned asset URL, size and mandatory API digest required")
    if shutil.disk_usage(output).free < row["size"] + 1024 ** 3:
        raise ValueError("Insufficient public download capacity")
    path = output / name
    fetch(url, path, max_bytes=row["size"])
    if path.stat().st_size != row["size"] or "sha256:" + preview.digest(path) != row["digest"]:
        raise ValueError("Public asset bytes differ from the release API")
    return path


def acquire_source(release: dict, directory: Path, *, source: Path, commit: str, version: str) -> dict:
    directory.mkdir()
    for name in ("LOKI-PREVIEW.json", "SHA256SUMS"):
        download_asset(release, name, directory)
    sums = checksum_rows((directory / "SHA256SUMS").read_text(encoding="utf-8-sig"))
    if len(sums) != 8 or sums.get("LOKI-PREVIEW.json") != preview.digest(directory / "LOKI-PREVIEW.json"):
        raise ValueError("Exact eight source checksum rows required")
    for name in sums.keys() - {"LOKI-PREVIEW.json"}:
        download_asset(release, name, directory)
    companions = preview.source_manifest(directory, commit)
    if companions["version"] != version:
        raise ValueError("Published source version differs from admitted source")
    comparison = read_metadata(f"{API}/compare/{commit}...main", directory / "ancestry.json")
    metadata = json.loads((directory / "LOKI-PREVIEW.json").read_bytes())
    validate_release(release, metadata, tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8-sig"))["project"],
                     json.loads((source / "docs/loki/UPSTREAM.json").read_bytes()), comparison,
                     tag="v" + version, commit=commit, peeled=commit)
    return companions


def acquire_native(release: dict, directory: Path, *, commit: str, version: str, expected_proof: str) -> tuple[Path, dict]:
    directory.mkdir()
    for name in ("NATIVE-PREVIEW.json", "NATIVE-SHA256SUMS"):
        download_asset(release, name, directory)
    if preview.digest(directory / "NATIVE-PREVIEW.json") != expected_proof:
        raise ValueError("Published native proof differs from the independently accepted staging digest")
    proof = json.loads((directory / "NATIVE-PREVIEW.json").read_bytes())
    if (proof.get("commit") != commit or proof.get("version") != version or proof.get("architecture") != "arm64"
            or proof.get("signed") is not False or proof.get("installed_cli_and_loopback_mock") != "passed"
            or proof.get("privacy", {}).get("status") != "passed"):
        raise ValueError("Passed exact-source unsigned staging proof required")
    sums = checksum_rows((directory / "NATIVE-SHA256SUMS").read_text(encoding="utf-8-sig"))
    archives = [name for name in sums if re.fullmatch(r"UNSIGNED-PREVIEW-[A-Za-z0-9._+-]+\.zip", name)]
    if len(archives) != 1 or set(sums) != {"NATIVE-PREVIEW.json", archives[0], archives[0] + ".blockmap"}:
        raise ValueError("Exact three native checksum rows required")
    for name in sums.keys() - {"NATIVE-PREVIEW.json"}:
        download_asset(release, name, directory)
    if any(preview.digest(directory / name) != value for name, value in sums.items()):
        raise ValueError("Published native checksums differ from downloaded bytes")
    archive = directory / archives[0]
    if preview.digest(archive) != proof.get("native_zip_sha256"):
        raise ValueError("Published ZIP differs from accepted staging")
    return archive, proof


def accept(args) -> None:
    from hermes_platform.host.facts import os_family, process_arch
    from scripts.loki.native_preview_scan import scan
    if os_family() != "darwin" or process_arch() != "arm64":
        raise ValueError("Actual native macOS arm64 is required")
    version = preview.source_identity(args.source, args.commit)
    args.output.mkdir(exist_ok=False)
    release = public_release(args.output, release_id=args.release_id, commit=args.commit, version=version)
    companions = acquire_source(release, args.output / "source-assets", source=args.source, commit=args.commit, version=version)
    archive, proof = acquire_native(release, args.output / "native-assets", commit=args.commit, version=version,
                                    expected_proof=args.native_manifest_sha256)
    privacy = scan(archive, commit=args.commit, build_roots=[args.source, args.output], scratch=args.output)
    from pm import installed_package
    selected = installed_package("node")
    if selected is None or selected.binary is None:
        raise ValueError("Verified pinned PM Node prerequisite missing")
    node = selected.binary
    measured = preview.accept_archive(archive, source=args.source, commit=args.commit, version=version,
                                      output=args.output, node=node, expected_notices=proof["notices"])
    preview.source_identity(args.source, args.commit)
    after = args.output / "release-after"
    after.mkdir()
    final_release = public_release(after, release_id=args.release_id, commit=args.commit, version=version)
    def inventory(value):
        return {row["id"]: (row["name"], row["size"], row.get("digest")) for row in value["assets"]}
    if inventory(final_release) != inventory(release):
        raise ValueError("Published release assets changed during acceptance")
    for directory in (args.output / "source-assets", args.output / "native-assets"):
        for path in directory.iterdir():
            if path.name == "ancestry.json":
                continue
            rows = [row for row in release["assets"] if row["name"] == path.name]
            if len(rows) != 1 or "sha256:" + preview.digest(path) != rows[0]["digest"]:
                raise ValueError("Downloaded immutable companion changed during acceptance")
    result = {"status": "passed", "commit": args.commit, "version": version, "release_id": args.release_id,
              "source_assets": companions["assets"], "native_assets": {path.name: preview.digest(path) for path in archive.parent.iterdir()},
              "native_staging_proof_sha256": args.native_manifest_sha256, "notices": measured, "privacy": privacy,
              "anonymous_published_download": "passed", "installed_cli_and_loopback_mock": "passed",
              "scope": "unsigned macOS arm64 installed components; no app rebuild or release mutation",
              "human_gui_quarantine_signing_live_provider_actual_update_ssh": "not qualified"}
    (args.output / "PUBLIC-NATIVE-ACCEPTANCE.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release-id", required=True, type=int)
    parser.add_argument("--native-manifest-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (os.environ.get("GITHUB_REPOSITORY") != preview.REPOSITORY or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        parser.error("Only this repository's token-free manual main workflow on a hosted runner is admitted")
    if args.release_id <= 0 or not re.fullmatch(r"[a-f0-9]{64}", args.native_manifest_sha256):
        parser.error("Explicit release ID and accepted staging proof SHA-256 required")
    accept(args)


if __name__ == "__main__":
    main()
