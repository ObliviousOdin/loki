"""A native approval consumer enables only the existing catalog edge on new iOS policies."""
from dataclasses import replace


def test_fresh_native_catalog_preserves_explicit_disable_and_existing_policy(tmp_path):
    from gateway.session_policy import build_policy

    config = {'platform_toolsets': {'cli': ['terminal', 'connections']}}
    fresh = build_policy({'source': 'ios', 'cwd': str(tmp_path), 'follow_profile_config': True}, config)
    assert 'catalog' in fresh.toolsets
    assert 'catalog' in fresh.current_toolsets(config)
    assert not {'desktop_ui', 'project', 'onboarding'}.intersection(fresh.toolsets)
    legacy = replace(fresh, toolsets=tuple(name for name in fresh.toolsets if name != 'catalog'))
    assert 'catalog' not in legacy.current_toolsets(config)
    disabled = {**config, 'agent': {'disabled_toolsets': ['catalog']}}
    policy = build_policy({'source': 'ios', 'cwd': str(tmp_path)}, disabled)
    assert 'catalog' not in policy.toolsets
    assert 'catalog' not in fresh.current_toolsets(disabled)
    from gateway.session_policy_refresh import refreshed_policy
    resumed, _, _ = refreshed_policy(fresh, config, {'TERMINAL_CWD': str(tmp_path)})
    assert 'catalog' in resumed.toolsets
    old_resumed, _, _ = refreshed_policy(legacy, config, {'TERMINAL_CWD': str(tmp_path)})
    assert 'catalog' not in old_resumed.toolsets


def test_mobile_catalog_alias_load_and_search_keep_electron_bridges_excluded(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import model_tools
    import toolsets
    from agent.agent_init import _load_tools

    assert 'manage_catalog' not in toolsets.resolve_toolset('all')
    monkeypatch.setitem(toolsets.TOOLSETS, 'mobile-catalog-alias', {
        'description': 'Fixture catalog plus renderer alias', 'tools': [],
        'includes': ['catalog', 'desktop_ui', 'project']})
    monkeypatch.setattr('hermes_cli.plugins.discover_plugins', lambda: None)
    agent = SimpleNamespace(quiet_mode=True, platform='mobile', enabled_toolsets=['mobile-catalog-alias'], disabled_toolsets=None)
    _load_tools(agent, agent.enabled_toolsets, None)
    found = json.loads(model_tools.handle_function_call('tool_search', {'queries': ['catalog plugin install']},
        enabled_toolsets=agent.enabled_toolsets, disabled_toolsets=agent.disabled_toolsets))
    assert 'manage_catalog' in json.dumps(agent.tools) + json.dumps(found)
    assert {'desktop_preview', 'desktop_project'} <= toolsets.session_platform_tool_drops('mobile')
    from gateway.session_policy import build_policy
    from gateway.session_local_inventory import _policy_tools
    config = {'platform_toolsets': {'cli': ['mobile-catalog-alias']}}
    fresh = build_policy({'source': 'ios', 'cwd': str(tmp_path)}, config)
    assert 'catalog' in fresh.toolsets
    legacy = replace(fresh, toolsets=('mobile-catalog-alias',), config_json=json.dumps(config))
    _, old_tools = _policy_tools(legacy, legacy.config())
    assert 'manage_catalog' not in json.dumps(old_tools)
    assert config == {'platform_toolsets': {'cli': ['mobile-catalog-alias']}}
