"""Fail-closed Loki source identity admission shared by Git and ZIP updates.

This checks the public product contract, not signatures or target code safety.
Versions and the recorded Hermes baseline may change in ordinary Loki updates.
Target Python is parsed as data and is never imported in the old interpreter.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import tomllib

from loki_identity import COMMAND, DISTRIBUTION, PRODUCT_NAME, REPOSITORY

IDENTITY_FILES = ("loki.py", "loki_identity.py", "pyproject.toml")
_EXPECTED = {"PRODUCT_NAME": PRODUCT_NAME, "COMMAND": COMMAND,
             "DISTRIBUTION": DISTRIBUTION, "REPOSITORY": REPOSITORY}


class TargetIdentityError(ValueError):
    """The proposed source does not prove Loki's stable public identity."""


def source_identity_refusal(files: dict[str, bytes | None]) -> str | None:
    """A bounded, static public identity contract; no version or upstream SHA pin."""
    for name in IDENTITY_FILES:
        data = files.get(name)
        if not data or len(data) > 1024 * 1024:
            return f"Loki source identity is missing or unreadable ({name})"
    try:
        identity = ast.parse(files["loki_identity.py"])
        values = {}
        for node in identity.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in _EXPECTED:
                        values[target.id] = ast.literal_eval(node.value)
        if any(values.get(key) != value for key, value in _EXPECTED.items()):
            return "the source target does not declare this Loki product and repository"
        launcher = ast.parse(files["loki.py"])
        if not any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in launcher.body):
            return "the source target has no Loki main entry point"
        project = tomllib.loads(files["pyproject.toml"].decode("utf-8"))["project"]
        scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
        if (not isinstance(project, dict) or project.get("name") != DISTRIBUTION
                or not isinstance(scripts, dict) or scripts.get(COMMAND) != "loki:main"):
            return "the source target does not install Loki's package and command"
    except (SyntaxError, ValueError, TypeError, KeyError, UnicodeError):
        return "the source target has invalid or unreadable Loki identity metadata"
    return None


def git_identity_refusal(git_cmd, root: Path, target_ref: str) -> str | None:
    """Read committed blobs, not the live checkout; read failures never admit a target."""
    from hermes_cli.update_cmd_commit import read_target_files

    try:
        files = read_target_files(git_cmd, root, target_ref, IDENTITY_FILES)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "the source target's Loki identity could not be read from Git"
    return source_identity_refusal(files)


def require_tree_identity(root: Path) -> None:
    """Admit extracted ZIP source before staging or any live overlay."""
    try:
        files = {name: None if (root / name).is_symlink() else (root / name).read_bytes()
                 for name in IDENTITY_FILES}
    except OSError as exc:
        raise TargetIdentityError("the extracted source's Loki identity could not be read") from exc
    if reason := source_identity_refusal(files):
        raise TargetIdentityError(reason)


def refuse_git_target(git_cmd, root: Path, target_ref: str, resume) -> None:
    """The early refusal also covers CP0's local branch before parking or stashing."""
    if reason := git_identity_refusal(git_cmd, root, target_ref):
        from hermes_cli.update_cmd_common import _record_stop
        from hermes_cli.update_cmd import _m

        _record_stop("target_identity_refused")
        print(f"✗ Refusing this source update: {reason}.")
        print("  No update was applied; your install is unchanged.")
        _m()._resume_windows_gateways_after_update(resume)
        raise SystemExit(1)


def refuse_branch_landing(git_cmd, branch, current_branch, target_ref, *, release_tag, in_place, resume):
    """CP0 tries the local branch first, which may differ from the admitted fetched target."""
    if not release_tag and not in_place and current_branch != branch:
        from hermes_cli.update_cmd import _m, _resolved_commit

        local = _resolved_commit(git_cmd, f"refs/heads/{branch}")
        refuse_git_target(git_cmd, _m().PROJECT_ROOT, local or target_ref, resume)
