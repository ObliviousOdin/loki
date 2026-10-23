"""Owner-only persistent phone grants. One captured launch home, never an ambient profile."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from hermes_cli.dashboard_auth.base import Session
from hermes_cli.dashboard_auth.device_links_crypto import (
    CLIENT_ID, LinkError, b64, claim_payload, fingerprint, json_payload, normalize_code,
    opaque, public_wire, sign, verify)

PAIR_TTL = 300
CHALLENGE_TTL = 60
TOKEN_TTL = 900
_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'


def _hash(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _id(prefix: str) -> str:
    return prefix + '_' + secrets.token_urlsafe(24)


def _identity(session: Session) -> dict:
    if not session.user_id or not session.provider or session.expires_at <= int(time.time()):
        raise LinkError('owner_sign_in_required')
    return {k: getattr(session, k) for k in (
        'user_id', 'email', 'display_name', 'org_id', 'provider', 'issuer')}


class DeviceLinkStore:
    """Transactions serialize claim/approval/replay/revocation across processes and restarts."""

    def __init__(self, home: Path, *, gateway_url: str, host_name: str):
        home = home.resolve()
        self.home = str(home)
        self.gateway_url, self.host_name = gateway_url, host_name
        self._lock = threading.RLock()
        directory = home / 'auth' / 'device-links'
        if (home / 'auth').is_symlink() or directory.is_symlink():
            raise LinkError('unsafe_device_store')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink():
            raise LinkError('unsafe_device_store')
        os.chmod(directory, 0o700)
        self.path = directory / 'grants.sqlite3'
        if self.path.is_symlink():
            raise LinkError('unsafe_device_store')
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self._transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pairings (id TEXT PRIMARY KEY, code_hash TEXT NOT NULL,
                    expires INTEGER NOT NULL, owner TEXT NOT NULL, status TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS pending_code ON pairings(code_hash) WHERE status='pending';
                CREATE TABLE IF NOT EXISTS claims (id TEXT PRIMARY KEY, pairing_id TEXT NOT NULL UNIQUE,
                    public_key TEXT NOT NULL, name TEXT NOT NULL, request_hash TEXT NOT NULL,
                    token_hash TEXT NOT NULL, status TEXT NOT NULL, device_id TEXT NOT NULL,
                    expires INTEGER NOT NULL, comparison TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, public_key TEXT NOT NULL,
                    name TEXT NOT NULL, owner TEXT NOT NULL, created INTEGER NOT NULL,
                    last_used INTEGER, revoked INTEGER);
                CREATE TABLE IF NOT EXISTS challenges (id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    payload TEXT NOT NULL, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS tokens (hash TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    expires INTEGER NOT NULL);
                BEGIN IMMEDIATE;
            ''')
            self._poll_key = bytes.fromhex(self._meta(db, 'poll_key', lambda: secrets.token_hex(32)))
            pem = self._meta(db, 'signing_key', self._new_key)
            self._key = serialization.load_pem_private_key(pem.encode(), password=None)
            if not isinstance(self._key, ec.EllipticCurvePrivateKey) or not isinstance(self._key.curve, ec.SECP256R1):
                raise LinkError('unsafe_device_store')
        self.host_public_key = public_wire(self._key.public_key())
        from hermes_cli.dashboard_auth.device_links_crypto import unb64
        self.host_id = hashlib.sha256(unb64(self.host_public_key)).hexdigest()

    @staticmethod
    def _new_key():
        return ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()

    @staticmethod
    def _meta(db, key, create):
        row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        if row:
            return row[0]
        value = create()
        db.execute('INSERT INTO meta VALUES (?,?)', (key, value))
        return value

    @contextmanager
    def _transaction(self):
        with self._lock, sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db

    @property
    def host(self):
        return {'host_id': self.host_id, 'host_name': self.host_name,
                'host_public_key': self.host_public_key, 'gateway_url': self.gateway_url}

    def _signed(self, value):
        payload = json_payload(value)
        return {'payload': b64(payload), 'signature': sign(self._key, payload)}

    def _poll_token(self, claim_id, request_hash):
        return b64(hmac.new(self._poll_key, ('loki-device-poll-v1\n' + claim_id + '\n' + request_hash).encode(),
                            hashlib.sha256).digest())

    @staticmethod
    def _gc(db, now):
        db.execute("UPDATE pairings SET status='expired' WHERE expires<=? AND status='pending'", (now,))
        db.execute("UPDATE claims SET status='expired' WHERE expires<=? AND status='pending'", (now,))
        db.execute('DELETE FROM challenges WHERE expires<=?', (now,))
        db.execute('DELETE FROM tokens WHERE expires<=?', (now,))
        db.execute('DELETE FROM claims WHERE expires<?', (now - 86400,))
        db.execute("DELETE FROM pairings WHERE status!='pending' AND expires<?", (now - 86400,))
        db.execute('DELETE FROM devices WHERE revoked<?', (now - 86400,))

    @staticmethod
    def _capacity(db, table, maximum):
        if db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] >= maximum:
            raise LinkError('capacity_reached')

    def create_pairing(self, session: Session) -> dict:
        owner = json.dumps(_identity(session), sort_keys=True)
        now = int(time.time())
        with self._transaction() as db:
            self._gc(db, now)
            self._capacity(db, 'pairings', 64)
            for _ in range(8):
                code = ''.join(secrets.choice(_ALPHABET) for _ in range(8))
                if not db.execute("SELECT 1 FROM pairings WHERE code_hash=? AND status='pending'",
                                  (_hash(code),)).fetchone():
                    break
            else:
                raise LinkError('code_collision')
            pairing_id = _id('pair')
            db.execute('INSERT INTO pairings VALUES (?,?,?,?,?)',
                       (pairing_id, _hash(code), now + PAIR_TTL, owner, 'pending'))
        return {**self.host, 'pairing_id': pairing_id, 'code': code[:4] + '-' + code[4:],
                'expires_at': now + PAIR_TTL}

    def cancel(self, pairing_id):
        opaque(pairing_id)
        with self._transaction() as db:
            db.execute("UPDATE pairings SET status='cancelled' WHERE id=? AND status='pending'", (pairing_id,))
            db.execute("UPDATE claims SET status='denied' WHERE pairing_id=? AND status='pending'", (pairing_id,))

    def claim(self, body: dict) -> dict:
        payload = claim_payload(body)
        verify(body['device_public_key'], body['signature'], payload)
        request_hash, now = _hash(payload), int(time.time())
        with self._transaction() as db:
            self._gc(db, now)
            pairing = db.execute('SELECT * FROM pairings WHERE id=?', (body['pairing_id'],)).fetchone()
            if (not pairing or pairing['expires'] <= now or pairing['status'] not in ('pending', 'approved')
                    or not hmac.compare_digest(pairing['code_hash'], _hash(normalize_code(body['code'])))):
                raise LinkError('invalid_or_expired')
            previous = db.execute('SELECT * FROM claims WHERE pairing_id=?', (pairing['id'],)).fetchone()
            if previous:
                if previous['request_hash'] != request_hash or previous['status'] not in ('pending', 'approved'):
                    raise LinkError('invalid_or_expired')
                row = dict(previous)
            else:
                self._capacity(db, 'claims', 128)
                claim_id, device_id = _id('claim'), _id('device')
                comparison = str(secrets.randbelow(1000000)).zfill(6)
                comparison = comparison[:3] + '-' + comparison[3:]
                values = (claim_id, pairing['id'], body['device_public_key'], body['device_name'],
                          request_hash, _hash(self._poll_token(claim_id, request_hash)), 'pending',
                          device_id, pairing['expires'], comparison)
                db.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)', values)
                row = dict(db.execute('SELECT * FROM claims WHERE id=?', (claim_id,)).fetchone())
        metadata = {**self.host, 'protocol': 'loki-device-host-v1', 'pairing_id': body['pairing_id'],
                    'claim_id': row['id'], 'device_id': row['device_id'],
                    'key_fingerprint': fingerprint(row['public_key']),
                    'comparison': row['comparison'], 'expires_at': row['expires']}
        return {'claim_id': row['id'], 'claim_token': self._poll_token(row['id'], row['request_hash']),
                'host_id': self.host_id, 'device_id': row['device_id'], 'comparison': row['comparison'],
                'expires_at': row['expires'], 'host_metadata': self._signed(metadata)}

    def poll(self, claim_id, claim_token):
        opaque(claim_id)
        opaque(claim_token)
        with self._transaction() as db:
            self._gc(db, int(time.time()))
            row = db.execute('SELECT * FROM claims WHERE id=?', (claim_id,)).fetchone()
            if not row or not hmac.compare_digest(row['token_hash'], _hash(claim_token)):
                raise LinkError('invalid_or_expired')
            status = row['status']
            device = db.execute('SELECT revoked FROM devices WHERE id=?', (row['device_id'],)).fetchone()
            if status == 'approved' and (not device or device['revoked'] is not None):
                status = 'denied'
            return {'status': status, 'host_id': self.host_id,
                    'device_id': row['device_id'], 'expires_at': row['expires']}

    def settle(self, claim_id, *, approve, key_fingerprint='', comparison=''):
        opaque(claim_id)
        now = int(time.time())
        with self._transaction() as db:
            self._gc(db, now)
            row = db.execute('SELECT * FROM claims WHERE id=?', (claim_id,)).fetchone()
            pairing = db.execute('SELECT * FROM pairings WHERE id=?', (row['pairing_id'],)).fetchone() if row else None
            if not row or not pairing or row['status'] != 'pending' or pairing['status'] != 'pending':
                raise LinkError('invalid_or_expired')
            if approve:
                if (not hmac.compare_digest(fingerprint(row['public_key']), key_fingerprint)
                        or not hmac.compare_digest(row['comparison'], comparison)):
                    raise LinkError('claim_changed')
                self._capacity(db, 'devices', 64)
                db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?)',
                           (row['device_id'], row['public_key'], row['name'], pairing['owner'], now, None, None))
            status = 'approved' if approve else 'denied'
            db.execute('UPDATE claims SET status=? WHERE id=?', (status, claim_id))
            db.execute('UPDATE pairings SET status=? WHERE id=?', (status, pairing['id']))
        return {'status': status, 'device_id': row['device_id'], 'host_id': self.host_id}

    def _active(self, db, device_id):
        row = db.execute('SELECT * FROM devices WHERE id=? AND revoked IS NULL', (device_id,)).fetchone()
        if row is None:
            raise LinkError('invalid_or_expired')
        return row

    def is_active(self, device_id):
        with self._transaction() as db:
            return db.execute('SELECT 1 FROM devices WHERE id=? AND revoked IS NULL', (device_id,)).fetchone() is not None

    def challenge(self, device_id, host_id):
        opaque(device_id)
        if host_id != self.host_id:
            raise LinkError('invalid_or_expired')
        now, challenge_id = int(time.time()), _id('challenge')
        payload = {'protocol': 'loki-device-token-v1', 'host_id': self.host_id, 'device_id': device_id,
                   'client_id': CLIENT_ID, 'challenge_id': challenge_id, 'nonce': secrets.token_urlsafe(32),
                   'expires_at': now + CHALLENGE_TTL}
        with self._transaction() as db:
            self._gc(db, now)
            self._active(db, device_id)
            self._capacity(db, 'challenges', 256)
            db.execute('INSERT INTO challenges (id,device_id,payload,expires) VALUES (?,?,?,?)',
                       (challenge_id, device_id, json_payload(payload).decode(), now + CHALLENGE_TTL))
        return {'challenge_id': challenge_id, 'host_id': self.host_id, 'device_id': device_id,
                'expires_at': now + CHALLENGE_TTL, **self._signed(payload)}

    def token(self, device_id, challenge_id, signature):
        opaque(device_id)
        opaque(challenge_id)
        now = int(time.time())
        with self._transaction() as db:
            self._gc(db, now)
            device = self._active(db, device_id)
            row = db.execute('SELECT * FROM challenges WHERE id=? AND device_id=? AND used=0 AND expires>?',
                             (challenge_id, device_id, now)).fetchone()
            if row is None:
                raise LinkError('invalid_or_expired')
            verify(device['public_key'], signature, row['payload'].encode())
            db.execute('UPDATE challenges SET used=1 WHERE id=?', (challenge_id,))
            self._capacity(db, 'tokens', 512)
            token = 'loki-device-v1.' + secrets.token_urlsafe(32)
            db.execute('INSERT INTO tokens VALUES (?,?,?)', (_hash(token), device_id, now + TOKEN_TTL))
            db.execute('UPDATE devices SET last_used=? WHERE id=?', (now, device_id))
            owner = json.loads(device['owner'])
        return {**owner, 'access_token': token, 'token_type': 'Bearer', 'expires_at': now + TOKEN_TTL,
                'device_id': device_id, 'host_id': self.host_id}

    def verify_token(self, token):
        if not token.startswith('loki-device-v1.') or len(token) > 128:
            return None
        now = int(time.time())
        with self._transaction() as db:
            row = db.execute('SELECT d.*,t.expires FROM devices d JOIN tokens t ON d.id=t.device_id '
                             'WHERE t.hash=? AND t.expires>? AND d.revoked IS NULL', (_hash(token), now)).fetchone()
            if row is None:
                return None
            return Session(**json.loads(row['owner']), expires_at=row['expires'],
                           access_token=token, refresh_token='', device_id=row['id'],
                           device_host_id=self.host_id, device_home=self.home)

    def revoke(self, device_id):
        opaque(device_id)
        with self._transaction() as db:
            db.execute('UPDATE devices SET revoked=COALESCE(revoked,?) WHERE id=?', (int(time.time()), device_id))
            db.execute('DELETE FROM tokens WHERE device_id=?', (device_id,))
            db.execute('DELETE FROM challenges WHERE device_id=?', (device_id,))

    def list(self):
        with self._transaction() as db:
            self._gc(db, int(time.time()))
            pairings = [dict(r) for r in db.execute("SELECT id AS pairing_id,expires AS expires_at FROM pairings WHERE status='pending'")]
            claims = [{**dict(r), 'key_fingerprint': fingerprint(r['device_public_key'])} for r in db.execute(
                "SELECT id AS claim_id,pairing_id,name AS device_name,public_key AS device_public_key,comparison,expires AS expires_at "
                "FROM claims WHERE status='pending'")]
            devices = [{**dict(r), 'key_fingerprint': fingerprint(r['public_key'])} for r in db.execute('SELECT id AS device_id,name AS device_name,public_key,'
                'created AS created_at,last_used AS last_used_at,revoked AS revoked_at FROM devices ORDER BY created DESC')]
            for row in devices:
                row.pop('public_key')
        return {'host': self.host, 'pairings': pairings, 'claims': claims, 'devices': devices}
