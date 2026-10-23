"""The phone-link v1 signing contract; all wire encodings are strict and bounded."""
from __future__ import annotations

import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

CLIENT_ID = 'loki-ios'
_URLSAFE = re.compile(r'^[A-Za-z0-9_-]+$')
_CODE = re.compile(r'^[0-9A-HJKMNP-TV-Z]{8}$')


class LinkError(ValueError):
    """A bounded, non-secret public protocol failure."""


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def unb64(value: str, *, size: int | None = None) -> bytes:
    if not isinstance(value, str) or len(value) > 16384 or not _URLSAFE.fullmatch(value):
        raise LinkError('invalid_encoding')
    raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    if b64(raw) != value or (size is not None and len(raw) != size):
        raise LinkError('invalid_encoding')
    return raw


def opaque(value: str) -> str:
    if not isinstance(value, str) or not 16 <= len(value) <= 128 or not _URLSAFE.fullmatch(value):
        raise LinkError('invalid_identifier')
    return value


def normalize_code(value: str) -> str:
    if (not isinstance(value, str) or len(value) > 32
            or not re.fullmatch(r'[0-9A-Za-z -]+', value)):
        raise LinkError('invalid_code')
    normalized = value.replace(' ', '').replace('-', '').upper()
    if not _CODE.fullmatch(normalized):
        raise LinkError('invalid_code')
    return normalized


def public_key(value: str) -> ec.EllipticCurvePublicKey:
    try:
        raw = unb64(value, size=65)
        if raw[0] != 4:
            raise LinkError('invalid_key')
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    except ValueError:
        raise LinkError('invalid_key') from None


def public_wire(key) -> str:
    return b64(key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def fingerprint(value: str) -> str:
    public_key(value)
    return b64(hashlib.sha256(unb64(value)).digest())


def sign(key: ec.EllipticCurvePrivateKey, payload: bytes) -> str:
    r, s = decode_dss_signature(key.sign(payload, ec.ECDSA(hashes.SHA256())))
    return b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))


def verify(key_wire: str, signature: str, payload: bytes) -> None:
    raw = unb64(signature, size=64)
    try:
        public_key(key_wire).verify(
            encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')),
            payload, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError):
        raise LinkError('invalid_proof') from None


def claim_payload(body: dict) -> bytes:
    """Fixed LF-delimited UTF-8. Only the name is UTF-8 and it is base64url encoded first."""
    pairing = opaque(body['pairing_id'])
    code = normalize_code(body['code'])
    name = body['device_name']
    if (body['client_id'] != CLIENT_ID or not isinstance(name, str) or not name.strip()
            or len(name.encode('utf-8')) > 120 or any(ord(c) < 32 for c in name)):
        raise LinkError('invalid_claim')
    key = body['device_public_key']
    public_key(key)
    nonce = body['nonce']
    unb64(nonce, size=32)
    return ('\n'.join(('loki-device-claim-v1', pairing, code, CLIENT_ID,
                       b64(name.encode('utf-8')), key, nonce)) + '\n').encode('ascii')


def json_payload(value: dict) -> bytes:
    """Servers supply signed JSON bytes on the wire; clients verify those exact bytes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
