import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { phoneLinkMessages } from '@/i18n/phone-links'
import { deferred } from '@/test/deferred'

import type {
  PhoneLinkClaim,
  PhoneLinkDevice,
  PhoneLinkInvitation,
  PhoneLinkOwner,
  PhoneLinkResult,
  PhoneLinksBridge,
  PhoneLinkStatus
} from '../../../electron/phone-link-types'

import { PhoneLinkSettings } from './phone-link-settings'

const copy = phoneLinkMessages('en')

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

function makeClaim(overrides: Partial<PhoneLinkClaim> = {}): PhoneLinkClaim {
  return {
    id: 'claim_A_1234567890123456',
    pairingId: 'pairing_A_1234567890123456',
    deviceName: 'Fixture iPhone',
    devicePublicKey: 'a'.repeat(87),
    keyFingerprint: 'b'.repeat(43),
    comparison: '123-456',
    expiresAt: Math.floor(Date.now() / 1000) + 600,
    ...overrides
  }
}

function makeDevice(overrides: Partial<PhoneLinkDevice> = {}): PhoneLinkDevice {
  return {
    id: 'device_A_1234567890123456',
    deviceName: 'First iPhone',
    keyFingerprint: 'c'.repeat(43),
    createdAt: Math.floor(Date.now() / 1000) - 600,
    lastUsedAt: null,
    ...overrides
  }
}

function makeStatus(overrides: Partial<PhoneLinkStatus> = {}): PhoneLinkStatus {
  return {
    hostId: 'host_A_1234567890123456',
    hostName: 'Fixture Mac',
    hostPublicKey: 'd'.repeat(87),
    gatewayUrl: 'https://phone-link-a.invalid',
    configured: true,
    ready: true,
    transportVerifiedAt: Math.floor(Date.now() / 1000),
    ownerSignInRequired: false,
    ownerAuthorizeBaseUrl: 'https://dashboard.example.test/loki',
    ownerLoginProviders: [],
    unavailableReason: null,
    claims: [],
    devices: [],
    ...overrides
  }
}

function makeInvitation(overrides: Partial<PhoneLinkInvitation> = {}): PhoneLinkInvitation {
  return {
    pairingId: 'pairing_A_1234567890123456',
    code: 'ABCD-EFGH',
    expiresAt: Math.floor(Date.now() / 1000) + 600,
    hostId: 'host_A_1234567890123456',
    hostName: 'Fixture Mac',
    ...overrides
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

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('reads unavailable readiness without creating codes or approving waiting phones', async () => {
  const api = makeBridge()
  api.status.mockResolvedValue(
    success(
      makeStatus({
        configured: false,
        ready: false,
        transportVerifiedAt: null,
        unavailableReason: 'transport_missing',
        claims: [makeClaim()]
      })
    )
  )
  render(<PhoneLinkSettings api={api} />)
  expect(await screen.findByText(copy.unavailableDetail)).toBeTruthy()
  const connect = screen.queryByRole('button', { name: copy.connect })

  if (connect) {
    expect(connect).toHaveProperty('disabled', true)
    fireEvent.click(connect)
  }

  expect(api.status).toHaveBeenCalledTimes(1)
  expect(api.createPairing).not.toHaveBeenCalled()
  expect(api.approveClaim).not.toHaveBeenCalled()
  expect(api.denyClaim).not.toHaveBeenCalled()
  expect(api.revokeDevice).not.toHaveBeenCalled()
})

it('allows an explicit code request for configured transport without probing it on load', async () => {
  const api = makeBridge()
  const invitation = makeInvitation()
  api.status.mockResolvedValue(
    success(makeStatus({ ready: false, transportVerifiedAt: null, unavailableReason: 'transport_unverified' }))
  )
  api.createPairing.mockResolvedValue(success(invitation))
  render(<PhoneLinkSettings api={api} />)
  expect(await screen.findByText(copy.transportUnverified)).toBeTruthy()
  const connect = screen.getByRole('button', { name: copy.connect })
  expect(connect).toHaveProperty('disabled', false)
  expect(api.createPairing).not.toHaveBeenCalled()
  expect(api.approveClaim).not.toHaveBeenCalled()
  fireEvent.click(connect)
  expect(await screen.findByText(invitation.code)).toBeTruthy()
  expect(api.createPairing).toHaveBeenCalledExactlyOnceWith(firstOwner)
})

it('requires explicit owner sign-in and a refreshed server status before creating a code', async () => {
  const api = makeBridge()
  const provider = { name: 'stub', displayName: 'Fixture owner', supportsPassword: false }
  api.status
    .mockResolvedValueOnce(
      success(
        makeStatus({
          ready: false,
          ownerSignInRequired: true,
          ownerLoginProviders: [provider],
          unavailableReason: 'owner_sign_in_required'
        })
      )
    )
    .mockResolvedValue(success(makeStatus()))
  render(<PhoneLinkSettings api={api} />)
  expect(await screen.findByText(copy.ownerSignInRequired)).toBeTruthy()
  const connect = screen.getByRole('button', { name: copy.connect })
  expect(connect).toHaveProperty('disabled', true)
  expect(api.signInOwner).not.toHaveBeenCalled()
  expect(api.createPairing).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: copy.signIn }))
  await waitFor(() => expect(api.signInOwner).toHaveBeenCalledExactlyOnceWith(firstOwner, provider.name))
  await waitFor(() => expect(api.status).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(screen.getByRole('button', { name: copy.connect })).toHaveProperty('disabled', false))
  expect(api.createPairing).not.toHaveBeenCalled()
  expect(api.approveClaim).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: copy.connect }))
  expect(await screen.findByText(makeInvitation().code)).toBeTruthy()
  expect(api.createPairing).toHaveBeenCalledExactlyOnceWith(firstOwner)
})

it('creates a code only after Connect and cancels that exact pairing', async () => {
  const api = makeBridge()
  const invitation = makeInvitation()
  api.createPairing.mockResolvedValue(success(invitation))
  render(<PhoneLinkSettings api={api} />)
  const connect = await screen.findByRole('button', { name: copy.connect })
  await waitFor(() => expect(connect).toHaveProperty('disabled', false))
  expect(api.createPairing).not.toHaveBeenCalled()
  fireEvent.click(connect)
  expect(await screen.findByText(invitation.code)).toBeTruthy()
  expect(api.createPairing).toHaveBeenCalledExactlyOnceWith(firstOwner)
  expect(api.approveClaim).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: copy.cancelCode }))
  await waitFor(() => expect(api.cancelPairing).toHaveBeenCalledExactlyOnceWith(firstOwner, invitation.pairingId))
  await waitFor(() => expect(screen.queryByText(invitation.code)).toBeNull())
  expect(api.createPairing).toHaveBeenCalledTimes(1)
})

it('keeps advertised password sign-in available when the common OAuth address is unavailable', async () => {
  const api = makeBridge()
  const provider = { name: 'local-password', displayName: 'Loki owner', supportsPassword: true }
  api.status
    .mockResolvedValueOnce(
      success(makeStatus({ ownerAuthorizeBaseUrl: null, ownerSignInRequired: true, ownerLoginProviders: [provider] }))
    )
    .mockResolvedValue(success(makeStatus()))
  render(<PhoneLinkSettings api={api} />)
  expect(await screen.findByText(copy.ownerSignInRequired)).toBeTruthy()
  expect(screen.queryByText(copy.ownerSignInUnavailable)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: copy.signIn }))
  await waitFor(() => expect(api.signInOwner).toHaveBeenCalledExactlyOnceWith(firstOwner, provider.name))
  expect(api.createPairing).not.toHaveBeenCalled()
})

it('keeps creation busy through its held authoritative refresh and cannot dispatch another code', async () => {
  const api = makeBridge()
  const invitation = makeInvitation()
  const refreshed = deferred<PhoneLinkResult<PhoneLinkStatus>>()
  api.status
    .mockResolvedValueOnce(success(makeStatus()))
    .mockReturnValueOnce(refreshed.promise)
    .mockResolvedValue(success(makeStatus()))
  api.createPairing.mockResolvedValue(success(invitation))
  render(<PhoneLinkSettings api={api} />)
  const connect = await screen.findByRole('button', { name: copy.connect })
  await waitFor(() => expect(connect).toHaveProperty('disabled', false))
  fireEvent.click(connect)
  await waitFor(() => expect(api.createPairing).toHaveBeenCalledExactlyOnceWith(firstOwner))
  await waitFor(() => expect(api.status).toHaveBeenCalledTimes(2))
  expect(connect).toHaveProperty('disabled', true)
  expect(connect.getAttribute('aria-busy')).toBe('true')
  expect(screen.getByRole('button', { name: copy.connect })).toBe(connect)
  fireEvent.click(connect)
  expect(api.createPairing).toHaveBeenCalledTimes(1)
  await act(async () => refreshed.resolve(success(makeStatus())))
  expect(await screen.findByText(invitation.code)).toBeTruthy()
  expect(api.createPairing).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: copy.cancelCode }))
  await waitFor(() => expect(api.cancelPairing).toHaveBeenCalledExactlyOnceWith(firstOwner, invitation.pairingId))
})

it('retires an expired code without generating a replacement automatically', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T12:00:00Z'))
  const api = makeBridge()
  const invitation = makeInvitation({ expiresAt: Math.floor(Date.now() / 1000) + 2 })
  api.createPairing.mockResolvedValue(success(invitation))
  render(<PhoneLinkSettings api={api} />)
  await act(async () => {
    await Promise.resolve()
  })
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: copy.connect }))
  })
  expect(screen.getByText(invitation.code)).toBeTruthy()
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000)
  })
  expect(screen.getByText(copy.codeExpired)).toBeTruthy()
  expect(api.createPairing).toHaveBeenCalledTimes(1)
  expect(api.cancelPairing).not.toHaveBeenCalled()
  expect(api.approveClaim).not.toHaveBeenCalled()
})

it('shows the exact comparison, fingerprint and access before explicit approval', async () => {
  const api = makeBridge()
  const claim = makeClaim()
  api.status.mockResolvedValue(success(makeStatus({ claims: [claim] })))
  render(<PhoneLinkSettings api={api} />)
  fireEvent.click(await screen.findByRole('button', { name: copy.approve }))
  const dialog = await screen.findByRole('dialog', { name: copy.approvalTitle(claim.deviceName) })
  expect(within(dialog).getByText(claim.comparison)).toBeTruthy()
  expect(within(dialog).getByText(claim.keyFingerprint)).toBeTruthy()
  expect(within(dialog).getByText(copy.approvalConsent)).toBeTruthy()
  expect(within(dialog).getByText(copy.approvalCheck)).toBeTruthy()
  expect(api.approveClaim).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: copy.approveConfirm }))
  await waitFor(() => expect(api.approveClaim).toHaveBeenCalledExactlyOnceWith(firstOwner, claim))
  expect(api.denyClaim).not.toHaveBeenCalled()
  expect(api.createPairing).not.toHaveBeenCalled()
})

it('cancels approval review without dispatching an approval or denial', async () => {
  const api = makeBridge()
  const claim = makeClaim()
  api.status.mockResolvedValue(success(makeStatus({ claims: [claim] })))
  render(<PhoneLinkSettings api={api} />)
  fireEvent.click(await screen.findByRole('button', { name: copy.approve }))
  const dialog = await screen.findByRole('dialog', { name: copy.approvalTitle(claim.deviceName) })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(api.approveClaim).not.toHaveBeenCalled()
  expect(api.denyClaim).not.toHaveBeenCalled()
})

it('does not publish a held invitation after another bridge and owner replace it', async () => {
  const api = makeBridge()
  const next = makeBridge()
  const held = deferred<PhoneLinkResult<PhoneLinkInvitation>>()
  const invitation = makeInvitation()
  api.createPairing.mockReturnValue(held.promise)
  next.status.mockResolvedValue(success(makeStatus({ hostName: 'Replacement Mac' }), nextOwner))
  const view = render(<PhoneLinkSettings api={api} />)
  const connect = await screen.findByRole('button', { name: copy.connect })
  await waitFor(() => expect(connect).toHaveProperty('disabled', false))
  fireEvent.click(connect)
  await waitFor(() => expect(api.createPairing).toHaveBeenCalledTimes(1))
  view.rerender(<PhoneLinkSettings api={next} />)
  await waitFor(() => expect(next.status).toHaveBeenCalledTimes(1))
  await act(async () => held.resolve(success(invitation)))
  expect(screen.queryByText(invitation.code)).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(next.createPairing).not.toHaveBeenCalled()
  expect(next.approveClaim).not.toHaveBeenCalled()
})

it('retires a pending approval when the owner changes and cannot approve the old claim', async () => {
  const api = makeBridge()
  const next = makeBridge()
  const claim = makeClaim()
  api.status.mockResolvedValue(success(makeStatus({ claims: [claim] })))
  next.status.mockResolvedValue(success(makeStatus(), nextOwner))
  const view = render(<PhoneLinkSettings api={api} />)
  fireEvent.click(await screen.findByRole('button', { name: copy.approve }))
  await screen.findByRole('dialog', { name: copy.approvalTitle(claim.deviceName) })
  view.rerender(<PhoneLinkSettings api={next} />)
  await waitFor(() => expect(next.status).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(screen.queryByRole('button', { name: copy.approveConfirm })).toBeNull()
  expect(api.approveClaim).not.toHaveBeenCalled()
  expect(next.approveClaim).not.toHaveBeenCalled()
})

it('ignores a held old status response instead of presenting its claim under a new owner', async () => {
  const api = makeBridge()
  const next = makeBridge()
  const held = deferred<PhoneLinkResult<PhoneLinkStatus>>()
  const claim = makeClaim()
  api.status.mockReturnValue(held.promise)
  next.status.mockResolvedValue(success(makeStatus(), nextOwner))
  const view = render(<PhoneLinkSettings api={api} />)
  await waitFor(() => expect(api.status).toHaveBeenCalledTimes(1))
  view.rerender(<PhoneLinkSettings api={next} />)
  expect(await screen.findByText(copy.noPending)).toBeTruthy()
  await act(async () => held.resolve(success(makeStatus({ claims: [claim] }))))
  expect(screen.queryByText(claim.deviceName)).toBeNull()
  expect(screen.queryByRole('button', { name: copy.approve })).toBeNull()
  expect(api.approveClaim).not.toHaveBeenCalled()
  expect(next.approveClaim).not.toHaveBeenCalled()
})

it('revokes only the selected phone and uses refreshed server devices as the result', async () => {
  const api = makeBridge()
  const first = makeDevice()

  const second = makeDevice({
    id: 'device_B_1234567890123456',
    deviceName: 'Second iPhone',
    keyFingerprint: 'e'.repeat(43)
  })

  const refreshed = deferred<PhoneLinkResult<PhoneLinkStatus>>()
  api.status.mockResolvedValueOnce(success(makeStatus({ devices: [first, second] }))).mockReturnValue(refreshed.promise)
  render(<PhoneLinkSettings api={api} />)
  expect(await screen.findByText(first.deviceName)).toBeTruthy()
  expect(screen.getByText(second.deviceName)).toBeTruthy()
  fireEvent.click(screen.getAllByRole('button', { name: copy.revoke })[0])
  const dialog = await screen.findByRole('dialog', { name: copy.revokeTitle(first.deviceName) })
  expect(api.revokeDevice).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: copy.revoke }))
  await waitFor(() => expect(api.revokeDevice).toHaveBeenCalledExactlyOnceWith(firstOwner, first.id))
  await waitFor(() => expect(api.status).toHaveBeenCalledTimes(2))
  expect(api.approveClaim).not.toHaveBeenCalled()
  await act(async () => refreshed.resolve(success(makeStatus({ devices: [second] }))))
  await waitFor(() => expect(screen.queryByText(first.deviceName)).toBeNull())
  expect(screen.getByText(second.deviceName)).toBeTruthy()
  expect(api.revokeDevice).toHaveBeenCalledTimes(1)
})
