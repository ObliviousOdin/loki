"""A committed reply cannot be classified using an earlier admission snapshot."""
import asyncio

import pytest

from gateway import session_bot
from gateway.session_contract import SessionRef
from hermes_state import SessionDB
from hermes_state_runtime import (
    admit_session_input, claim_session_input,
    get_session_admission, list_session_admissions, settle_session_input,
)

pytest_plugins = ('tests.gateway.test_session_bot_retry',)


def _settle_between_reads(monkeypatch, writer, epoch, row, outcome, reply):
    """Commit through another SQLite connection after the projector's first real read."""
    read = session_bot.get_session_admission
    snapshots = []

    def read_then_settle(db, *, admission_id):
        snapshot = read(db, admission_id=admission_id)
        if admission_id == row['admission_id'] and not snapshots:
            snapshots.append(snapshot)
            settle_session_input(writer, epoch=epoch, admission_id=admission_id,
                generation=row['generation'], outcome=outcome,
                result={'result': {'final_response': reply}, 'usage': {}})
        return snapshot

    monkeypatch.setattr(session_bot, 'get_session_admission', read_then_settle)
    return snapshots


@pytest.mark.parametrize(('outcome', 'reply', 'status', 'visible_reply'), [
    ('completed', 'exact reply', 'settled', 'exact reply'),
    ('completed', ' *NO_REPLY* ', 'settled', ''),
    ('failed', 'provider refused', 'failed', 'provider refused'),
    ('interrupted', 'partial reply', 'failed', 'partial reply'),
])
def test_receipt_uses_the_outcome_committed_with_its_reply(
        owner, tmp_path, monkeypatch, outcome, reply, status, visible_reply):
    db = owner.db
    db.create_session('bot', source='gui')
    admission = admit_session_input(db, epoch=owner.epoch, principal_id='owner',
        session_id='bot', request_id='one', payload={'text': 'hello'})
    row = claim_session_input(db, epoch=owner.epoch, session_id='bot')
    record = dict(status='canonical', admission_id=admission['admission_id'],
        delivery_id='a' * 32, profile_home=str(tmp_path), session_id='bot', message='hello')
    writer = SessionDB(db.db_path)
    try:
        snapshots = _settle_between_reads(monkeypatch, writer, owner.epoch, row, outcome, reply)
        receipt = session_bot._result(owner, record)
        assert snapshots[0]['status'] == 'started' and snapshots[0]['outcome'] is None
        assert get_session_admission(db, admission_id=row['admission_id'])['outcome'] == outcome
        assert (receipt['status'], receipt['reply']) == (status, visible_reply)
        assert ('error' in receipt) == (status == 'failed')
        assert 'retry_admission_id' not in receipt
        assert len(list_session_admissions(db, session_id='bot', pending_only=False)) == 1
    finally:
        writer.close()


@pytest.mark.asyncio
async def test_paused_mailbox_settles_when_publication_crosses_the_result_read(bot, monkeypatch):
    from tests.gateway.test_session_bot_retry import _settle_quietly
    from tools import bot_live_delivery as mailbox

    authority = bot.authority
    monkeypatch.setattr(authority, '_schedule', lambda ref: None)
    key = 'b' * 32
    receipt = await session_bot.deliver(bot.connection,
        dict(id=key, profile='default', message='paused'))
    ref = SessionRef(authority.profile_id, receipt['session_id'])
    authority._pause(ref, 'unknown_execution')
    await _settle_quietly(bot)
    assert mailbox.read_delivery_result(bot.home, key)['status'] == 'queued'
    row = claim_session_input(authority.db, epoch=authority.epoch, session_id=ref.session_id)
    writer = SessionDB(authority.db.db_path)
    entered, release = asyncio.Event(), asyncio.Event()
    projected = []
    write = session_bot.write_receipt

    async def hold_projection(home, record):
        projected.append(dict(record))
        if not entered.is_set():
            entered.set()
            await release.wait()
        await write(home, record)

    monkeypatch.setattr(session_bot, 'write_receipt', hold_projection)
    monkeypatch.setattr(mailbox, 'authority_delivery',
        lambda *args, **kwargs: pytest.fail('local receipt reader dialed authority'))
    try:
        snapshots = _settle_between_reads(monkeypatch, writer, authority.epoch,
            row, 'completed', 'pong')
        authority._publish_pending(ref)
        await asyncio.wait_for(entered.wait(), 5)
        assert snapshots[0]['status'] == 'started'
        # Settlement publication arrives while the first projection still owns the mailbox.
        authority._publish_pending(ref)
        assert key in authority._bot_receipt_dirty
        release.set()
        await _settle_quietly(bot)
        final = mailbox.read_delivery_result(bot.home, key)
        assert (final['status'], final['reply']) == ('settled', 'pong')
        assert all(record['status'] == 'settled' for record in projected)
        assert 'error' not in final and 'retry_admission_id' not in final
        rows = list_session_admissions(authority.db, session_id=ref.session_id, pending_only=False)
        assert [(item['request_id'], item['outcome']) for item in rows] == [('bot:' + key, 'completed')]
        assert key not in authority._bot_receipt_index
        assert not authority._bot_reply_watchers
    finally:
        release.set()
        await _settle_quietly(bot)
        writer.close()
