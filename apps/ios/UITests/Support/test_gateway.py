"""Loopback-only developer fixture. Never imported or bundled by the iOS application."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

REPO = Path(__file__).resolve().parents[4]


def isolated_environment(home):
    kept = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'LANG', 'TZ') if key in os.environ}
    os.environ.clear()
    os.environ.update(kept, HOME=str(home / 'user'), USERPROFILE=str(home / 'user'),
                      LOKI_HOME=str(home / 'state'), LOKI_RUNTIME_DIR=str(home / 'runtime'),
                      HERMES_HOME=str(home / 'state'), HERMES_RUNTIME_DIR=str(home / 'runtime'),
                      OPENAI_API_KEY='local-ui-test-placeholder')
    for child in ('user', 'state', 'runtime'):
        (home / child).mkdir()
    sys.path.insert(0, str(REPO))


async def serve(port, ready_file):
    from gateway.run import GatewayRunner
    from gateway.run_api import start_gateway_api, stop_gateway_api
    from gateway.run_runtime import initialize_gateway_runtime
    from gateway.runtime_ownership import process_ownership
    from hermes_cli import web_server
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from local_identity import LocalIdentity
    from scripted_peer import TestCatalogInstaller, TestConnectorService
    from tools.connectors import catalog, managed

    identity = LocalIdentity()
    clear_providers()
    register_provider(identity)
    identity.install(web_server.app)
    service = TestConnectorService()
    managed.managed_client = lambda **kwargs: service
    catalog.HostInstaller = TestCatalogInstaller
    launch_home = Path(os.environ['HERMES_HOME'])
    process_ownership.reserve([launch_home])
    runner = GatewayRunner()
    await initialize_gateway_runtime(runner)
    runner._record_served_profiles('default', [('default', launch_home)])
    runner._running = True
    # The fixture has no service-manager PID identity. Exercise the production periodic
    # reconcile rather than pretending its launcher owns the gateway control socket.
    watcher = asyncio.create_task(runner._profile_reconcile_watcher(interval=0.1))
    api = await start_gateway_api(runner, host='127.0.0.1', port=port)
    api.app.state.auth_required = True
    runner.session_runtime_descriptor.update(state='ready', api_origin=api.api_origin)
    ready_file.write_text(json.dumps({'kind': 'loki-ios-ui-test-gateway', 'test_only': True,
        'origin': api.api_origin, 'provider': identity.name, 'client_id': 'loki-ios',
        'callback': 'com.loki.ios://auth/callback', 'pid': os.getpid(),
        'instance_id': runner.session_runtime_descriptor['instance_id']}, indent=2) + '\n')
    print(f'LOCAL TEST ONLY: {api.api_origin} — synthetic identity, scripted model, no vendor accounts.', flush=True)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await stopped.wait()
    finally:
        runner._running = False
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        from tools import clarify_gateway
        from tools.approval import resolve_gateway_approval
        from tools.connectors.contract import SettleReason
        authorities = list(runner.session_authorities)
        for live in [live for authority in authorities for live in authority.sessions.values()]:
            resolve_gateway_approval(live.route, 'deny', resolve_all=True)
            clarify_gateway.clear_session(live.route)
            if live.connection_operation is not None:
                live.connection_operation.operation.settle(SettleReason.interrupt)
        tasks = [live.task for authority in authorities for live in authority.sessions.values() if live.task is not None]
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 20)
        await stop_gateway_api(api)
        from gateway.run_runtime import release_profile_home, unserve_profile_runtime
        for authority in authorities[1:]:
            await unserve_profile_runtime(runner, Path(authority.profile_id))
            release_profile_home(runner, Path(authority.profile_id))
        runner.session_store._db.close()
        process_ownership.release(launch_home)
        clear_providers()


def main():
    import faulthandler
    faulthandler.register(signal.SIGUSR1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='loki-ios-ui-test-') as temporary:
        home = Path(temporary)
        isolated_environment(home)
        from scripted_peer import start_peer
        from hermes_cli.config import atomic_config_write
        peer = start_peer(home)
        model_url = f'http://127.0.0.1:{peer.server_port}/v1'
        os.environ['OPENAI_BASE_URL'] = model_url
        atomic_config_write(home / 'state' / 'config.yaml', {
            'model': {'default': 'loki-ui-test', 'provider': 'custom', 'base_url': model_url, 'context_length': 256000},
            'terminal': {'env_type': 'local', 'cwd': str(home)},
            'approvals': {'mode': 'manual', 'timeout': 300},
            'streaming': {'enabled': True}, 'platform_toolsets': {'cli': ['terminal', 'clarify', 'connections']},
            'gateway': {'multiplex_profiles': True},
            'auxiliary': {'title_generation': {'enabled': False}},
            'dashboard': {'native_auth': {'clients': {'loki-ios': {'redirect_uris': ['com.loki.ios://auth/callback']}}}}})
        from tools.memory_tool import load_on_disk_store, memory_tool
        memory = json.loads(memory_tool(action='add', target='user',
            content='LOCAL UI TEST FIXTURE: I prefer a calm, clear workspace.', store=load_on_disk_store()))
        if not memory.get('success'):
            raise RuntimeError('Could not seed the isolated test memory')
        try:
            asyncio.run(serve(args.port, args.ready_file))
        finally:
            peer.shutdown()
            peer.server_close()


if __name__ == '__main__':
    main()
