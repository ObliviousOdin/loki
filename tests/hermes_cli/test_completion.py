"""Tests for hermes_cli/completion.py — shell completion script generation."""

import argparse
import os
import shutil
import subprocess
import tempfile

import pytest

from hermes_cli.completion import _walk, generate_bash, generate_fish, generate_zsh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    """Build a minimal parser that mirrors the real hermes structure."""
    p = argparse.ArgumentParser(prog="hermes")
    p.add_argument("--version", "-V", action="store_true")
    p.add_argument("-p", "--profile", help="Profile name")
    sub = p.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="Interactive chat with the agent")
    chat.add_argument("-q", "--query")
    chat.add_argument("-m", "--model")

    gw = sub.add_parser("gateway", help="Messaging gateway management")
    gw_sub = gw.add_subparsers(dest="gateway_command")
    gw_sub.add_parser("start", help="Start service")
    gw_sub.add_parser("stop", help="Stop service")
    gw_sub.add_parser("status", help="Show status")
    # alias — should NOT appear as a duplicate in completions
    gw_sub.add_parser("run", aliases=["foreground"], help="Run in foreground")

    sess = sub.add_parser("sessions", help="Manage session history")
    sess_sub = sess.add_subparsers(dest="sessions_action")
    sess_sub.add_parser("list", help="List sessions")
    sess_sub.add_parser("delete", help="Delete a session")

    prof = sub.add_parser("profile", help="Manage profiles")
    prof_sub = prof.add_subparsers(dest="profile_command")
    prof_sub.add_parser("list", help="List profiles")
    prof_sub.add_parser("use", help="Switch to a profile")
    prof_sub.add_parser("create", help="Create a new profile")
    prof_sub.add_parser("delete", help="Delete a profile")
    prof_sub.add_parser("show", help="Show profile details")
    prof_sub.add_parser("alias", help="Set profile alias")
    prof_sub.add_parser("rename", help="Rename a profile")
    prof_sub.add_parser("export", help="Export a profile")

    sub.add_parser("version", help="Show version")

    return p


# ---------------------------------------------------------------------------
# 1. Parser extraction
# ---------------------------------------------------------------------------

class TestWalk:
    def test_top_level_subcommands_extracted(self):
        tree = _walk(_make_parser())
        assert set(tree["subcommands"].keys()) == {"chat", "gateway", "sessions", "profile", "version"}


    def test_aliases_not_duplicated(self):
        """'foreground' is an alias of 'run' — must not appear as separate entry."""
        tree = _walk(_make_parser())
        gw_subs = tree["subcommands"]["gateway"]["subcommands"]
        assert "foreground" not in gw_subs


# ---------------------------------------------------------------------------
# 2. Bash output
# ---------------------------------------------------------------------------

class TestGenerateBash:
    def test_contains_completion_function_and_register(self):
        out = generate_bash(_make_parser())
        assert "_loki_completion()" in out
        assert "complete -F _loki_completion loki" in out


    def test_valid_bash_syntax(self):
        """Script must pass `bash -n` syntax check."""
        out = generate_bash(_make_parser())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write(out)
            path = f.name
        try:
            result = subprocess.run(["bash", "-n", path], capture_output=True, check=False)
            assert result.returncode == 0, result.stderr.decode()
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 3. Profile completion (regression prevention)
# ---------------------------------------------------------------------------

class TestProfileCompletion:
    """Ensure profile name completion is present in all shell outputs."""


    def test_bash_profile_actions_complete_profile_names(self):
        """After 'hermes profile use', complete with profile names."""
        out = generate_bash(_make_parser())
        # The profile case should have _hermes_profiles for name-taking actions
        lines = out.split("\n")
        in_profile_case = False
        has_profiles_in_action = False
        for line in lines:
            if "profile)" in line:
                in_profile_case = True
            if in_profile_case and "_loki_profiles" in line:
                has_profiles_in_action = True
                break
        assert has_profiles_in_action, "profile actions should complete with _loki_profiles"


    def test_fish_profile_actions_complete_names(self):
        out = generate_fish(_make_parser())
        # Should have profile name completion for actions like use, delete, etc.
        assert "__loki_profiles" in out
        count = out.count("(__loki_profiles)")
        # At least the -p flag + the profile action completions
        assert count >= 2, f"Expected >=2 profile completion entries, got {count}"


@pytest.mark.parametrize("generate,shell", [(generate_bash, "bash"), (generate_zsh, "zsh"), (generate_fish, "fish")])
def test_generated_product_templates_preserve_custom_parser_descriptions(generate, shell):
    parser = _make_parser()
    subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    subparsers.add_parser("custom", help="Hermes model documentation")

    script = generate(parser)

    assert f"# Loki {shell} completion" in script
    assert "Hermes model documentation" in script or shell == "bash"
    assert "$HOME/.hermes" not in script
    assert "hermes completion" not in script


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("custom_root", [False, True])
def test_generated_bash_uses_owned_profiles_and_preserves_foreign_completion(tmp_path, custom_root):
    home = tmp_path / "home with spaces"
    home.mkdir()
    root = home / ("custom state with spaces" if custom_root else ".loki")
    (root / "profiles/hermes-custom").mkdir(parents=True)
    foreign = home / ".hermes/profiles/foreign-profile/canary"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"foreign profile bytes")
    script = "_hermes_profiles() { printf 'existing-foreign-completion\\n'; }\n"
    script += "complete -F _hermes_profiles hermes\n" + generate_bash(_make_parser())
    script += "\n_loki_profiles\n_hermes_profiles\ncomplete -p loki\ncomplete -p hermes\n"
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    if custom_root:
        env["LOKI_HOME"] = str(root)

    bash = shutil.which("bash", path=os.defpath)
    assert bash, "Generated completion acceptance requires native Bash with programmable completion"
    result = subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "default hermes-custom" in result.stdout
    assert "foreign-profile" not in result.stdout
    assert "existing-foreign-completion" in result.stdout
    assert "complete -F _loki_completion loki" in result.stdout
    assert "complete -F _hermes_profiles hermes" in result.stdout
    assert foreign.read_bytes() == b"foreign profile bytes"
