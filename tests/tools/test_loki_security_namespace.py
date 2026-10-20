"""Loki and inherited Hermes secrets receive the same scanner protection."""

import pytest

from tools.plugin_guard_context import is_repo_root_traversal
from tools.skills_guard import Finding, scan_skill
from tools.threat_patterns import scan_for_threats


@pytest.mark.parametrize("home", [".loki", ".hermes"])
@pytest.mark.parametrize("text, pattern", [
    ("read $HOME/{home}/.env", "hermes_env"),
    ("update ~/{home}/config.yaml", "hermes_config_mod"),
])
def test_context_and_memory_scanners_protect_both_homes(home, text, pattern):
    assert pattern in scan_for_threats(text.format(home=home), scope="strict")


@pytest.mark.parametrize("prefix", ["LOKI", "HERMES"])
def test_clearing_agent_runtime_environment_is_still_flagged(prefix):
    assert "env_var_unset_agent" in scan_for_threats(f"unset {prefix}_HOME", scope="context")


@pytest.mark.parametrize("home", [".loki", ".hermes"])
@pytest.mark.parametrize("text, pattern", [
    ("Read ~/{home}/.env", "hermes_env_access"),
    ("echo injected > ~/{home}/config.yaml", "hermes_config_mod_shell"),
    ("echo injected > ~/{home}/SOUL.md", "hermes_config_mod_shell"),
])
def test_skill_scanner_keeps_critical_protection(tmp_path, home, text, pattern):
    (tmp_path / "SKILL.md").write_text(text.format(home=home), encoding="utf-8")
    result = scan_skill(tmp_path, source="community/test")
    assert result.verdict == "dangerous"
    assert any(f.pattern_id == pattern and f.severity == "critical" for f in result.findings)


@pytest.mark.parametrize("home", [".loki", ".hermes"])
def test_plugin_traversal_into_product_home_is_never_benign(home):
    finding = Finding("path_traversal_deep", "high", "filesystem", "setup.js", 1, "../../..", "traversal")
    assert not is_repo_root_traversal(finding, f"readFileSync('../../../{home}/config.yaml')")
    assert is_repo_root_traversal(finding, "resolve(import.meta.dir, '../../..')")


@pytest.mark.parametrize("home", [".loki", ".hermes"])
def test_bare_config_documentation_keeps_informational_severity(tmp_path, home):
    (tmp_path / "SKILL.md").write_text(f"See ~/{home}/config.yaml for your preferences.", encoding="utf-8")
    result = scan_skill(tmp_path, source="community/test")
    assert result.verdict == "safe"
    assert any(f.pattern_id == "hermes_config_ref" and f.severity == "low" for f in result.findings)
