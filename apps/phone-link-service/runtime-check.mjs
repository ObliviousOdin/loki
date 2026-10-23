/** Synthetic local workerd smoke. Refuses any public or non-loopback endpoint. */
import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync, randomBytes } from 'node:crypto';

const origin = new URL(process.argv[2] ?? 'http://127.0.0.1:52781');
if (origin.protocol !== 'http:' || origin.hostname !== '127.0.0.1' || !origin.port || origin.pathname !== '/' || origin.search || origin.hash || origin.username || origin.password) {
  throw new Error('This synthetic check is restricted to an explicit local workerd port.');
}
const secret = 'synthetic-test-only-registration-secret-0001';
const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + secret };
const id = 'pair_runtime_' + randomBytes(16).toString('hex');
const { publicKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
const jwk = publicKey.export({ format: 'jwk' });
const key = Buffer.concat([Buffer.from([4]), Buffer.from(jwk.x, 'base64url'), Buffer.from(jwk.y, 'base64url')]);
const code = [...randomBytes(8)].map(value => '0123456789ABCDEFGHJKMNPQRSTVWXYZ'[value & 31]).join('');
const registration = { code, pairing_id: id, gateway_url: 'https://mac.example.test', host_name: 'Synthetic runtime Mac',
  host_id: createHash('sha256').update(key).digest('hex'), host_public_key: key.toString('base64url'), expires_at: Math.floor(Date.now() / 1000) + 30 };
const post = (path, value, authenticated = true) => fetch(new URL(path, origin), {
  method: 'POST', headers: authenticated ? headers : { 'Content-Type': 'application/json' }, body: JSON.stringify(value), redirect: 'error',
});
const cancel = () => fetch(new URL('/v1/pairings/' + id, origin), { method: 'DELETE', headers, redirect: 'error' });
try {
  assert.equal((await fetch(new URL('/health', origin))).status, 200);
  const created = await post('/v1/pairings', registration);
  assert.equal(created.status, 201, await created.text());
  const resolved = await post('/v1/pairings/resolve', { code }, false);
  assert.equal(resolved.status, 200);
  assert.equal((await resolved.json()).host_id, registration.host_id);
  assert.equal((await post('/v1/pairings', registration)).status, 200);
  assert.equal((await post('/v1/pairings', { ...registration, pairing_id: id + 'other' })).status, 409);
  assert.equal((await cancel()).status, 200);
  assert.equal((await post('/v1/pairings/resolve', { code }, false)).status, 404);
  console.log(JSON.stringify({ runtime: 'workerd SQLite Durable Object', checks: 6, passed: true }));
} finally { await cancel(); }
