"""Session-owned connector RPCs on the canonical authority, never sidecar session guesses."""
import asyncio
from functools import partial

from pydantic import ValidationError

from gateway.session_contract import SessionRef
from hermes_state_runtime import RuntimeStoreError

_CAPABILITIES = {'connectors.list': 'session:read', 'connectors.connect': 'session:submit',
                 'connectors.operation.status': 'session:read', 'connectors.operation.wake': 'session:respond',
                 'connection.respond': 'session:respond'}


def handlers(connection):
    return {name: partial(rpc, connection, method=name) for name in _CAPABILITIES}


def dispatch_handlers(available, method, params):
    """Account-owned calls retain the existing full-grant legacy fallback and its profile scope."""
    if method in _CAPABILITIES and isinstance(params.get('owner'), dict) and params['owner'].get('type') == 'account':
        available.pop(method, None)
    return available


def _request(connection, method, params):
    from tui_gateway.contracts.connectors import ConnectorsConnectParams, ConnectorsListParams
    from tui_gateway.contracts.connectors_operation import ConnectionOperationParams, ConnectionRespondParams
    models = {'connectors.list': ConnectorsListParams, 'connectors.connect': ConnectorsConnectParams,
              'connection.respond': ConnectionRespondParams}
    try:
        request = models.get(method, ConnectionOperationParams).model_validate(params)
    except ValidationError as exc:
        raise RuntimeStoreError('invalid_params') from exc
    if request.owner.type != 'session':
        raise RuntimeStoreError('invalid_params')
    ref = SessionRef(connection.actor.profile_id, request.owner.session_id)
    from gateway.session_busy_controls import authorize
    authorize(connection, ref, params, _CAPABILITIES[method])
    live = connection.authority.sessions[ref.session_id]
    _attached(connection, ref, live)
    return request, ref, live


def _attached(connection, ref, live):
    from gateway.session_authorities import require_serving
    require_serving(connection.authority)
    if (ref.session_id not in connection.subscriptions or connection.actor not in live.subscribers.values()
            or connection.authority.sessions.get(ref.session_id) is not live or live.superseded):
        raise RuntimeStoreError('permission_denied')


async def rpc(connection, _ref, params, *, method):
    request, ref, live = _request(connection, method, params)
    from gateway.session_authorities import owner_scope
    def run():
        from tools.connectors.gateway.errors import ToolGatewayError
        with owner_scope(connection.authority):
            try:
                _attached(connection, ref, live)
                if method == 'connectors.list':
                    result = _listing(connection, ref, live)
                else:
                    result = _operation(connection, ref, request, live, method)
                _attached(connection, ref, live)
                return result
            except ToolGatewayError as exc:
                raise RuntimeStoreError('connector_gateway_error') from exc
            except ValidationError as exc:
                raise RuntimeStoreError('connector_gateway_invalid_response') from exc
    return await asyncio.to_thread(run)


def _listing(connection, ref, live):
    import model_tools
    from tools.connectors import connectors_available
    from tools.connectors.gateway.wire import ConnectorListItem
    from tools.connectors.managed import managed_client
    from gateway.session_policy import policy_for_source
    from tui_gateway.connector_payload import connector_ui_payload
    policy = policy_for_source(connection.authority.runner, live.source)
    if policy is None:
        raise RuntimeStoreError('unsupported_runtime')
    agent = connection.authority.agent(ref)
    enabled = getattr(agent, 'enabled_toolsets', None) if agent is not None else list(policy.current_toolsets(policy.config()))
    disabled = getattr(agent, 'disabled_toolsets', None)
    if ('manage_connections' not in model_tools._select_tool_names(enabled, disabled, quiet_mode=True)
            or not connectors_available()):
        return {'available': False, 'connectors': []}
    rows = managed_client().list_connectors()
    return {'available': True, 'connectors': connector_ui_payload([
        ConnectorListItem.model_validate(row).model_dump(mode='json', by_alias=False) for row in rows])}


def _binding(connection, request, live, *, mutate):
    from gateway.local_connections import ConnectionBinding
    binding = live.connection_operation
    if (not isinstance(binding, ConnectionBinding) or binding.authority is not connection.authority
            or not binding.current() or (hasattr(request, 'op_id') and request.op_id != binding.operation.op_id)):
        raise RuntimeStoreError('unknown_operation')
    if mutate and not binding.active():
        raise RuntimeStoreError('stale_generation')
    return binding


def _operation(connection, ref, request, live, method):
    from tui_gateway.connector_payload import connector_ui_payload
    with live.event_stream.lock:
        _attached(connection, ref, live)
        binding = _binding(connection, request, live, mutate=method != 'connectors.operation.status')
        operation = binding.operation
        if method == 'connectors.operation.status':
            snapshot = operation.snapshot()
            return connector_ui_payload({**snapshot, 'settled': operation.settled})
        if method == 'connectors.operation.wake':
            operation.wake.set()
            return {'status': 'ok'}
        if method == 'connection.respond':
            return _answer(operation, request)
    # Retry can mint over HTTP. The operation's own lock protects its transitions; holding the
    # stream lock across that request would stop interrupt/detach and block every session event.
    if method == 'connectors.connect':
        result = _reissue(operation, request)
        with live.event_stream.lock:
            _attached(connection, ref, live)
            _binding(connection, request, live, mutate=True)
        return result


def _answer(operation, request):
    from tools.connectors.contract import SettleReason
    from tools.connectors.operation import IllegalTransition
    from tools.connectors.run import apply_answer
    try:
        apply_answer(operation, request.result.model_dump_json(exclude_none=True))
    except (IllegalTransition, ValueError) as exc:
        raise RuntimeStoreError('invalid_answer') from exc
    if not operation.settled and operation.all_resolved:
        operation.settle(SettleReason.all_resolved)
    return {'status': 'ok', 'settled': operation.settled}


def _reissue(operation, request):
    from tools.connectors.run import reissue
    from tui_gateway.connector_payload import connector_ui_payload
    for name in request.connectors:
        target = operation.target(name)
        if target is None or (request.alias is not None and request.alias != target.alias) or (
                request.connection_id not in (None, target.repair_id, target.connection_id)):
            raise RuntimeStoreError('unknown_target')
    reason = reissue(operation, request.connectors)
    if reason:
        raise RuntimeStoreError(reason)
    return connector_ui_payload({**operation.snapshot(), 'settled': operation.settled})
