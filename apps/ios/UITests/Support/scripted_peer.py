"""Deterministic local model/connector substitutes; the real gateway still owns each turn."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shlex
import time
from types import SimpleNamespace


def answer(messages, target):
    last_user = max((i for i, message in enumerate(messages) if message.get('role') == 'user'), default=-1)
    prompt = str(messages[last_user].get('content', '')).lower() if last_user >= 0 else ''
    calls = [call.get('function', {}).get('name') for message in messages[last_user + 1:]
             for call in message.get('tool_calls') or []]
    catalog = 'install test support' in prompt
    if any(message.get('role') == 'tool' for message in messages[last_user + 1:]) and not (catalog and 'tool_call' not in calls):
        return {'role': 'assistant', 'content': 'The local test step is complete. No real service was contacted.'}
    tool = None
    if 'approval' in prompt:
        target.mkdir(exist_ok=True)
        (target / 'disposable.txt').write_text('Created by the local UI test gateway.\n')
        tool = ('terminal', {'command': 'rm -r -- ' + shlex.quote(str(target))})
    elif 'question' in prompt or 'clarify' in prompt:
        tool = ('clarify', {'questions': [{'question': 'Which quiet moment should we plan?',
                                         'choices': ['A walk', 'A cup of tea']}]})
    elif catalog:
        tool = catalog_step(calls)
    elif 'hubspot' in prompt or 'connect' in prompt:
        tool = ('manage_connections', {'action': 'connect', 'connectors': ['hubspot']})
    if tool is not None:
        return {'role': 'assistant', 'content': None, 'tool_calls': [{
            'id': f'ui-test-tool-{last_user}', 'type': 'function',
            'function': {'name': tool[0], 'arguments': json.dumps(tool[1])}}]}
    if 'show code' in prompt:
        return {'role': 'assistant', 'content': 'Here is a small, calm beginning.\n\n```swift\nstruct QuietMoment {\n    let message = "One step at a time."\n\n    func begin() {\n        print(message)\n    }\n}\n```\n\nYour next step can stay small.'}
    return {'role': 'assistant', 'content': 'Hello from the local test gateway. Let us take one calm step at a time.'}


def catalog_step(calls):
    if 'tool_search' not in calls:
        return 'tool_search', {'queries': ['catalog plugin install']}
    if 'tool_describe' not in calls:
        return 'tool_describe', {'names': ['manage_catalog']}
    return 'tool_call', {'calls': [{'name': 'manage_catalog', 'arguments': {
        'action': 'install', 'items': [{'kind': 'plugin', 'id': 'loki-ui-test-support'}]}}]}


class ModelPeer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return None

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"loki-ui-test","object":"model"}]}')

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        message = answer(request.get('messages', []), self.server.target)
        self.server.requests += 1
        finish = 'tool_calls' if message.get('tool_calls') else 'stop'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if request.get('stream') else 'application/json')
        self.end_headers()
        if request.get('stream'):
            if message.get('tool_calls'):
                message['tool_calls'][0]['index'] = 0
                deltas = [message]
            else:
                deltas = [{'role': 'assistant', 'content': chunk} for chunk in re.findall(r'\S+\s*|\s+', message['content'])]
            for delta in deltas + [{}]:
                chunk = {'id': 'local-ui-test', 'object': 'chat.completion.chunk', 'created': 1,
                         'model': 'loki-ui-test', 'choices': [{'index': 0, 'delta': delta,
                         'finish_reason': finish if not delta else None}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
        else:
            self.wfile.write(json.dumps({'id': 'local-ui-test', 'object': 'chat.completion', 'created': 1,
                'model': 'loki-ui-test', 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}).encode())
        self.wfile.flush()


def start_peer(home):
    from agent.memory_provider import spawn_context_thread
    server = ThreadingHTTPServer(('127.0.0.1', 0), ModelPeer)
    server.target = Path(home) / 'disposable-approval-target'
    server.requests = 0
    spawn_context_thread(server.serve_forever, name='loki-ui-test-model').start()
    return server


class TestConnectorService:
    """Only the remote vendor boundary is synthetic; operation ownership/watch/replay stay real."""
    def __init__(self):
        self.account_states = {}

    def list_connectors(self):
        return [{'connector': 'hubspot', 'enabled': True,
                 'connected': any(status == 'active' for status in self.account_states.values())}]

    def connections(self, connectors, **kwargs):
        account = kwargs.get('connection_id') or f'ca_ui_test_{time.time_ns()}'
        self.account_states[account] = 'pending'
        return {'results': [{'connector': name, 'status': 'initiated', 'connection_id': account,
                             'instruction': 'Synthetic local UI test. Use Not now or Continue; no vendor login.'}
                            for name in connectors]}

    def account_status(self, connection_id, **kwargs):
        return {'status': self.account_states[connection_id]}


class TestCatalogInstaller:
    """Synthetic upstream installer: real approval ownership, no downloaded or executed plugin code."""
    def plugin_entry(self, name):
        if name != 'loki-ui-test-support':
            return None
        return SimpleNamespace(name=name, title='Local UI test support',
            repo='https://example.invalid/loki-ui-test-support', sha='a' * 40, subdir='', tier='community',
            description='Synthetic local approval fixture. No third-party code will be installed.',
            requires_hermes='', platforms=[], capabilities=SimpleNamespace(requires_env=['LOKI_UI_TEST_VALUE']))

    def refuse(self, entry):
        return None

    def install_plugin(self, name, *, force, enable, ref, on_step):
        from hermes_cli.plugin_install_phase import InstallPhase
        on_step(InstallPhase.downloading)
        return {'ok': True, 'plugin_name': name, 'missing_env': [],
                'activation': {'live_now': {'mcp_servers': [], 'skills': []}}}

    def skill_meta(self, identifier):
        return None

    def install_skill(self, identifier, *, force):
        raise RuntimeError('This local fixture does not install skills')
