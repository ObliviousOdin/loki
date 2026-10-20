"""Accept an already published Loki alpha through its public default source installer.

This runs only on disposable hosted runners. Controlled local-source installation,
native applications, interactive startup and live providers have separate gates.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPOSITORY = "ObliviousOdin/loki"
ORIGIN = f"https://github.com/{REPOSITORY}.git"
API = f"https://api.github.com/repos/{REPOSITORY}"
MIN_FREE = 3_000_000_000
ALLOWED_HOSTS = {"api.github.com", "github.com", "raw.githubusercontent.com",
                 "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
SCENARIOS = ["public default source install", "PATH discovery and help", "version",
             "configuration", "gateway help", "cross-process session persistence",
             "local terminal tool", "foreign state and owned update source"]


class CommandFailure(RuntimeError):
    def __init__(self, phase: str, outcome: str):
        super().__init__("Acceptance command did not complete successfully")
        self.phase = phase
        self.outcome = outcome


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Public GitHub HTTPS destination required")


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, destination: Path) -> None:
    validate_url(url)
    opener = build_opener(ProxyHandler({}), PublicRedirects())
    request = Request(url, headers={"User-Agent": "Loki-public-source-acceptance"})
    with opener.open(request, timeout=60) as response, destination.open("xb") as target:
        validate_url(response.url)
        size = 0
        while block := response.read(64 * 1024):
            size += len(block)
            if size > 8 * 1024 * 1024:
                raise ValueError("Acceptance metadata or installer exceeds the bounded download size")
            target.write(block)


def checksum_rows(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        row = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,255})", line)
        if row is None or row[2] in result:
            raise ValueError("Malformed or duplicate release checksum")
        result[row[2]] = row[1]
    return result


def validate_release(release: dict, metadata: dict, project: dict, baseline: dict,
                     comparison: dict, *, tag: str, commit: str, peeled: str) -> None:
    version = tag.removeprefix("v")
    declared_version = re.sub(r"-alpha\.(\d+)$", r"a\1", version)
    if (release.get("tag_name") != tag or release.get("draft") is not False
            or release.get("prerelease") is not True or peeled != commit):
        raise ValueError("Published alpha and immutable tag identity mismatch")
    expected = {"product": "Loki", "version": version, "commit": commit,
                "repository": REPOSITORY, "kind": "source-preview", "signed": False,
                "upstream_commit": baseline.get("commit")}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Release manifest does not bind the expected source")
    if (project.get("name") != "obliviousodin-loki-agent"
            or project.get("version") != declared_version
            or not re.fullmatch(r"[0-9a-f]{40}", str(baseline.get("commit", "")))):
        raise ValueError("Target project version or upstream baseline mismatch")
    if (comparison.get("status") not in {"ahead", "identical"}
            or comparison.get("behind_by") != 0
            or comparison.get("base_commit", {}).get("sha") != commit
            or comparison.get("merge_base_commit", {}).get("sha") != commit):
        raise ValueError("Release commit is not on main ancestry")


def clean_environment(home: Path, host: dict[str, str], *, windows: bool) -> dict[str, str]:
    env = {key: host[key] for key in ("SYSTEMROOT", "ComSpec", "PATHEXT", "PROGRAMFILES",
                                    "ProgramFiles", "ProgramFiles(x86)") if key in host}
    if windows:
        system = Path(host["SYSTEMROOT"])
        git = shutil.which("git.exe", path=host.get("PATH"))
        if git is None:
            raise RuntimeError("Hosted native Git prerequisite missing")
        env["PATH"] = os.pathsep.join(map(str, (
            system / "System32", system, system / "System32/WindowsPowerShell/v1.0", Path(git).parent,
        )))
    else:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        env["SHELL"] = "/bin/bash"
    env.update(HOME=str(home), USERPROFILE=str(home), LOCALAPPDATA=str(home / "AppData/Local"),
               APPDATA=str(home / "AppData/Roaming"), TMPDIR=str(home / "tmp"),
               TMP=str(home / "tmp"), TEMP=str(home / "tmp"), PYTHONUTF8="1", NO_COLOR="1",
               LANG="C.UTF-8", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_TERMINAL_PROMPT="0")
    # Hosted runner ownership tracking permits its final job cleanup as well.
    if "RUNNER_TRACKING_ID" in host:
        env["RUNNER_TRACKING_ID"] = host["RUNNER_TRACKING_ID"]
    return env


def stop_owned(child: subprocess.Popen) -> None:
    if os.name == "nt":
        if child.poll() is None:
            try:
                taskkill = Path(os.environ["SYSTEMROOT"]) / "System32/taskkill.exe"
                subprocess.run([str(taskkill), "/T", "/F", "/PID", str(child.pid)],
                               capture_output=True, timeout=15, check=False)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=15)
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)  # windows-footgun: ok -- Windows returned above.
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)  # windows-footgun: ok -- Windows returned above.
    except ProcessLookupError:
        pass
    child.wait(timeout=5)


def run(command: list[str], env: dict[str, str], root: Path, label: str,
        *, cwd: Path | None = None, timeout: int = 180, stdin: str | None = None,
        cleanup: bool = False) -> str:
    if not cleanup and shutil.disk_usage(root).free < MIN_FREE:
        raise RuntimeError("Acceptance disk capacity guard")
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with (root / f"{label}.log").open("xb") as output:
        child = subprocess.Popen(command, cwd=cwd or root, env=env, stdout=output,
                                 stderr=subprocess.STDOUT, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                 **kwargs)
        try:
            if stdin is not None:
                child.stdin.write(stdin.encode("ascii"))
                child.stdin.close()
            deadline = time.monotonic() + timeout
            while child.poll() is None:
                if time.monotonic() >= deadline or (not cleanup and shutil.disk_usage(root).free < MIN_FREE):
                    raise CommandFailure(label, "deadline-or-capacity")
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            if child.returncode:
                raise CommandFailure(label, "nonzero-exit")
        finally:
            stop_owned(child)
    return (root / f"{label}.log").read_text(encoding="utf-8-sig", errors="replace")


def foreign_snapshot(paths: list[Path]) -> dict:
    result = {}
    for index, root in enumerate(paths):
        if not root.is_dir() or root.is_symlink():
            raise ValueError("Foreign canary root changed")
        rows = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Foreign canary symlink refused")
            rows.append((path.relative_to(root).as_posix(), "dir" if path.is_dir() else "file",
                         None if path.is_dir() else digest(path)))
        result[str(index)] = rows
    return result


def acquire(root: Path, tag: str, commit: str, installer: str) -> dict:
    def get(url: str, name: str) -> Path:
        path = root / name
        fetch(url, path)
        return path

    release = json.loads(get(f"{API}/releases/tags/{quote(tag, safe='')}", "release.json").read_bytes())
    ref = json.loads(get(f"{API}/git/ref/tags/{quote(tag, safe='')}", "tag.json").read_bytes())["object"]
    for index in range(4):
        if ref["type"] == "commit":
            break
        if ref["type"] != "tag" or not re.fullmatch(r"[0-9a-f]{40}", ref["sha"]):
            raise ValueError("Unsupported release tag object")
        ref = json.loads(get(f"{API}/git/tags/{ref['sha']}", f"tag-{index}.json").read_bytes())["object"]
    comparison = json.loads(get(f"{API}/compare/{commit}...main", "ancestry.json").read_bytes())
    prefix = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}"
    project = tomllib.loads(get(f"{prefix}/pyproject.toml", "project.toml").read_text(encoding="utf-8-sig"))["project"]
    baseline = json.loads(get(f"{prefix}/docs/loki/UPSTREAM.json", "upstream.json").read_bytes())
    listed = release.get("assets", [])
    assets = ("SHA256SUMS", "LOKI-PREVIEW.json", installer)
    for name in assets:
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        rows = [row for row in listed if row.get("name") == name]
        if len(rows) != 1 or rows[0].get("browser_download_url") != url:
            raise ValueError("Owned public release asset missing or duplicated")
        path = get(url, name)
        if path.stat().st_size != rows[0].get("size"):
            raise ValueError("Release asset size mismatch")
        if rows[0].get("digest") not in (None, f"sha256:{digest(path)}"):
            raise ValueError("Release API asset hash mismatch")
    sums = checksum_rows((root / "SHA256SUMS").read_text(encoding="utf-8-sig"))
    for name in ("LOKI-PREVIEW.json", installer):
        if sums.get(name) != digest(root / name):
            raise ValueError("Released SHA256SUMS does not match downloaded bytes")
    metadata = json.loads((root / "LOKI-PREVIEW.json").read_bytes())
    validate_release(release, metadata, project, baseline, comparison,
                     tag=tag, commit=commit, peeled=ref["sha"] if ref["type"] == "commit" else "")
    exact = get(f"{prefix}/scripts/{installer}", f"exact-{installer}")
    if exact.read_bytes() != (root / installer).read_bytes():
        raise ValueError("Released installer differs from immutable source")
    return {"asset_sha256": {name: digest(root / name) for name in assets},
            "release_id": release["id"], "hash_verification_not_signing": True,
            "declared_version": project["version"]}


def powershell(env: dict[str, str], body: str) -> list[str]:
    binary = Path(env["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    output = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
    return [str(binary), "-NoProfile", "-NonInteractive", "-Command", output + body]


def restore_user_path(value: str | None, env: dict[str, str], root: Path) -> None:
    body = ("$value=[Console]::In.ReadToEnd()|ConvertFrom-Json;"
            "[Environment]::SetEnvironmentVariable('Path',$value,'User');"
            "ConvertTo-Json -InputObject ([Environment]::GetEnvironmentVariable('Path','User')) -Compress")
    actual = run(powershell(env, body), env, root, "restore-user-path",
                 stdin=json.dumps(value, ensure_ascii=True), cleanup=True)
    if json.loads(actual) != value:
        raise ValueError("Runner User PATH restoration did not persist")


@contextmanager
def runner_user_path(env: dict[str, str], root: Path, receipt: dict):
    """Only the real installer may edit the disposable runner's User PATH."""
    query = "ConvertTo-Json -InputObject ([Environment]::GetEnvironmentVariable('Path','User')) -Compress"
    original = json.loads(run(powershell(env, query), env, root, "original-user-path"))
    try:
        yield
    finally:
        restore_user_path(original, env, root)
        receipt["runner_user_path_restored"] = True


def check_installed(root: Path, home: Path, env: dict[str, str], commit: str, version: str) -> None:
    windows = os.name == "nt"
    state = home / "AppData/Local/loki" if windows else home / ".loki"
    source = state / "hermes-agent"
    launcher = state / "bin/loki.exe" if windows else home / ".local/bin/loki"
    if not source.is_dir() or source.is_symlink() or not launcher.is_file() or launcher.is_symlink():
        raise ValueError("Default source or published launcher missing")
    if windows:
        discovery = powershell(env, "$env:Path=[Environment]::GetEnvironmentVariable('Path','User')+';'+$env:Path;(Get-Command loki -CommandType Application -ErrorAction Stop).Source")
    else:
        discovery = ["/bin/bash", "-l", "-c", "command -v loki"]
    found = run(discovery, env, root, "path-discovery", cwd=home).strip()
    if Path(found).resolve() != launcher.resolve():
        raise ValueError("Default published PATH entry did not resolve Loki")
    observed = run([str(launcher), "--version"], env, root, "version", cwd=home)
    if "Loki" not in observed or version not in observed or commit[:8] not in observed:
        raise ValueError("Installed version differs from immutable release")
    if "loki" not in run([str(launcher), "--help"], env, root, "help", cwd=home):
        raise ValueError("Installed public help identity missing")
    run([str(launcher), "config", "set", "model", "loki-public-install-synthetic"],
        env, root, "config-set", cwd=home)
    if "loki-public-install-synthetic" not in run([str(launcher), "config", "show"], env, root, "config-show", cwd=home):
        raise ValueError("Synthetic configuration did not persist")
    run([str(launcher), "gateway", "--help"], env, root, "gateway-help", cwd=home)
    runtime = json.loads(run([str(launcher), "--print-runtime-command"], env, root, "runtime", cwd=home))
    if (not isinstance(runtime, list) or not runtime or not all(isinstance(x, str) for x in runtime)
            or not Path(runtime[0]).is_absolute() or not Path(runtime[0]).resolve().is_relative_to(state.resolve())):
        raise ValueError("Installed Python escapes the default owned state")

    def probe(body: str, name: str) -> str:
        setup = f"import sys;sys.path.insert(0,{str(source)!r});import hermes_bootstrap;"
        return run([runtime[0], "-I", "-c", setup + body], env, root, name, cwd=home)

    origins = json.loads(probe(
        "import importlib,json,pathlib;from hermes_constants import get_hermes_home;"
        "from hermes_cli.update_cmd_git import OFFICIAL_REPO_URL;"
        "mods=['hermes_cli.main','hermes_state','tools.terminal_tool','pm','hermes_yaml','openai','ruamel.yaml'];"
        "print(json.dumps({'home':str(get_hermes_home().resolve()),'update':OFFICIAL_REPO_URL,"
        "'origins':{n:str(pathlib.Path(importlib.import_module(n).__file__).resolve()) for n in mods}}))",
        "owned-origins"))
    if Path(origins["home"]) != state.resolve() or origins["update"] != ORIGIN:
        raise ValueError("Default home or owned update URL mismatch")
    for name, path in origins["origins"].items():
        expected = state if name in {"openai", "ruamel.yaml"} else source
        if not Path(path).is_relative_to(expected.resolve()):
            raise ValueError("Installed module origin is outside its owned source/runtime")
    probe("from hermes_state import SessionDB;db=SessionDB();"
          "db.create_session('loki-public-install',source='cli');"
          "db.append_message('loki-public-install','user','synthetic persistent message');db.close()", "session-write")
    probe("from pathlib import Path;from hermes_state import SessionDB;db=SessionDB();"
          f"assert Path(db.db_path).resolve()==Path({str(state / 'state.db')!r}).resolve();"
          "assert any(r['content']=='synthetic persistent message' for r in db.get_messages('loki-public-install'));db.close()",
          "session-read")
    probe("import json;from tools.terminal_tool import terminal_tool;"
          "r=json.loads(terminal_tool('echo Loki-public-install-terminal',timeout=15));"
          "assert 'Loki-public-install-terminal' in str(r) and not r.get('error')", "local-terminal")
    head = run(["git", "rev-parse", "HEAD"], env, root, "installed-head", cwd=source).strip()
    origin = run(["git", "remote", "get-url", "origin"], env, root, "installed-origin", cwd=source).strip()
    config = run(["git", "config", "--local", "--list"], env, root, "git-config", cwd=source)
    status = run(["git", "status", "--porcelain", "--untracked-files=no"], env, root, "source-status", cwd=source)
    if head != commit or origin != ORIGIN or status.strip() or any(row.startswith("url.") for row in config.splitlines()):
        raise ValueError("Installed source identity, cleanliness or URL-rewrite guard failed")


def execute(args, root: Path, receipt: dict) -> None:
    home = root / "Fresh User Profile With Spaces"
    home.mkdir()
    for leaf in ("tmp", "AppData/Local", "AppData/Roaming"):
        (home / leaf).mkdir(parents=True, exist_ok=True)
    env = clean_environment(home, dict(os.environ), windows=os.name == "nt")
    foreign = [home / ".hermes", home / ".fabric",
               home / "AppData/Local/hermes", home / "AppData/Local/fabric"]
    for path in foreign:
        path.mkdir(parents=True)
        (path / "canary.txt").write_text("Synthetic foreign state: preserve exact bytes.\n", encoding="utf-8")
    before = foreign_snapshot(foreign)
    installer = "install.ps1" if os.name == "nt" else "install.sh"
    receipt.update(acquire(root, args.tag, args.commit, installer))
    try:
        with runner_user_path(env, root, receipt) if os.name == "nt" else nullcontext():
            if os.name == "nt":
                command = powershell(env, "")[:-2] + ["-ExecutionPolicy", "Bypass", "-File", str(root / installer),
                    "-Commit", args.commit, "-NonInteractive", "-SkipBrowser", "-SkipComputerUse"]
            else:
                command = ["/bin/bash", str(root / installer), "--commit", args.commit,
                           "--non-interactive", "--skip-browser", "--skip-computer-use"]
            run(command, env, root, "public-default-install", timeout=2400)
            check_installed(root, home, env, args.commit, receipt["declared_version"])
        receipt.update(status="passed", scenarios=SCENARIOS, actual_update_executed=False)
    finally:
        if foreign_snapshot(foreign) != before:
            receipt["status"] = "failed"
            raise ValueError("Foreign canary entries or bytes changed")
        receipt["foreign_canaries_unchanged"] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if (not args.execute or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        parser.error("Explicit execution on this repository's disposable hosted dispatch is required")
    if not re.fullmatch(r"v\d+\.\d+\.\d+-alpha\.\d+", args.tag) or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("Exact alpha tag and full immutable commit required")
    if shutil.disk_usage(args.out.parent).free < MIN_FREE:
        parser.error("At least 3 GB available capacity is required")
    args.out.mkdir(exist_ok=False)
    receipt = {"status": "failed", "repository": REPOSITORY, "commit": args.commit, "tag": args.tag,
               "platform": sys.platform, "architecture": os.uname().machine if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE"),
               "started_at": time.time(), "native_or_provider_qualification": False,
               "browser_and_computer_use": "explicit lean-install skips", "interactive_tty": "not exercised"}
    try:
        execute(args, args.out, receipt)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        receipt.update(status="failed", error_type=type(error).__name__)
        if isinstance(error, CommandFailure):
            receipt.update(failed_check=error.phase, command_outcome=error.outcome)
    finally:
        receipt["finished_at"] = time.time()
        # Allowlisted scalars/hashes only: raw logs, paths, config, databases and
        # runtime commands remain ephemeral runner state, never artifacts.
        (args.out / "PUBLIC-SUMMARY.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
