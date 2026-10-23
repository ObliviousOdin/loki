"""Creation identity survives concurrent processes, normal store mutations and restart."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.waiting import wait_until

REQUEST = {'request_id': 'create-request-0123456789', 'principal_id': 'verified-provider-user'}
OPTIONS = {'prompt': 'A quiet morning brief', 'schedule': 'every 2h', 'name': 'Morning'}
CHILD = '''
import json,sys
from pathlib import Path
from cron.jobs import create_job
from tests.waiting import wait_until
Path(sys.argv[1]).write_text('ready')
wait_until(Path(sys.argv[2]).exists, timeout=20, what='concurrent cron writers released')
try:
    print(json.dumps({'id': create_job(**json.loads(sys.argv[3]), creation_request=json.loads(sys.argv[4]))['id']}))
except ValueError as exc:
    print(json.dumps({'reason': str(exc)}))
'''


def concurrent_creates(home, tmp_path, *, count=3):
    repo = Path(__file__).resolve().parents[2]
    start = tmp_path / 'start'
    env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'LANG', 'TZ') if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), HERMES_HOME=str(home))
    processes = []
    try:
        for index in range(count):
            ready = tmp_path / f'ready-{index}'
            processes.append(subprocess.Popen([sys.executable, '-c', CHILD, str(ready), str(start),
                json.dumps(OPTIONS), json.dumps(REQUEST)], cwd=repo, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        wait_until(lambda: all((tmp_path / f'ready-{index}').exists() for index in range(count)),
                   timeout=20, what='all concurrent cron creators ready')
        start.touch()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
            results.append(json.loads(stdout))
        return results
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def test_concurrent_creation_and_restart_keep_one_job_and_a_deletion_receipt(tmp_path, monkeypatch):
    from cron import jobs
    from cron.job_creation_receipts import CreationConflict

    home = tmp_path / 'home'
    home.mkdir()
    ids = {result['id'] for result in concurrent_creates(home, tmp_path)}
    assert len(ids) == 1
    job_id = ids.pop()
    with jobs.use_cron_store(home):
        assert len(jobs.load_jobs()) == 1
        jobs.update_job(job_id, {'name': 'Renamed after creation'})
        jobs.pause_job(job_id)
        jobs.resume_job(job_id)
        jobs.create_job('Legacy sibling', 'every 3h')
        retry = jobs.create_job(**OPTIONS, creation_request=REQUEST)
        assert retry['id'] == job_id and retry['name'] == 'Renamed after creation'
        for intent, identity in (({**OPTIONS, 'prompt': 'Changed intent'}, REQUEST),
                                 (OPTIONS, {**REQUEST, 'principal_id': 'another-user'})):
            with pytest.raises(CreationConflict, match='creation_request_conflict'):
                jobs.create_job(**intent, creation_request=identity)
        assert jobs.remove_job(job_id)
        with pytest.raises(CreationConflict, match='creation_target_deleted'):
            jobs.create_job(**OPTIONS, creation_request=REQUEST)
        ledger = json.loads((home / 'cron/jobs.json').read_text())['creation_receipts']
        assert ledger[REQUEST['request_id']]['job_id'] == job_id
        monkeypatch.setattr(jobs, '_acquire_flock', lambda *args: None)
        with pytest.raises(CreationConflict, match='creation_store_unavailable'):
            jobs.create_job(**OPTIONS, creation_request={**REQUEST, 'request_id': 'another-request-0123456789'})
    restarted = tmp_path / 'restart'
    restarted.mkdir()
    assert concurrent_creates(home, restarted, count=1) == [{'reason': 'creation_target_deleted'}]


def test_receipt_cannot_be_rebound_by_copying_a_store_into_another_profile(tmp_path):
    from cron import jobs
    from cron.job_creation_receipts import CreationConflict

    first, second = tmp_path / 'first', tmp_path / 'second'
    with jobs.use_cron_store(first):
        jobs.create_job(**OPTIONS, creation_request=REQUEST)
    (second / 'cron').mkdir(parents=True)
    shutil.copy2(first / 'cron/jobs.json', second / 'cron/jobs.json')
    with jobs.use_cron_store(second), pytest.raises(CreationConflict, match='creation_request_conflict'):
        jobs.create_job(**OPTIONS, creation_request=REQUEST)
