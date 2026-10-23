"""Immutable creation intents committed in the same atomic payload as scheduled jobs."""
import hashlib
import json
import re


class CreationConflict(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _read(path, *, replace=False):
    from cron import jobs as store
    if not path.exists():
        return {}
    try:
        data, _ = store._parse_jobs_file(path)
    except (ValueError, OSError):
        if replace:
            return {}  # existing explicit disaster-recovery replacement semantics
        raise
    receipts = data.get('creation_receipts', {}) if isinstance(data, dict) else {}
    if not isinstance(receipts, dict):
        raise ValueError('Invalid cron creation receipts')
    for key, receipt in receipts.items():
        if (not isinstance(key, str) or not isinstance(receipt, dict) or receipt.get('version') != 1
                or not all(isinstance(receipt.get(field), str) and receipt[field]
                           for field in ('profile_id', 'principal_id', 'fingerprint', 'job_id'))):
            raise ValueError('Invalid cron creation receipt')
    return receipts


def payload(path, jobs, updated_at, *, proposed=None, replace=False):
    """Every normal save preserves the ledger, including update, deletion and scheduler writes."""
    receipts = _read(path, replace=replace)
    for key, receipt in (proposed or {}).items():
        if key in receipts and receipts[key] != receipt:
            raise CreationConflict('creation_request_conflict')
        receipts[key] = receipt
    value = {'jobs': jobs, 'updated_at': updated_at}
    if receipts:
        value['creation_receipts'] = receipts
    return value


def _identity(request, options):
    from cron import jobs as store
    from hermes_constants import hermes_home_key
    if (not isinstance(request, dict) or set(request) != {'request_id', 'principal_id'}
            or not isinstance(request.get('request_id'), str)
            or re.fullmatch(r'[A-Za-z0-9_-]{16,128}', request['request_id']) is None
            or not isinstance(request.get('principal_id'), str) or not request['principal_id']):
        raise CreationConflict('invalid_creation_request')
    encoded = json.dumps(options, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return {'version': 1, 'profile_id': hermes_home_key(store._current_cron_store().cron_dir.parent),
            'principal_id': request['principal_id'], 'fingerprint': hashlib.sha256(encoded.encode()).hexdigest()}


def create(request, options, build):
    from cron import jobs as store
    expected = _identity(request, options)
    with store._jobs_lock():
        # Ordinary legacy writes can degrade to in-process locking. A durable creation cannot
        # promise cross-process uniqueness under that degradation, so this consumer fails closed.
        if not getattr(store._jobs_lock_state, 'cross_process', False):
            raise CreationConflict('creation_store_unavailable')
        receipts = _read(store._current_cron_store().jobs_file)
        jobs = store.load_jobs()
        existing = receipts.get(request['request_id'])
        if existing is not None:
            if any(existing.get(key) != value for key, value in expected.items()):
                raise CreationConflict('creation_request_conflict')
            found = next((job for job in jobs if job.get('id') == existing['job_id']), None)
            if found is None:
                raise CreationConflict('creation_target_deleted')
            return store._normalize_job_record(found)
        job = build()
        receipts[request['request_id']] = {**expected, 'job_id': job['id']}
        store.save_jobs(jobs + [job], creation_receipts=receipts)
        return job
