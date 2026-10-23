"""The mobile inline catalog uses actual scoped operation/install machinery, with a fake upstream installer."""
import json
from types import SimpleNamespace

from agent.inline_tool_executors import INLINE_TOOL_EXECUTORS, InlineToolContext
from tests.tools.test_connectors_catalog import FakeInstaller, _approve, _card, _entry


def test_mobile_catalog_approval_uses_reviewed_pin_and_keeps_credentials_out_of_result(tmp_path, monkeypatch):
    from tools.connectors import live
    from hermes_cli.config import get_env_value

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    installer = FakeInstaller([_entry('fixture-plugin', requires_env=['FIXTURE_API_TOKEN'])])
    monkeypatch.setattr('tools.connectors.catalog.HostInstaller', lambda: installer)
    monkeypatch.setattr('tools.connectors.run.WATCH_INTERVAL_SECONDS', 0.01)
    secret = 'synthetic-native-test-value'
    card = _card(_approve({'FIXTURE_API_TOKEN': secret, 'ref': 'a' * 40,
                          'agent_half': '1', 'desktop_half': '0', 'force': '0', 'enable': '1'}),
                 session_id='mobile-catalog-session', profile_home=tmp_path)
    agent = SimpleNamespace(platform='mobile', session_id='mobile-catalog-session', connection_callback=card)
    live.reset_for_tests()
    try:
        result = INLINE_TOOL_EXECUTORS['manage_catalog'](agent, {'action': 'install',
            'items': [{'kind': 'plugin', 'id': 'fixture-plugin'}]}, InlineToolContext(effective_task_id='task', tool_call_id='install'))
        value = json.loads(result)
        assert value['targets'][0]['state'] == 'connected', value
        assert card.seen[0]['targets'][0]['sha'] == 'a' * 40
        assert installer.installs == [{'name': 'fixture-plugin', 'force': False, 'enable': True,
                                      'ref': 'a' * 40, 'home': tmp_path}]
        assert get_env_value('FIXTURE_API_TOKEN') == secret
        assert secret not in result
    finally:
        live.reset_for_tests()
