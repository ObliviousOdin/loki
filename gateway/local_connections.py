"""Connection cards bound to one canonical session's exact running turn."""
from dataclasses import dataclass


@dataclass
class ConnectionBinding:
    authority: object
    session_id: str
    generation: int
    route: str
    stream: object
    operation: object

    def current(self):
        live = self.authority.sessions.get(self.session_id)
        return (live is not None and live.event_stream is self.stream and live.route == self.route
                and live.connection_operation is self and not live.superseded
                and not getattr(self.authority, 'retired', False))

    def active(self):
        return self.current() and self.authority.executing.get(self.session_id) == self.generation

    def changed(self, operation, change, snapshot):
        from tui_gateway.connector_payload import connector_ui_payload
        with self.stream.lock:
            if operation is not self.operation or not self.active():
                return
            payload = {**snapshot, 'settled': snapshot.get('settled_at') is not None,
                       'owner': {'type': 'session', 'session_id': self.session_id}, **(change or {})}
            self.authority.publish_execution(self.session_id, self.generation, 'connection.update',
                                             connector_ui_payload(payload))


def wire(turn, agent):
    """The model's existing tool owns mint/watch/settle; its callback only projects the card."""
    owner = getattr(turn, '_approval_owner', None)
    if owner is None or getattr(agent, 'platform', None) not in {'desktop', 'mobile'}:
        return
    authority, session_id, generation = owner
    live = authority.sessions.get(session_id)
    if live is None:
        return

    def show(payload):
        from tools.connectors import live as operations
        from tui_gateway.connector_payload import connector_ui_payload
        operation = operations.get(live.route, payload.get('op_id'), profile_home=authority.profile_id)
        if operation is None:
            return
        binding = ConnectionBinding(authority, session_id, generation, live.route, live.event_stream, operation)
        with live.event_stream.lock:
            if (authority.sessions.get(session_id) is not live or live.superseded
                    or getattr(authority, 'retired', False) or authority.executing.get(session_id) != generation):
                return
            live.connection_operation = binding
            operation.change_callback = binding.changed
            authority.publish_execution(session_id, generation, 'connection.request', connector_ui_payload(payload))
    agent.connection_callback = show


def pending_connection(authority, session_id):
    live = authority.sessions.get(session_id)
    if live is not None:
        with live.event_stream.lock:
            binding = live.connection_operation
            if isinstance(binding, ConnectionBinding) and binding.active() and not binding.operation.settled:
                from tui_gateway.connector_payload import connector_ui_payload
                return connector_ui_payload(binding.operation.request_payload())
    return None
