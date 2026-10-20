"""Verify an unsigned macOS preview and optionally stage it to an owned draft release."""
from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPSConnection
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tomllib
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPOSITORY = "ObliviousOdin/loki"
MIN_FREE = 13 * 1024 ** 3
MAX_ASSET = 2 * 1024 ** 3


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(command: list[str], **options) -> str:
    timeout = options.pop("timeout", 180)
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                          start_new_session=True, **options) as child:
        try:
            output, _ = child.communicate(timeout=timeout)
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)  # windows-footgun: ok -- Hosted POSIX controller only.
            except ProcessLookupError:
                pass
            child.wait(timeout=15)
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, command, output)
    return output.strip()


def source_identity(source: Path, commit: str) -> str:
    from scripts.bundles.desktop_prepare import require_source
    from scripts.releases.commit_build import require_commit, version_at
    require_source(source, require_commit(commit))
    return version_at(source, commit)


def api(endpoint: str, *, upload: Path | None = None) -> dict:
    token = os.environ.get("GH_TOKEN")
    if not token or not endpoint.startswith(f"repos/{REPOSITORY}/"):
        raise ValueError("Explicit owned GitHub API authorization required")
    connection = HTTPSConnection("uploads.github.com" if upload else "api.github.com", timeout=600 if upload else 60)
    try:
        connection.putrequest("POST" if upload else "GET", "/" + endpoint)
        connection.putheader("Authorization", "Bearer " + token)
        connection.putheader("User-Agent", "Loki-native-preview")
        connection.putheader("Accept", "application/vnd.github+json")
        if upload:
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("Content-Length", str(upload.stat().st_size))
        connection.endheaders()
        if upload:
            with upload.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 ** 2), b""):
                    connection.send(block)
        response = connection.getresponse()
        raw = response.read(8 * 1024 ** 2 + 1)
        if not 200 <= response.status < 300 or len(raw) > 8 * 1024 ** 2:
            raise ValueError("GitHub API refused; retain the current draft without retry or deletion")
        return json.loads(raw)
    finally:
        connection.close()


def validate_draft(release: dict, tag: dict, comparison: dict, *, release_id: int, commit: str, version: str) -> None:
    if (release.get("id") != release_id or release.get("draft") is not True
            or release.get("prerelease") is not True or release.get("tag_name") != "v" + version
            or release.get("url") != f"https://api.github.com/repos/{REPOSITORY}/releases/{release_id}"):
        raise ValueError("An exact owned draft prerelease is required")
    if tag.get("type") != "commit" or tag.get("sha") != commit:
        raise ValueError("Draft release tag does not peel to the admitted commit")
    if (comparison.get("behind_by") != 0 or comparison.get("status") not in {"ahead", "identical"}
            or comparison.get("base_commit", {}).get("sha") != commit
            or comparison.get("merge_base_commit", {}).get("sha") != commit):
        raise ValueError("Native preview commit is outside main ancestry")


def draft(release_id: int, commit: str, version: str) -> dict:
    if release_id <= 0:
        raise ValueError("Explicit positive draft release ID required")
    release = api(f"repos/{REPOSITORY}/releases/{release_id}")
    tag = api(f"repos/{REPOSITORY}/git/ref/tags/{quote('v' + version, safe='')}")["object"]
    for _ in range(4):
        if tag["type"] == "commit":
            break
        if tag["type"] != "tag" or not re.fullmatch(r"[a-f0-9]{40}", tag["sha"]):
            raise ValueError("Unsupported release tag object")
        tag = api(f"repos/{REPOSITORY}/git/tags/{tag['sha']}")["object"]
    comparison = api(f"repos/{REPOSITORY}/compare/{commit}...main")
    validate_draft(release, tag, comparison, release_id=release_id, commit=commit, version=version)
    return release


def source_manifest(directory: Path, commit: str) -> dict:
    from scripts.loki.public_source_acceptance import checksum_rows
    metadata = json.loads((directory / "LOKI-PREVIEW.json").read_bytes())
    if metadata["commit"] != commit or metadata["repository"] != REPOSITORY or metadata["kind"] != "source-preview":
        raise ValueError("Exact source companion metadata required")
    if len(metadata["third_party_sources"]) != 1:
        raise ValueError("The declared Pilk source companions are required")
    pilk = metadata["third_party_sources"][0]
    expected = {f"loki-{metadata['version']}-source.tar.gz", "LOKI-PREVIEW.json", "SHA256SUMS",
                "install.sh", "install.ps1", "install.cmd", pilk["source_asset"], pilk["license_asset"], pilk["codec_notice_asset"]}
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("Source companion symlinks refused")
    rows = {path.name: {"size": path.stat().st_size, "sha256": digest(path)} for path in directory.iterdir() if path.is_file()}
    sums = checksum_rows((directory / "SHA256SUMS").read_text(encoding="utf-8-sig"))
    if len(rows) != 9 or set(rows) != expected or set(rows) != {"SHA256SUMS", *sums} or any(rows[name]["sha256"] != value for name, value in sums.items()):
        raise ValueError("Exact nine source companion assets required")
    return {"commit": commit, "version": metadata["version"], "assets": rows}


def validate_assets(release: dict, companions: dict, native: list[Path]) -> None:
    if len(companions["assets"]) != 9:
        raise ValueError("All nine source companions are required")
    listed = release.get("assets", [])
    for name, expected in companions["assets"].items():
        rows = [row for row in listed if row.get("name") == name]
        if len(rows) != 1 or rows[0].get("size") != expected["size"] or rows[0].get("digest") != "sha256:" + expected["sha256"]:
            raise ValueError("Draft source companions must already match the exact source job")
    if any(path.name in {row["name"] for row in listed} for path in native):
        raise ValueError("Native release assets already exist; refusing overwrite")
    if any(not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size < MAX_ASSET for path in native):
        raise ValueError("Every native asset must be regular, nonempty and under 2 GiB")


def upload_assets(release_id: int, commit: str, version: str, assets: list[Path]) -> None:
    release = draft(release_id, commit, version)
    before = {row["id"]: (row["name"], row["size"], row.get("digest")) for row in release["assets"]}
    expected = {path.name: (path.stat().st_size, "sha256:" + digest(path)) for path in assets}
    uploaded = []
    for path in assets:
        current = draft(release_id, commit, version)
        if any(row["name"] == path.name for row in current["assets"]):
            raise ValueError("Asset appeared during staging; refusing overwrite")
        row = api(f"repos/{REPOSITORY}/releases/{release_id}/assets?name={quote(path.name)}", upload=path)
        if (row.get("name") != path.name or row.get("state") != "uploaded"
                or (row.get("size"), row.get("digest")) != expected[path.name]):
            raise ValueError("Uploaded asset digest mismatch; draft retained")
        uploaded.append({key: row[key] for key in ("id", "name", "size", "digest")})
    after = draft(release_id, commit, version)
    observed = {row["id"]: (row["name"], row["size"], row.get("digest")) for row in after["assets"]}
    if any(observed.get(key) != value for key, value in before.items()):
        raise ValueError("Existing release asset changed")
    if any((path.stat().st_size, "sha256:" + digest(path)) != expected[path.name] for path in assets):
        raise ValueError("Local staged assets changed during upload")
    print(json.dumps({"status": "staged-draft-only", "commit": commit, "assets": uploaded}))


def stage_source(args) -> None:
    version = source_identity(args.source, args.commit)
    companions = source_manifest(args.output, args.commit)
    if companions["version"] != version:
        raise ValueError("Source package version differs from admitted source")
    release = draft(args.draft_release_id, args.commit, version)
    missing = []
    for name, value in companions["assets"].items():
        rows = [row for row in release["assets"] if row["name"] == name]
        if rows and (len(rows) != 1 or rows[0]["size"] != value["size"] or rows[0].get("digest") != "sha256:" + value["sha256"]):
            raise ValueError("Existing source asset differs; refusing overwrite")
        if not rows:
            path = args.output / name
            if not 0 < path.stat().st_size < MAX_ASSET:
                raise ValueError("Source assets must be nonempty and under 2 GiB")
            missing.append(path)
    upload_assets(args.draft_release_id, args.commit, version, missing)
    validate_assets(draft(args.draft_release_id, args.commit, version), companions, [])
    source_identity(args.source, args.commit)


def preflight(args) -> None:
    from hermes_platform.host.facts import os_family, process_arch
    if os_family() != "darwin" or process_arch() != "arm64":
        raise ValueError("Actual native macOS arm64 is required")
    version = source_identity(args.source, args.commit)
    if shutil.disk_usage(args.output.parent).free < MIN_FREE:
        raise ValueError("At least 13 GiB free is required before native preparation")
    if args.draft_release_id:
        release = draft(args.draft_release_id, args.commit, version)
        companions = json.loads(os.environ["SOURCE_ASSET_MANIFEST"])
        if companions["commit"] != args.commit or companions["version"] != version:
            raise ValueError("Source companion job identity mismatch")
        validate_assets(release, companions, [])
    args.output.mkdir(exist_ok=False)


def product_environment(home: Path) -> dict[str, str]:
    home.mkdir()
    (home / "tmp").mkdir()
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "USERPROFILE": str(home),
            "TMPDIR": str(home / "tmp"), "LANG": "C.UTF-8", "PYTHONUTF8": "1", "NO_COLOR": "1"}


def module_origins(payload: Path, env: dict[str, str], output: Path) -> None:
    manifest = json.loads((payload / "manifest.json").read_bytes())["runtime"]
    python = (payload / manifest["storePython"]).resolve()
    roots = [(payload / manifest[name]).resolve() for name in ("repoDir", "sitePackages")]
    if not python.is_relative_to(payload.resolve()) or any(not root.is_relative_to(payload.resolve()) for root in roots):
        raise ValueError("Installed runtime paths escape the packaged payload")
    body = ("import importlib,json,pathlib,site,sys;"
            f"sys.path.insert(0,{str(roots[0])!r});site.addsitedir({str(roots[1])!r});"
            "names=['hermes_cli.main','hermes_state','pm','hermes_yaml','ruamel.yaml','openai'];"
            "print(json.dumps({n:str(pathlib.Path(importlib.import_module(n).__file__).resolve()) for n in names}))")
    observed = json.loads(checked([str(python), "-I", "-S", "-X", f"pycache_prefix={output / 'observer-cache'}", "-c", body], env=env, cwd=env["HOME"]))
    if any(not Path(value).is_relative_to(payload.resolve()) for value in observed.values()):
        raise ValueError("Installed imports escaped the packaged payload")


def notices(source: Path, resources: Path) -> dict:
    pairs = {"Hermes-LICENSE.txt": "LICENSE", "Loki-NOTICE.txt": "NOTICE",
             "hermes-bots-LICENSE.txt": "apps/desktop/src/plugins/hermes-bots/LICENSE",
             "pilk/LICENSE": "notices/pilk-0.2.4/LICENSE", "pilk/SILK-NOTICES.txt": "notices/pilk-0.2.4/SILK-NOTICES.txt"}
    for target, original in pairs.items():
        if (resources / "licenses" / target).read_bytes() != (source / original).read_bytes():
            raise ValueError("Packaged license/notice differs from admitted source")
    prepared = json.loads((source / ".build/desktop-job/packager/prepared.json").read_bytes())
    vendor = Path(prepared["electron"])
    entry = next(row for row in prepared["files"] if Path(row["path"]) == vendor)
    prefix = json.dumps(["", vendor.stat().st_mode & 0o777], separators=(",", ":"))
    if hashlib.sha256((prefix + digest(vendor)).encode()).hexdigest() != entry["digest"]:
        raise ValueError("Admitted Electron archive bytes changed")
    import zipfile
    with zipfile.ZipFile(vendor) as supplier:
        for name in ("LICENSE", "LICENSES.chromium.html"):
            if (resources / "licenses/electron" / name).read_bytes() != supplier.read(name):
                raise ValueError("Packaged Electron notice differs from admitted supplier")
    npm = resources / "licenses/npm"
    if not (npm / "react/LICENSE").is_file():
        raise ValueError("Packaged npm notices are missing")
    for path in npm.rglob("*"):
        if path.is_file() and path.read_bytes() != (source / "node_modules" / path.relative_to(npm)).read_bytes():
            raise ValueError("Packaged npm notice differs from installed supplier")
    return {name: digest(resources / "licenses" / name) for name in [*pairs, "electron/LICENSE", "electron/LICENSES.chromium.html"]}


def installed_identity(app: Path, *, source: Path, commit: str, version: str) -> dict:
    resources = app / "Contents/Resources"
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    stamp = json.loads((resources / "install-stamp.json").read_bytes())
    if (plist["CFBundleIdentifier"] != "com.obliviousodin.loki" or plist["CFBundleShortVersionString"] != version
            or plist["CFBundleExecutable"] != "Loki" or stamp["commit"] != commit
            or stamp["dirty"] is not False or stamp.get("lokiPreviewPrimary") is not True):
        raise ValueError("Installed unsigned app identity mismatch")
    schemes = [value for row in plist["CFBundleURLTypes"] for value in row["CFBundleURLSchemes"]]
    if schemes != ["loki"] or (resources / "app-update.yml").exists():
        raise ValueError("Public protocol or disabled updater boundary differs")
    if checked(["/usr/bin/lipo", "-archs", str(app / "Contents/MacOS/Loki")]) != "arm64":
        raise ValueError("Native app architecture mismatch")
    electron = plistlib.loads((app / "Contents/Frameworks/Electron Framework.framework/Resources/Info.plist").read_bytes())
    expected = json.loads((source / "apps/desktop/package.json").read_bytes())["devDependencies"]["electron"]
    if electron["CFBundleVersion"] != expected:
        raise ValueError("Packaged Electron version differs from admitted source")
    checked(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    trust = checked(["/usr/bin/codesign", "-d", "--verbose=4", str(app)], stderr=subprocess.STDOUT)
    if "Signature=adhoc" not in trust or re.search(r"^TeamIdentifier=(?!not set$).+", trust, re.MULTILINE):
        raise ValueError("Only the intended unsigned ad-hoc preview is supported")
    return notices(source, resources)


def retire_build_copies(source: Path, output: Path, *, commit: str, version: str) -> None:
    """Only this fresh job's generated app/payload; immutable ZIP remains untouched."""
    built = source / "apps/desktop/release/mac-arm64/Loki.app"
    payload = source / "apps/desktop/build/agent-payload"
    for path in (built, payload):
        if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("Generated build-copy retirement path is not owned")
    proof = installed_identity(built, source=source, commit=commit, version=version)
    (output / "build-copy-custody.json").write_text(json.dumps({"commit": commit, "notices": proof,
        "payload_manifest": json.loads((payload / "manifest.json").read_bytes()),
        "prepared": json.loads((source / ".build/desktop-job/prepared.json").read_bytes())}, indent=2), encoding="utf-8")
    source_identity(source, commit)
    shutil.rmtree(built)
    shutil.rmtree(payload)


def verify(args) -> None:
    from scripts.loki.native_preview_scan import scan
    version = source_identity(args.source, args.commit)
    release = args.source / "apps/desktop/release"
    archives = list(release.glob("*.zip"))
    if len(archives) != 1 or not 0 < archives[0].stat().st_size < MAX_ASSET:
        raise ValueError("One native ZIP under 2 GiB required")
    archive = archives[0]
    original_hash = digest(archive)
    scan_result = scan(archive, commit=args.commit, build_roots=[args.source, args.source / ".cache", args.source / ".build"], scratch=args.output)
    retire_build_copies(args.source, args.output, commit=args.commit, version=version)
    import zipfile
    with zipfile.ZipFile(archive) as zipped:
        required = sum(item.file_size for item in zipped.infolist()) + 1024 ** 3
    if shutil.disk_usage(args.output).free < required:
        raise ValueError("Insufficient capacity for a fresh ZIP extraction")
    installed = args.output / "installed"
    installed.mkdir()
    checked(["/usr/bin/ditto", "-x", "-k", str(archive), str(installed)])
    app = installed / "Loki.app"
    resources = app / "Contents/Resources"
    notice_hashes = installed_identity(app, source=args.source, commit=args.commit, version=version)
    binary = app / "Contents/MacOS/Loki"
    payload = resources / "agent-payload"
    launcher = payload / "bin/loki"
    env = product_environment(args.output / "cli-home")
    module_origins(payload, env, args.output)
    cli_version = tomllib.loads((args.source / "pyproject.toml").read_text(encoding="utf-8-sig"))["project"]["version"]
    for index, command in enumerate((["--version"], ["--help"], ["tools", "list"], ["pm", "doctor"])):
        text = checked([str(launcher), *command], env=env, cwd=env["HOME"], timeout=240)
        (args.output / f"cli-{index}.log").write_text(text, encoding="utf-8")
        if index == 0 and ("Loki" not in text or cli_version not in text or args.commit[:8] not in text):
            raise ValueError("Installed CLI source identity mismatch")
    smoke = args.source / "tests/install/e2e-assets/desktop-smoke.ts"
    (args.output / "mock-smoke").mkdir()
    from scripts.bundles.desktop_prepare import fingerprint
    prepared = json.loads((args.source / ".build/desktop-job/prepared.json").read_bytes())
    node = Path(prepared["node"])
    if not node.resolve().is_relative_to(args.source.resolve()) or fingerprint(node) != prepared["digests"][str(node)]:
        raise ValueError("Admitted Node changed")
    checked([str(node), str(smoke), "--exe", str(binary), "--root", str(payload), "--origin", "bundled",
             "--home", str(args.output / "mock-home"), "--user-data", str(args.output / "mock-user-data"),
             "--out", str(args.output / "mock-smoke"), "--phase", "installed", "--expect-commit", args.commit],
            env={**env, "PATH": str(node.parent) + os.pathsep + env["PATH"]}, cwd=env["HOME"], timeout=600)
    checked(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    source_identity(args.source, args.commit)
    if digest(archive) != original_hash:
        raise ValueError("Immutable native ZIP changed")
    destination = args.output / ("UNSIGNED-PREVIEW-" + archive.name)
    shutil.move(archive, destination)
    blockmap = archive.with_suffix(".zip.blockmap")
    if not blockmap.is_file():
        raise ValueError("Native ZIP blockmap missing")
    shutil.move(blockmap, args.output / (destination.name + ".blockmap"))
    proof = {"commit": args.commit, "version": version, "architecture": "arm64", "signed": False,
             "native_zip_sha256": original_hash, "notices": notice_hashes, "privacy": scan_result,
             "installed_cli_and_loopback_mock": "passed", "published_download": "pending separate verification-only hosted job",
             "human_gui_quarantine_live_provider": "not qualified"}
    (args.output / "NATIVE-PREVIEW.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    assets = [destination, args.output / (destination.name + ".blockmap"), args.output / "NATIVE-PREVIEW.json"]
    (args.output / "NATIVE-SHA256SUMS").write_text("".join(f"{digest(path)}  {path.name}\n" for path in assets), encoding="utf-8")


def stage(args) -> None:
    from scripts.loki.public_source_acceptance import checksum_rows
    version = source_identity(args.source, args.commit)
    companions = json.loads(os.environ["SOURCE_ASSET_MANIFEST"])
    if companions["commit"] != args.commit or companions["version"] != version:
        raise ValueError("Source companion job identity mismatch")
    proof = json.loads((args.output / "NATIVE-PREVIEW.json").read_bytes())
    if proof["commit"] != args.commit or proof["installed_cli_and_loopback_mock"] != "passed":
        raise ValueError("A passed exact-source native verification is required")
    assets = [*args.output.glob("UNSIGNED-PREVIEW-*.zip"), *args.output.glob("UNSIGNED-PREVIEW-*.zip.blockmap"),
              args.output / "NATIVE-PREVIEW.json", args.output / "NATIVE-SHA256SUMS"]
    if len(assets) != 4:
        raise ValueError("Exact four native assets required")
    sums = checksum_rows((args.output / "NATIVE-SHA256SUMS").read_text(encoding="utf-8-sig"))
    if set(sums) != {path.name for path in assets if path.name != "NATIVE-SHA256SUMS"} or any(digest(args.output / name) != value for name, value in sums.items()):
        raise ValueError("Native verification/checksum bytes changed")
    zipped = next(path for path in assets if path.suffix == ".zip")
    if not (args.output / (zipped.name + ".blockmap")).is_file():
        raise ValueError("Native blockmap name differs from the verified ZIP")
    if digest(zipped) != proof["native_zip_sha256"]:
        raise ValueError("Native archive no longer matches its verification")
    release = draft(args.draft_release_id, args.commit, version)
    validate_assets(release, companions, assets)
    upload_assets(args.draft_release_id, args.commit, version, assets)
    source_identity(args.source, args.commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["source-manifest", "stage-source", "preflight", "verify", "stage"])
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draft-release-id", type=int, default=0)
    args = parser.parse_args()
    if args.mode == "source-manifest":
        source_identity(args.source, args.commit)
        print("manifest=" + json.dumps(source_manifest(args.output, args.commit), separators=(",", ":")))
        return
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        parser.error("Only this repository's manual main workflow on a disposable hosted runner is admitted")
    {"stage-source": stage_source, "preflight": preflight, "verify": verify, "stage": stage}[args.mode](args)


if __name__ == "__main__":
    main()
