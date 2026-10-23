import type { IpcMain, IpcMainInvokeEvent } from 'electron'

import type { PhoneLinkClaim, PhoneLinkMutation, PhoneLinkOwner, PhoneLinksBridge } from './phone-link-types'

function mutationFrom(value: unknown): PhoneLinkMutation | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const row = value as Record<string, unknown>
  const owner = row.owner as PhoneLinkOwner

  switch (row.action) {
    case 'create':
      return { action: 'create', owner }

    case 'cancel':
      return typeof row.pairingId === 'string' ? { action: 'cancel', owner, pairingId: row.pairingId } : null

    case 'revoke':
      return typeof row.deviceId === 'string' ? { action: 'revoke', owner, deviceId: row.deviceId } : null

    case 'approve':

    case 'deny':
      return row.claim && typeof row.claim === 'object'
        ? { action: row.action, owner, claim: row.claim as PhoneLinkClaim }
        : null

    default:
      return null
  }
}

function dispatchMutation(api: PhoneLinksBridge, mutation: PhoneLinkMutation) {
  switch (mutation.action) {
    case 'create':
      return api.createPairing(mutation.owner)

    case 'cancel':
      return api.cancelPairing(mutation.owner, mutation.pairingId)

    case 'approve':
      return api.approveClaim(mutation.owner, mutation.claim)

    case 'deny':
      return api.denyClaim(mutation.owner, mutation.claim)

    case 'revoke':
      return api.revokeDevice(mutation.owner, mutation.deviceId)
  }
}

/** No renderer can select a URL or receive a native HTTP or dashboard credential. */
export function registerPhoneLinksIpc(
  ipc: Pick<IpcMain, 'handle'>,
  api: PhoneLinksBridge,
  trusted: (event: IpcMainInvokeEvent) => boolean
): void {
  const refused = { ok: false, reason: 'refused' } as const
  ipc.handle('hermes:phone-links:status', event => (trusted(event) ? api.status() : refused))
  ipc.handle('hermes:phone-links:sign-in', (event, owner, provider) => {
    if (!trusted(event)) {
      return refused
    }

    if (typeof provider !== 'string' || provider.length > 128) {
      return { ok: false, reason: 'invalid_request' }
    }

    return api.signInOwner(owner, provider)
  })
  ipc.handle('hermes:phone-links:mutate', (event, value) => {
    if (!trusted(event)) {
      return refused
    }

    const mutation = mutationFrom(value)

    return mutation ? dispatchMutation(api, mutation) : { ok: false, reason: 'invalid_request' }
  })
}
