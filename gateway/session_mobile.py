"""Mobile launch policy: gateway tools without a desktop renderer's bridges."""
from hermes_state_runtime import RuntimeStoreError


def mobile_toolsets(enabled, explicit, config, *, include_catalog=False):
    """Reject an explicit bridge pick; implicit profile settings keep host capabilities.

    Aliases may contain both host and client tools, so the runtime's platform guard
    also subtracts bridge tools at load/refresh/search time rather than dropping
    the whole alias and losing its usable host tools.
    """
    from toolsets import resolve_toolset, session_disabled_toolsets, session_platform_tool_drops
    if explicit is not None:
        requested = {tool for name in explicit for tool in resolve_toolset(name)}
        unsupported = requested & session_platform_tool_drops('mobile')
        if unsupported:
            raise RuntimeStoreError('invalid_params', field='toolsets',
                                    detail=f"unavailable on mobile: {', '.join(sorted(unsupported))}")
    if explicit is None and include_catalog:
        from agent.skill_utils import parse_config_string_list
        disabled = parse_config_string_list((config.get('agent') or {}).get('disabled_toolsets'))
        if 'catalog' not in disabled:
            enabled = enabled | {'catalog'}
    elif include_catalog and any('manage_catalog' in resolve_toolset(name) for name in enabled):
        # Record the same granted capability when a newly created policy picked an alias.
        enabled = enabled | {'catalog'}
    if not include_catalog:
        enabled = enabled - {'catalog'}
    return enabled - set(session_disabled_toolsets(None, 'mobile') or ())


def mobile_session_config(config, source, frozen_toolsets):
    """An older native policy cannot gain a new card tool through an alias after restart.

    Return a scoped projection, not a write to the profile or the policy's cached config.
    """
    if source != 'ios' or 'catalog' in frozen_toolsets:
        return config
    from agent.skill_utils import parse_config_string_list
    agent = config.get('agent') or {}
    disabled = parse_config_string_list(agent.get('disabled_toolsets'))
    return {**config, 'agent': {**agent, 'disabled_toolsets': sorted(set(disabled) | {'catalog'})}}
