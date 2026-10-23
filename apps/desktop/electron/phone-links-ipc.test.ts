import type { IpcMain, IpcMainInvokeEvent } from 'electron'
import { expect, it, vi } from 'vitest'

import fixture from '../../../docs/loki/phone-link-wire.json'

import type { PhoneLinkClaim, PhoneLinkOwner, PhoneLinksBridge } from './phone-link-types'
import { registerPhoneLinksIpc } from './phone-links-ipc'

const owner: PhoneLinkOwner = {
  origin: 'http://127.0.0.1:9119',
  instanceId: 'phone-ipc-instance',
  profileId: '/fixture/loki',
  authorityEpoch: 7
}

const metadata = fixture.host_metadata_decoded

const reviewed: PhoneLinkClaim = {
  id: metadata.claim_id,
  pairingId: metadata.pairing_id,
  deviceName: fixture.claim_request.device_name,
  devicePublicKey: fixture.claim_request.device_public_key,
  keyFingerprint: metadata.key_fingerprint,
  comparison: metadata.comparison,
  expiresAt: metadata.expires_at
}

function registry(isTrusted = true) {
  const unavailable = { ok: false, reason: 'unavailable' } as const

  const api = {
    status: vi.fn<PhoneLinksBridge['status']>().mockResolvedValue(unavailable),
    signInOwner: vi.fn<PhoneLinksBridge['signInOwner']>().mockResolvedValue(unavailable),
    createPairing: vi.fn<PhoneLinksBridge['createPairing']>().mockResolvedValue(unavailable),
    cancelPairing: vi.fn<PhoneLinksBridge['cancelPairing']>().mockResolvedValue(unavailable),
    approveClaim: vi.fn<PhoneLinksBridge['approveClaim']>().mockResolvedValue(unavailable),
    denyClaim: vi.fn<PhoneLinksBridge['denyClaim']>().mockResolvedValue(unavailable),
    revokeDevice: vi.fn<PhoneLinksBridge['revokeDevice']>().mockResolvedValue(unavailable)
  } satisfies PhoneLinksBridge

  const handlers = new Map<string, Parameters<IpcMain['handle']>[1]>()

  const ipc: Pick<IpcMain, 'handle'> = {
    handle: (channel, listener) => {
      handlers.set(channel, listener)
    }
  }

  const frame = { senderFrame: { url: 'file:///synthetic-loki-shell' } } as unknown as IpcMainInvokeEvent
  const trusted = vi.fn((event: IpcMainInvokeEvent) => event === frame && isTrusted)
  registerPhoneLinksIpc(ipc, api, trusted)

  const invoke = async (channel: string, ...args: unknown[]) => {
    const handler = handlers.get(channel)

    if (!handler) {
      throw new Error(`Missing test handler ${channel}`)
    }

    return handler(frame, ...args)
  }

  return { api, trusted, frame, invoke }
}

it('refuses untrusted frames on every phone channel before calling the manager', async () => {
  const test = registry(false)
  expect(await test.invoke('hermes:phone-links:status')).toEqual({ ok: false, reason: 'refused' })
  expect(await test.invoke('hermes:phone-links:sign-in', owner, 'stub')).toEqual({ ok: false, reason: 'refused' })
  expect(await test.invoke('hermes:phone-links:mutate', { action: 'approve', owner, claim: reviewed })).toEqual({
    ok: false,
    reason: 'refused'
  })

  for (const method of Object.values(test.api)) {
    expect(method).not.toHaveBeenCalled()
  }

  expect(test.trusted.mock.calls.every(([frame]) => frame === test.frame)).toBe(true)
})

it.each([
  null,
  undefined,
  {},
  [],
  'create',
  { action: 'forward-http', owner, url: 'https://foreign.example.test' },
  { action: 'cancel', owner, pairingId: 42 },
  { action: 'revoke', owner, deviceId: 42 },
  { action: 'approve', owner, claim: null },
  { action: 'deny', owner, claim: 'not-a-claim' }
])('rejects malformed or unknown mutation input %# without manager dispatch', async input => {
  const test = registry()
  expect(await test.invoke('hermes:phone-links:mutate', input)).toEqual({ ok: false, reason: 'invalid_request' })

  for (const method of Object.values(test.api)) {
    expect(method).not.toHaveBeenCalled()
  }
})

it.each([null, 42, 'x'.repeat(129)])('rejects malformed sign-in provider %# without opening login', async provider => {
  const test = registry()
  expect(await test.invoke('hermes:phone-links:sign-in', owner, provider)).toEqual({
    ok: false,
    reason: 'invalid_request'
  })
  expect(test.api.signInOwner).not.toHaveBeenCalled()
})

it('dispatches only the reviewed claim and owner to approval', async () => {
  const test = registry()
  const reply = { ok: true, owner, value: null } as const
  test.api.approveClaim.mockResolvedValue(reply)
  expect(
    await test.invoke('hermes:phone-links:mutate', {
      action: 'approve',
      owner,
      claim: reviewed,
      url: 'https://renderer-selected-origin.invalid',
      bearer: 'synthetic-renderer-bearer'
    })
  ).toEqual(reply)
  expect(test.api.approveClaim).toHaveBeenCalledExactlyOnceWith(owner, reviewed)
  expect(test.api.createPairing).not.toHaveBeenCalled()
  expect(test.api.denyClaim).not.toHaveBeenCalled()
  expect(test.api.revokeDevice).not.toHaveBeenCalled()
})
