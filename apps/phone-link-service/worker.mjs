/** Code discovery only. Authentication, approval and device grants stay on the Mac. */
const ALPHABET = /^[0-9A-HJKMNP-TV-Z]{8}$/;
const IDENTIFIER = /^[A-Za-z0-9_-]{16,128}$/;
const MAX_PAIRINGS = 128;
const MAX_RATE_KEYS = 1024;
const MAX_BODY_BYTES = 4096;
const encoder = new TextEncoder();

function json(value, status = 200) {
  return Response.json(value, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}

function normalizeCode(value) {
  if (typeof value !== 'string' || value.length > 32) return null;
  const code = value.replace(/[ -]/g, '').toUpperCase();
  return ALPHABET.test(code) ? code : null;
}

async function sha256(value) {
  const bytes = typeof value === 'string' ? encoder.encode(value) : value;
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('');
}

async function authorized(request, secret) {
  if (typeof secret !== 'string' || secret.length < 32) return false;
  const header = request.headers.get('Authorization') ?? '';
  if (!header.startsWith('Bearer ') || header.length > 520) return false;
  const [actual, expected] = await Promise.all([sha256(header.slice(7)), sha256(secret)]);
  let difference = 0;
  for (let index = 0; index < expected.length; index++) difference |= actual.charCodeAt(index) ^ expected.charCodeAt(index);
  return difference === 0;
}

async function readBody(request) {
  if ((request.headers.get('Content-Type') ?? '').split(';')[0].trim() !== 'application/json') return null;
  if (Number(request.headers.get('Content-Length') ?? 0) > MAX_BODY_BYTES) return null;
  if (!request.body) return null;
  const reader = request.body.getReader();
  const chunks = [];
  let length = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > MAX_BODY_BYTES) { await reader.cancel(); return null; }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try {
    const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch { return null; }
}

function publicKeyBytes(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{87}$/.test(value)) return null;
  const decoded = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '=');
  const bytes = Uint8Array.from(decoded, character => character.charCodeAt(0));
  const canonical = btoa(decoded).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return bytes.length === 65 && bytes[0] === 4 && canonical === value ? bytes : null;
}

async function registration(body, origins, now) {
  const fields = new Set(['code', 'pairing_id', 'gateway_url', 'host_id', 'host_name', 'host_public_key', 'expires_at']);
  if (Object.keys(body).some(key => !fields.has(key))) return null;
  const code = normalizeCode(body.code);
  if (!code || !IDENTIFIER.test(body.pairing_id ?? '') || !/^[a-f0-9]{64}$/.test(body.host_id ?? '')) return null;
  if (typeof body.host_name !== 'string' || !body.host_name.trim() || encoder.encode(body.host_name).length > 120 || /[\x00-\x1f\x7f]/.test(body.host_name)) return null;
  if (!Number.isSafeInteger(body.expires_at) || body.expires_at <= now || body.expires_at > now + 300) return null;
  const key = publicKeyBytes(body.host_public_key);
  if (!key || await sha256(key) !== body.host_id) return null;
  try { await crypto.subtle.importKey('raw', key, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']); }
  catch { return null; }
  let url;
  try { url = new URL(body.gateway_url); } catch { return null; }
  const allowed = (origins ?? '').split(',').map(value => value.trim()).filter(Boolean);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/' || !allowed.includes(url.origin)) return null;
  return { hash: await sha256(code), record: {
    version: 1, pairing_id: body.pairing_id, gateway_url: url.origin,
    host_id: body.host_id, host_name: body.host_name.trim(),
    host_public_key: body.host_public_key, expires_at: body.expires_at,
  } };
}

export class PairingRegistry {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; }

  async fetch(request) {
    const path = new URL(request.url).pathname;
    const registrationRoute = request.method === 'POST' && path === '/v1/pairings';
    const cancellation = request.method === 'DELETE' ? path.match(/^\/v1\/pairings\/([A-Za-z0-9_-]{16,128})$/) : null;
    const resolveRoute = request.method === 'POST' && path === '/v1/pairings/resolve';
    if (!registrationRoute && !cancellation && !resolveRoute) return json({ error: 'not_found' }, 404);
    if (typeof this.env.REGISTRATION_TOKEN !== 'string' || this.env.REGISTRATION_TOKEN.length < 32 || !this.env.GATEWAY_ORIGINS) return json({ error: 'service_unavailable' }, 503);
    const ip = request.headers.get('CF-Connecting-IP');
    if (!ip || ip.length > 128) return json({ error: 'service_unavailable' }, 503);
    const ipHash = await sha256(ip);
    const now = Math.floor(Date.now() / 1000);
    const limited = await this.ctx.storage.transaction(tx => this.rateLimit(tx, ipHash, now));
    if (limited) return json({ error: 'try_later' }, 429);
    if (!resolveRoute && !await authorized(request, this.env.REGISTRATION_TOKEN)) return json({ error: 'unauthorized' }, 401);
    if (cancellation) return this.cancel(cancellation[1]);
    let body;
    try { body = await readBody(request); } catch { body = null; }
    if (!body) return json({ error: 'invalid_request' }, 400);
    return registrationRoute ? this.register(body, now) : this.resolve(body, now);
  }

  async rateLimit(tx, ipHash, now) {
    const key = 'rate:' + ipHash;
    const old = await tx.get(key);
    const count = await tx.get('rate_count') ?? 0;
    if (!old && count >= MAX_RATE_KEYS) return true;
    const row = old && old.expires_at > now ? old : { count: 0, expires_at: now + 60 };
    if (row.count >= 20) return true;
    await tx.put(key, { count: row.count + 1, expires_at: row.expires_at });
    if (!old) await tx.put('rate_count', count + 1);
    if (await tx.getAlarm() === null) await tx.setAlarm((now + 60) * 1000);
    return false;
  }

  async register(body, now) {
    const parsed = await registration(body, this.env.GATEWAY_ORIGINS, now);
    if (!parsed) return json({ error: 'invalid_registration' }, 400);
    const result = await this.ctx.storage.transaction(async tx => {
      const key = 'pair:' + parsed.hash;
      const existing = await tx.get(key);
      if (existing && existing.expires_at > now) {
        return JSON.stringify(existing) === JSON.stringify(parsed.record) ? 200 : 409;
      }
      const previousHash = await tx.get('id:' + parsed.record.pairing_id);
      if (previousHash && previousHash !== parsed.hash) return 409;
      const count = await tx.get('pair_count') ?? 0;
      if (!existing && count >= MAX_PAIRINGS) return 503;
      if (existing) await tx.delete('id:' + existing.pairing_id);
      await tx.put(key, parsed.record);
      await tx.put('id:' + parsed.record.pairing_id, parsed.hash);
      if (!existing) await tx.put('pair_count', count + 1);
      return 201;
    });
    if (result === 409) return json({ error: 'code_unavailable' }, result);
    if (result === 503) return json({ error: 'service_unavailable' }, result);
    return json({ registered: true, pairing_id: parsed.record.pairing_id, expires_at: parsed.record.expires_at }, result);
  }

  async resolve(body, now) {
    const code = normalizeCode(body.code);
    if (!code || Object.keys(body).some(key => key !== 'code')) return json({ error: 'pairing_unavailable' }, 404);
    const row = await this.ctx.storage.get('pair:' + await sha256(code));
    if (!row || row.expires_at <= now) return json({ error: 'pairing_unavailable' }, 404);
    return json(row);
  }

  async cancel(pairingID) {
    await this.ctx.storage.transaction(async tx => {
      const hash = await tx.get('id:' + pairingID);
      if (!hash) return;
      const row = await tx.get('pair:' + hash);
      if (row?.pairing_id !== pairingID) return;
      await tx.delete(['id:' + pairingID, 'pair:' + hash]);
      await tx.put('pair_count', Math.max(0, (await tx.get('pair_count') ?? 1) - 1));
    });
    return json({ cancelled: true });
  }

  async alarm() {
    const now = Math.floor(Date.now() / 1000);
    await this.ctx.storage.transaction(async tx => {
      for (const [key, row] of await tx.list({ prefix: 'pair:' })) {
        if (row.expires_at <= now) {
          await tx.delete([key, 'id:' + row.pairing_id]);
          await tx.put('pair_count', Math.max(0, (await tx.get('pair_count') ?? 1) - 1));
        }
      }
      for (const [key, row] of await tx.list({ prefix: 'rate:' })) {
        if (row.expires_at <= now) {
          await tx.delete(key);
          await tx.put('rate_count', Math.max(0, (await tx.get('rate_count') ?? 1) - 1));
        }
      }
      if ((await tx.get('pair_count') ?? 0) || (await tx.get('rate_count') ?? 0)) await tx.setAlarm((now + 60) * 1000);
    });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health' && request.method === 'GET') {
      const ready = typeof env.REGISTRATION_TOKEN === 'string' && env.REGISTRATION_TOKEN.length >= 32 && Boolean(env.GATEWAY_ORIGINS) && Boolean(env.PAIRINGS);
      return json({ service: 'loki-phone-link', version: 1, ready }, ready ? 200 : 503);
    }
    if (!env.PAIRINGS) return json({ error: 'service_unavailable' }, 503);
    // Public callers cannot choose an internal object, key or origin.
    return env.PAIRINGS.get(env.PAIRINGS.idFromName('registry-v1')).fetch(request);
  },
};
