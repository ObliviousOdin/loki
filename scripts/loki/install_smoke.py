"""Install an exact Loki checkout in a disposable profile and exercise real entry points.

No provider credentials are copied. This receipt proves source installation, local
persistence and a local terminal tool; it does not qualify a native app or live provider.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid


def clean_environment(home: Path, state: Path) -> dict[str, str]:
    keys = ("PATH", "SYSTEMROOT", "ComSpec", "PATHEXT", "PROGRAMFILES", "ProgramFiles",
            "ProgramFiles(x86)", "PROGRAMDATA", "ProgramData", "SSL_CERT_FILE", "SSL_CERT_DIR",
            "INCLUDE", "LIB", "LIBPATH", "VSINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "LOKI_HOME": str(state),
                "HERMES_HOME": str(home / "foreign-hermes"),
                "HERMES_RUNTIME_DIR": str(home / "foreign-tools"),
                "PYTHONUTF8": "1", "CI": "true", "NO_COLOR": "1", "LEFTHOOK": "0",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    for key, leaf in (("TMPDIR", "tmp"), ("TEMP", "tmp"), ("TMP", "tmp"),
                      ("LOCALAPPDATA", "local"), ("APPDATA", "roaming"),
                      ("XDG_CACHE_HOME", ".cache"), ("XDG_CONFIG_HOME", ".config")):
        directory = home / leaf
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    return env


def run(command: list[str], env: dict[str, str], cwd: Path, output: Path,
        *, timeout: int = 2400) -> str:
    with output.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, env=env, cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                timeout=timeout, check=False)
    text = output.read_text(encoding="utf-8-sig", errors="replace")
    if result.returncode:
        raise RuntimeError(f"{command[0]} exited {result.returncode}; see {output}\n{text[-5000:]}")
    return text


def probe(python: str, source: Path, body: str) -> list[str]:
    setup = f"import sys; sys.path.insert(0, {str(source)!r}); import hermes_bootstrap; "
    return [python, "-I", "-c", setup + body]


def exercise(args, receipt: dict) -> None:
    source, out = args.source.resolve(), args.out.resolve()
    home, state, installed = out / "user", out / "state", out / "source"
    home.mkdir(parents=True)
    env = clean_environment(home, state)
    sentinel = home / "foreign-hermes"
    sentinel.mkdir()
    (sentinel / "sentinel.txt").write_text("unchanged", encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True, encoding="utf-8", timeout=30).strip()
    ref = "loki-install-smoke-" + uuid.uuid4().hex
    subprocess.run(["git", "update-ref", f"refs/heads/{ref}", commit, "0" * 40], cwd=source, check=True, timeout=30)
    env["LOKI_REPO_URL"] = str(source)
    if os.name == "nt":
        command = ["powershell", "-NoProfile", "-File", str(source / "scripts/install.ps1"),
                   "-Branch", ref, "-Commit", commit, "-Channel", "main",
                   "-InstallDir", str(installed), "-LokiHome", str(state), "-NonInteractive",
                   "-SkipBrowser", "-SkipComputerUse"]
    else:
        command = ["bash", str(source / "scripts/install.sh"), "--branch", ref,
                   "--commit", commit, "--channel", "main", "--dir", str(installed),
                   "--loki-home", str(state), "--non-interactive", "--skip-browser", "--skip-computer-use"]
    try:
        run(command, env, source, out / "install.log")
    finally:
        subprocess.run(["git", "update-ref", "-d", f"refs/heads/{ref}", commit], cwd=source, check=True, timeout=30)
    subprocess.run(["git", "remote", "set-url", "origin", "https://github.com/ObliviousOdin/loki.git"],
                   cwd=installed, check=True, timeout=30)
    launcher = installed / ".loki/bin" / ("loki.exe" if os.name == "nt" else "loki")
    receipt.update(commit=commit, launcher=str(launcher), state=str(state))
    version = run([str(launcher), "--version"], env, home, out / "version.log", timeout=180)
    if "Loki" not in version or "0.1.0" not in version:
        raise RuntimeError(f"Wrong installed identity: {version}")
    help_text = run([str(launcher), "--help"], env, home, out / "help.log", timeout=180)
    if "loki" not in help_text:
        raise RuntimeError("Installed help does not expose loki")
    run([str(launcher), "config", "set", "model", "loki-smoke-model"], env, home, out / "config-set.log", timeout=180)
    run([str(launcher), "config", "show"], env, home, out / "config-show.log", timeout=180)
    run([str(launcher), "gateway", "--help"], env, home, out / "gateway-help.log", timeout=180)
    runtime = json.loads(run([str(launcher), "--print-runtime-command"], env, home, out / "runtime.json", timeout=180))
    write = "from hermes_state import SessionDB; db=SessionDB(); db.create_session('loki-install-smoke',source='cli'); db.append_message('loki-install-smoke','user','persistent Loki session'); db.close()"
    read = "from hermes_state import SessionDB; db=SessionDB(); rows=db.get_messages('loki-install-smoke'); assert any(r['content']=='persistent Loki session' for r in rows); db.close(); print('session reopened')"
    run(probe(runtime[0], installed, write), env, home, out / "session-write.log", timeout=180)
    run(probe(runtime[0], installed, read), env, home, out / "session-resume.log", timeout=180)
    tool = "import json; from tools.terminal_tool import terminal_tool; result=json.loads(terminal_tool('echo Loki-terminal-smoke',timeout=15)); print(json.dumps(result)); assert 'Loki-terminal-smoke' in str(result) and not result.get('error')"
    run(probe(runtime[0], installed, tool), env, home, out / "terminal.log", timeout=180)
    identity = "from hermes_constants import get_hermes_home; from hermes_cli.update_cmd_git import OFFICIAL_REPO_URL; import json; print(json.dumps({'home':str(get_hermes_home()),'update':OFFICIAL_REPO_URL}))"
    observed = json.loads(run(probe(runtime[0], installed, identity), env, home, out / "identity.json", timeout=180).splitlines()[-1])
    if Path(observed["home"]).resolve() != state.resolve() or "ObliviousOdin/loki" not in observed["update"]:
        raise RuntimeError(f"Wrong installed home or update source: {observed}")
    if (sentinel / "sentinel.txt").read_text(encoding="utf-8-sig") != "unchanged" or list(sentinel.iterdir()) != [sentinel / "sentinel.txt"]:
        raise RuntimeError("Foreign Hermes state was changed")
    receipt.update(status="passed", version=version.strip(), identity=observed,
                   scenarios=["clean source install", "help", "version", "configuration", "gateway help",
                              "cross-process session persistence", "local terminal tool", "foreign state isolation"],
                   unverified=["live provider conversation", "messaging delivery", "native packaged application",
                               "browser and computer-use tools (explicit lean-install smoke)"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {"status": "failed", "platform": sys.platform, "architecture": platform.machine(),
               "started_at": time.time()}
    try:
        exercise(args, receipt)
    finally:
        (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
