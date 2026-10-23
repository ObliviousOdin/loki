import { afterEach, expect, it, vi } from 'vitest'

import { deferred } from '@/test/deferred'

import type {
  PhoneLinkClaim,
  PhoneLinkInvitation,
  PhoneLinkOwner,
  PhoneLinkResult,
  PhoneLinksBridge,
  PhoneLinkStatus
} from '../../electron/phone-link-types'

import { createPhoneLinkSettings } from './phone-links'

const firstOwner: PhoneLinkOwner = {
  origin: 'https://phone-link-a.invalid',
  instanceId: 'fixture-instance-a',
  profileId: '/fixture/loki-a',
  authorityEpoch: 7
}

const nextOwner: PhoneLinkOwner = { ...firstOwner, instanceId: 'fixture-instance-b', authorityEpoch: 8 }

function success<T>(value: T, owner: PhoneLinkOwner = firstOwner): PhoneLinkResult<T> {
  return { ok: true, owner, value }
}

function makeStatus(): PhoneLinkStatus {
  return {
    hostId: 'host_A_1234567890123456',
    hostName: 'Fixture Mac',
    hostPublicKey: 'd'.repeat(87),
    gatewayUrl: 'https://phone-link-a.invalid',
    configured: true,
    ready: true,
    transportVerifiedAt: Math.floor(Date.now() / 1000),
    ownerSignInRequired: false,
    ownerAuthorizeBaseUrl: 'https://dashboard.example.invalid',
    ownerLoginProviders: [],
    unavailableReason: null,
    claims: [],
    devices: []
  }
}

function makeInvitation(pairingId = 'pairing_A_1234567890123456', code = 'ABCD-EFGH'): PhoneLinkInvitation {
  return {
    pairingId,
    code,
    expiresAt: Math.floor(Date.now() / 1000) + 600,
    hostId: 'host_A_1234567890123456',
    hostName: 'Fixture Mac'
  }
}

function makeBridge() {
  return {
    status: vi.fn<PhoneLinksBridge['status']>().mockResolvedValue(success(makeStatus())),
    signInOwner: vi.fn<PhoneLinksBridge['signInOwner']>().mockResolvedValue(success(null)),
    createPairing: vi.fn<PhoneLinksBridge['createPairing']>().mockResolvedValue(success(makeInvitation())),
    cancelPairing: vi.fn<PhoneLinksBridge['cancelPairing']>().mockResolvedValue(success(null)),
    approveClaim: vi.fn<PhoneLinksBridge['approveClaim']>().mockResolvedValue(success(null)),
    denyClaim: vi.fn<PhoneLinksBridge['denyClaim']>().mockResolvedValue(success(null)),
    revokeDevice: vi.fn<PhoneLinksBridge['revokeDevice']>().mockResolvedValue(success(null))
  } satisfies PhoneLinksBridge
}

const cleanups: (() => void)[] = []

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) {
    cleanup()
  }
})

it.each(['invitation', 'failure'] as const)(
  'retires an old-owner %s when the same bridge refreshes to a new owner',
  async outcome => {
    const api = makeBridge()
    const oldCreate = deferred<PhoneLinkResult<PhoneLinkInvitation>>()
    const ownerRefresh = deferred<PhoneLinkResult<PhoneLinkStatus>>()
    const firstStatus = success(makeStatus())
    const nextStatus = success(makeStatus(), nextOwner)
    const oldInvitation = makeInvitation()
    const newInvitation = makeInvitation('pairing_B_1234567890123456', 'JKLM-NPQR')
    api.status
      .mockResolvedValue(nextStatus)
      .mockResolvedValueOnce(firstStatus)
      .mockReturnValueOnce(ownerRefresh.promise)
    api.createPairing.mockReturnValueOnce(oldCreate.promise).mockResolvedValueOnce(success(newInvitation, nextOwner))
    const controller = createPhoneLinkSettings(api)
    const publishedCodes: (string | undefined)[] = []
    const publishedIssues: (string | null)[] = []
    cleanups.push(
      controller.$state.subscribe(state => {
        publishedCodes.push(state.invitation?.code)
        publishedIssues.push(state.issue)
      }),
      controller.start()
    )
    await vi.waitFor(() => expect(controller.$state.get().status).toEqual(firstStatus))

    const creating = controller.act(controller.create)
    expect(api.createPairing).toHaveBeenCalledExactlyOnceWith(firstOwner)
    oldCreate.resolve(outcome === 'invitation' ? success(oldInvitation) : { ok: false, reason: 'refused' })
    await vi.waitFor(() => expect(api.status).toHaveBeenCalledTimes(2))
    expect(controller.$state.get().busy).toBe(true)
    ownerRefresh.resolve(nextStatus)
    await creating

    expect(controller.$state.get()).toMatchObject({ status: nextStatus, invitation: null, issue: null, busy: false })
    expect(publishedCodes).not.toContain(oldInvitation.code)
    expect(publishedIssues.every(issue => issue === null)).toBe(true)
    expect(api.createPairing).toHaveBeenCalledTimes(1)

    await controller.act(controller.create)
    expect(api.createPairing.mock.calls).toEqual([[firstOwner], [nextOwner]])
    expect(controller.$state.get()).toMatchObject({ invitation: newInvitation, issue: null, busy: false })
  }
)

it('publishes no late response and invokes no bridge actions after the controller stops', async () => {
  const api = makeBridge()

  const claim: PhoneLinkClaim = {
    id: 'claim_A_1234567890123456',
    pairingId: 'pairing_A_1234567890123456',
    deviceName: 'Fixture iPhone',
    devicePublicKey: 'a'.repeat(87),
    keyFingerprint: 'b'.repeat(43),
    comparison: '123-456',
    expiresAt: Math.floor(Date.now() / 1000) + 600
  }

  const deviceId = 'device_A_1234567890123456'
  api.status.mockResolvedValue(
    success({
      ...makeStatus(),
      claims: [claim],
      devices: [
        {
          id: deviceId,
          deviceName: 'Linked iPhone',
          keyFingerprint: 'c'.repeat(43),
          createdAt: Math.floor(Date.now() / 1000) - 600,
          lastUsedAt: null
        }
      ]
    })
  )
  const heldCreate = deferred<PhoneLinkResult<PhoneLinkInvitation>>()
  const initialInvitation = makeInvitation()
  api.createPairing.mockResolvedValueOnce(success(initialInvitation)).mockReturnValueOnce(heldCreate.promise)
  const controller = createPhoneLinkSettings(api)
  const stop = controller.start()
  cleanups.push(stop)
  await vi.waitFor(() => expect(controller.$state.get().status?.owner).toEqual(firstOwner))
  await controller.act(controller.create)
  expect(controller.$state.get().invitation).toEqual(initialInvitation)

  const creating = controller.act(controller.create)
  expect(api.createPairing).toHaveBeenCalledTimes(2)
  stop()
  const stateAtStop = controller.$state.get()
  heldCreate.resolve(success(makeInvitation('pairing_late_1234567890123', 'STUV-WXYZ')))
  await creating
  expect(controller.$state.get()).toBe(stateAtStop)

  const callsAtStop = Object.values(api).map(method => method.mock.calls.length)
  await controller.refresh()
  await controller.act(controller.create)
  await controller.act(controller.cancel)
  await controller.act(() => controller.decide(firstOwner, claim, true))
  await controller.act(() => controller.decide(firstOwner, claim, false))
  await controller.act(() => controller.revoke(firstOwner, deviceId))
  await controller.act(() => controller.signIn(firstOwner, 'fixture-provider'))

  expect(Object.values(api).map(method => method.mock.calls.length)).toEqual(callsAtStop)
  expect(controller.$state.get()).toBe(stateAtStop)
})
