"""A native phone is a distinct session surface without Electron renderer bridges."""
import pytest


def test_ios_launch_is_mobile_without_desktop_affordances(tmp_path):
    from gateway.session_policy import build_policy
    from toolsets import CLIENT_SURFACE_TOOLSETS

    policy = build_policy({'source': 'ios', 'cwd': str(tmp_path), 'follow_profile_config': True},
                          {'platform_toolsets': {'cli': ['terminal', 'connections']}})
    assert policy.source == 'ios' and policy.platform == 'mobile'
    assert 'terminal' in policy.toolsets and 'connections' in policy.toolsets
    assert CLIENT_SURFACE_TOOLSETS.intersection(policy.toolsets) == {'catalog'}
    assert CLIENT_SURFACE_TOOLSETS.intersection(policy.current_toolsets(
        {'platform_toolsets': {'cli': ['terminal', 'desktop_ui', 'project', 'catalog']}})) == {'catalog'}


def test_mobile_tool_guard_survives_aliases_and_rejects_explicit_desktop_picks(tmp_path, monkeypatch):
    import model_tools
    import toolsets
    from gateway.session_policy import build_policy
    from hermes_state_runtime import RuntimeStoreError

    monkeypatch.setitem(toolsets.TOOLSETS, 'mixed-client-fixture', {
        'description': 'Fixture alias with both host and client tools',
        'tools': [], 'includes': ['terminal', 'desktop_ui', 'project', 'catalog', 'onboarding']})
    disabled = toolsets.session_disabled_toolsets(None, 'mobile')
    selected = model_tools._select_tool_names(['mixed-client-fixture'], disabled, quiet_mode=True)
    assert 'terminal' in selected
    assert 'manage_catalog' in selected
    assert not {'desktop_preview', 'desktop_project', 'setup_beat'}.intersection(selected)
    assert {'desktop_preview', 'desktop_project'} <= toolsets.session_platform_tool_drops('mobile')
    assert 'desktop_preview' not in toolsets.session_platform_tool_drops('desktop')
    for requested in ('desktop_ui', 'project', 'mixed-client-fixture'):
        with pytest.raises(RuntimeStoreError, match='invalid_params') as error:
            build_policy({'source': 'ios', 'cwd': str(tmp_path), 'toolsets': [requested]}, {})
        assert error.value.field == 'toolsets'
    assert 'catalog' in build_policy({'source': 'ios', 'cwd': str(tmp_path), 'toolsets': ['catalog']}, {}).toolsets
