import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync } from 'node:crypto';
import { test } from 'node:test';
import worker, { PairingRegistry } from './worker.mjs';

// A serial, rollback-capable implementation of the small Storage API seam.
// Real-runtime coverage is separate: these contracts exercise request behavior.
class MemoryStorage {
  data = new Map();
  alarm = null;
  queue = Promise.resolve();
  async get(key) { return structuredClone(this.data.get(key)); }
  async put(key, value) { this.data.set(key, structuredClone(value)); }
  async delete(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) this.data.delete(key); }
  async list({ prefix }) { return new Map([...this.data].filter(([key]) => key.startsWith(prefix)).map(([key, value]) => [key, structuredClone(value)])); }
  async getAlarm() { return this.alarm; }
  async setAlarm(value) { this.alarm = value; }
  transaction(callback) {
    const result = this.queue.then(async () => {
      const before = structuredClone(this.data), alarm = this.alarm;
      try { return await callback(this); }
      catch (error) { this.data = before; this.alarm = alarm; throw error; }
    });
    this.queue = result.catch(() => {});
    return result;
  }
}

const secret = 'synthetic-test-only-registration-secret-0001';
const now = () => Math.floor(Date.now() / 1000);
const { publicKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
const jwk = publicKey.export({ format: 'jwk' });
const key = Buffer.concat([Buffer.from([4]), Buffer.from(jwk.x, 'base64url'), Buffer.from(jwk.y, 'base64url')]);
const host = { host_public_key: key.toString('base64url'), host_id: createHash('sha256').update(key).digest('hex') };
function invitation(overrides = {}) {
  return { code: '0123-ABCD', pairing_id: 'pair_synthetic00000001', gateway_url: 'https://mac.example.test', host_name: 'Test Mac', ...host, expires_at: now() + 240, ...overrides };
}
function setup() {
  const storage = new MemoryStorage();
  const env = { REGISTRATION_TOKEN: secret, GATEWAY_ORIGINS: 'https://mac.example.test' };
  const registry = new PairingRegistry({ storage }, env);
  env.PAIRINGS = { idFromName: name => name, get: name => { assert.equal(name, 'registry-v1'); return registry; } };
  let serial = 0;
  const request = (path, { method = 'POST', body, authenticated = false, ip = '192.0.2.' + (++serial), headers = {} } = {}) => {
    return worker.fetch(new Request('https://link.example.test' + path, {
      method, headers: { 'CF-Connecting-IP': ip, ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(authenticated ? { Authorization: 'Bearer ' + secret } : {}), ...headers },
      ...(body !== undefined ? { body: typeof body === 'string' ? body : JSON.stringify(body) } : {}),
    }), env);
  };
  return { storage, env, registry, request };
}

test('fails closed until configured and refuses registration without its operator secret', async () => {
  const { env, request } = setup();
  assert.equal((await request('/health', { method: 'GET' })).status, 200);
  assert.equal((await request('/v1/pairings', { body: invitation() })).status, 401);
  assert.equal((await request('/v1/pairings', { body: invitation(), headers: { Authorization: 'Bearer wrong' } })).status, 401);
  env.REGISTRATION_TOKEN = '';
  assert.equal((await request('/v1/pairings/resolve', { body: { code: '0123ABCD' } })).status, 503);
  assert.equal((await request('/health', { method: 'GET' })).status, 503);
});

test('registers public metadata only, resolves formatting variants and never stores plaintext code', async () => {
  const { storage, request } = setup();
  const value = invitation();
  assert.equal((await request('/v1/pairings', { authenticated: true, body: value })).status, 201);
  const result = await request('/v1/pairings/resolve', { body: { code: ' 0123 abcd ' } });
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('Cache-Control'), 'no-store');
  const resolved = await result.json();
  assert.deepEqual(resolved, { version: 1, ...Object.fromEntries(Object.entries(value).filter(([key]) => key !== 'code')) });
  for (const forbidden of ['0123-ABCD', '0123ABCD', secret, '192.0.2.']) assert.ok(!JSON.stringify([...storage.data]).includes(forbidden));
});

test('pins a valid public key, host digest and exact configured HTTPS gateway origin', async () => {
  const { request } = setup();
  const invalid = [
    { gateway_url: 'http://mac.example.test' }, { gateway_url: 'https://other.example.test' },
    { gateway_url: 'https://mac.example.test/path' }, { gateway_url: 'https://user@mac.example.test' },
    { gateway_url: 'https://mac.example.test/?secret=x' }, { gateway_url: 'https://mac.example.test/#x' },
    { host_id: '0'.repeat(64) }, { host_public_key: Buffer.alloc(65, 4).toString('base64url') },
    { host_name: 'Test\nMac' }, { host_name: ' ' }, { pairing_id: '../invalid' },
    { host_name: 'é'.repeat(61) },
    { expires_at: now() - 1 }, { expires_at: now() + 301 },
    { code: 'IIII-OOOO' }, { code: '0123\tABCD' },
    { access_token: 'must-not-be-submitted' },
  ];
  for (const override of invalid) assert.equal((await request('/v1/pairings', { authenticated: true, body: invitation(override) })).status, 400, JSON.stringify(override));
});

test('serializes collisions, retries exact registration and never replaces another live code', async () => {
  const { request } = setup();
  const value = invitation();
  const responses = await Promise.all([
    request('/v1/pairings', { authenticated: true, body: value }),
    request('/v1/pairings', { authenticated: true, body: { ...value, pairing_id: 'pair_synthetic00000002' } }),
  ]);
  assert.deepEqual(responses.map(result => result.status).sort(), [201, 409]);
  const winner = await (await request('/v1/pairings/resolve', { body: { code: value.code } })).json();
  assert.equal((await request('/v1/pairings', { authenticated: true, body: { ...value, pairing_id: winner.pairing_id } })).status, 200);
  assert.equal((await request('/v1/pairings', { authenticated: true, body: { ...value, pairing_id: winner.pairing_id, code: 'ABCD-1234' } })).status, 409);
});

test('cancels only the operator-selected invitation and expiry has a uniform missing response', async () => {
  const { storage, registry, request } = setup();
  const first = invitation(), second = invitation({ pairing_id: 'pair_synthetic00000002', code: 'ABCD1234' });
  await request('/v1/pairings', { authenticated: true, body: first });
  await request('/v1/pairings', { authenticated: true, body: second });
  assert.equal((await request('/v1/pairings/' + first.pairing_id, { method: 'DELETE' })).status, 401);
  assert.equal((await request('/v1/pairings/' + first.pairing_id, { method: 'DELETE', authenticated: true })).status, 200);
  const missing = await (await request('/v1/pairings/resolve', { body: { code: first.code } })).json();
  const hash = createHash('sha256').update(second.code).digest('hex');
  storage.data.get('pair:' + hash).expires_at = now() - 1;
  assert.deepEqual(await (await request('/v1/pairings/resolve', { body: { code: second.code } })).json(), missing);
  assert.deepEqual(await (await request('/v1/pairings/resolve', { body: { code: 'invalid' } })).json(), missing);
  storage.alarm = null; // Runtime clears the executing alarm before calling its handler.
  await registry.alarm();
  assert.equal(storage.data.has('pair:' + hash), false);
  assert.equal(await storage.get('pair_count'), 0);
});

test('bounds request bodies, rejects metadata smuggling and has no arbitrary proxy route', async () => {
  const { request } = setup();
  for (const body of ['{', '[]', 'null', '"text"', ' '.repeat(4097)]) {
    assert.equal((await request('/v1/pairings', { authenticated: true, body })).status, 400);
  }
  assert.equal((await request('/v1/pairings/resolve', { body: { code: '0123ABCD', gateway_url: 'https://other.example.test' } })).status, 404);
  assert.equal((await request('/v1/pairings/resolve', { body: {}, headers: { 'Content-Type': 'text/plain' } })).status, 400);
  for (const path of ['/api/auth/me', '/v1/pairings/anything/proxy', '/auth/native/token']) assert.equal((await request(path, { body: {} })).status, 404);
});

test('rate-limits resolution independently of guessed codes and bounds retained rate keys', async () => {
  const { storage, registry, request } = setup();
  for (let index = 0; index < 20; index++) assert.equal((await request('/v1/pairings/resolve', { ip: '192.0.2.1', body: { code: '0123ABCD' } })).status, 404);
  assert.equal((await request('/v1/pairings/resolve', { ip: '192.0.2.1', body: { code: 'ABCD1234' } })).status, 429);
  for (let index = 1; index < 1024; index++) await request('/v1/pairings/resolve', { ip: 'test-client-' + index, body: { code: '0123ABCD' } });
  assert.equal((await request('/v1/pairings/resolve', { ip: 'new-client', body: { code: '0123ABCD' } })).status, 429);
  assert.equal((await storage.list({ prefix: 'rate:' })).size, 1024);
  for (const [, row] of storage.data) if (row && typeof row === 'object' && 'count' in row) row.expires_at = now() - 1;
  storage.alarm = null;
  await registry.alarm();
  assert.equal(await storage.get('rate_count'), 0);
  assert.equal((await request('/v1/pairings/resolve', { ip: 'new-client', body: { code: '0123ABCD' } })).status, 404);
});

test('refuses new registrations at the bounded capacity and cancellation releases one slot', async () => {
  const { storage, request } = setup();
  const values = Array.from({ length: 129 }, (_, index) => invitation({
    code: index.toString(16).padStart(8, '0').toUpperCase(), pairing_id: 'pair_capacity_' + index.toString().padStart(16, '0'),
  }));
  for (const body of values.slice(0, 128)) assert.equal((await request('/v1/pairings', { authenticated: true, body })).status, 201);
  assert.equal((await request('/v1/pairings', { authenticated: true, body: values[128] })).status, 503);
  assert.equal((await storage.list({ prefix: 'pair:' })).size, 128);
  assert.equal((await request('/v1/pairings/' + values[0].pairing_id, { method: 'DELETE', authenticated: true })).status, 200);
  assert.equal((await request('/v1/pairings', { authenticated: true, body: values[128] })).status, 201);
});
