import { atom } from 'nanostores'

import { samePhoneLinkClaim, samePhoneLinkOwner } from '@/lib/phone-link-identity'

import type {
  PhoneLinkClaim,
  PhoneLinkFailureReason,
  PhoneLinkInvitation,
  PhoneLinkOwner,
  PhoneLinkResult,
  PhoneLinksBridge,
  PhoneLinkStatus
} from '../../electron/phone-link-types'

export interface PhoneLinkSettingsState {
  status: Extract<PhoneLinkResult<PhoneLinkStatus>, { ok: true }> | null
  invitation: PhoneLinkInvitation | null
  issue: PhoneLinkFailureReason | null
  loading: boolean
  busy: boolean
}

function initialState(): PhoneLinkSettingsState {
  return { status: null, invitation: null, issue: null, loading: true, busy: false }
}

/** One mounted settings page owns its transient code; the gateway owns every device grant. */
export function createPhoneLinkSettings(api: PhoneLinksBridge | undefined) {
  const $state = atom<PhoneLinkSettingsState>(initialState())

  let epoch = 0,
    reads = 0,
    active = false

  const update = (change: (state: PhoneLinkSettingsState) => PhoneLinkSettingsState) => $state.set(change($state.get()))

  const refresh = async (duringAction = false) => {
    if (!active || ($state.get().busy && !duringAction)) {
      return
    }

    if (!api) {
      update(state => ({ ...state, loading: false, issue: 'unsupported' }))

      return
    }

    const request = ++reads,
      generation = epoch

    try {
      const result = await api.status()

      if (generation !== epoch || request !== reads || ($state.get().busy && !duringAction)) {
        return
      }

      if (!result.ok) {
        update(state => ({ ...state, loading: false, issue: result.reason }))

        return
      }

      const previous = $state.get().status
      const changed = previous && !samePhoneLinkOwner(previous.owner, result.owner)

      if (changed) {
        epoch += 1
      }

      update(state => ({
        ...state,
        status: result,
        invitation: changed ? null : state.invitation,
        loading: false,
        busy: changed ? false : state.busy,
        issue: null
      }))
    } catch {
      if (generation === epoch && request === reads) {
        update(state => ({ ...state, loading: false, issue: 'unavailable' }))
      }
    }
  }

  const start = () => {
    active = true
    epoch += 1
    reads += 1
    $state.set(initialState())
    void refresh()

    const visibleRefresh = () => {
      if (document.visibilityState !== 'hidden') {
        void refresh()
      }
    }

    const timer = window.setInterval(visibleRefresh, 5_000)
    window.addEventListener('focus', visibleRefresh)
    document.addEventListener('visibilitychange', visibleRefresh)

    return () => {
      active = false
      epoch += 1
      reads += 1
      window.clearInterval(timer)
      window.removeEventListener('focus', visibleRefresh)
      document.removeEventListener('visibilitychange', visibleRefresh)
    }
  }

  const mutate = async <T>(owner: PhoneLinkOwner, action: () => Promise<PhoneLinkResult<T>>): Promise<T> => {
    const status = $state.get().status

    if (!active || $state.get().busy || !status || !samePhoneLinkOwner(owner, status.owner)) {
      throw new Error('owner_changed')
    }

    const operation = epoch
    let failed: PhoneLinkFailureReason | null = null
    reads += 1
    update(state => ({ ...state, busy: true, issue: null }))

    try {
      const result = await action()

      if (operation !== epoch) {
        throw new Error('owner_changed')
      }

      if (!result.ok) {
        failed = result.reason
        throw new Error(result.reason)
      }

      if (!samePhoneLinkOwner(owner, result.owner)) {
        throw new Error('owner_changed')
      }

      return result.value
    } catch (error) {
      failed ??= error instanceof Error && error.message === 'owner_changed' ? 'owner_changed' : 'unavailable'
      throw new Error(failed)
    } finally {
      if (operation === epoch) {
        await refresh(true)

        if (operation === epoch) {
          update(state => ({ ...state, busy: false, issue: failed ?? state.issue }))
        }
      }
    }
  }

  const create = async () => {
    const captured = $state.get().status,
      operation = epoch

    if (!api || !captured || !captured.value.configured || captured.value.ownerSignInRequired) {
      return
    }

    const invitation = await mutate(captured.owner, () => api.createPairing(captured.owner))
    const current = $state.get().status

    if (operation === epoch && current && samePhoneLinkOwner(captured.owner, current.owner)) {
      update(state => ({ ...state, invitation }))
    }
  }

  const cancel = async () => {
    const { status, invitation } = $state.get(),
      operation = epoch

    if (!api || !status || !invitation) {
      return
    }

    await mutate(status.owner, () => api.cancelPairing(status.owner, invitation.pairingId))

    if (operation === epoch) {
      update(state => ({
        ...state,
        invitation: state.invitation?.pairingId === invitation.pairingId ? null : state.invitation
      }))
    }
  }

  const decide = async (owner: PhoneLinkOwner, claim: PhoneLinkClaim, approve: boolean) => {
    const operation = epoch

    if (
      !api ||
      !$state.get().status?.value.claims.some(value => samePhoneLinkClaim(value, claim)) ||
      claim.expiresAt * 1_000 <= Date.now()
    ) {
      throw new Error('refused')
    }

    await mutate(owner, () => (approve ? api.approveClaim(owner, claim) : api.denyClaim(owner, claim)))
    const current = $state.get().status

    if (approve && operation === epoch && current && samePhoneLinkOwner(owner, current.owner)) {
      update(state => ({
        ...state,
        invitation: state.invitation?.pairingId === claim.pairingId ? null : state.invitation
      }))
    }
  }

  const revoke = async (owner: PhoneLinkOwner, deviceId: string) => {
    if (!api || !$state.get().status?.value.devices.some(device => device.id === deviceId)) {
      throw new Error('refused')
    }

    await mutate(owner, () => api.revokeDevice(owner, deviceId))
  }

  const signIn = async (owner: PhoneLinkOwner, provider: string) => {
    if (api) {
      await mutate(owner, () => api.signInOwner(owner, provider))
    }
  }

  const act = async (action: () => Promise<unknown>) => {
    const operation = epoch

    try {
      await action()
    } catch (error) {
      if (active && operation === epoch) {
        const issue =
          $state.get().issue ??
          (error instanceof Error && error.message === 'owner_changed' ? 'owner_changed' : 'unavailable')

        update(state => ({ ...state, issue }))
      }
    }
  }

  return { $state, start, refresh, create, cancel, decide, revoke, signIn, act }
}
