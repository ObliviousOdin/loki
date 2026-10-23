import { readJsonErrorBody, readStatusCode } from './api-transport'
import type { GatewayEndpoint } from './local-gateway'
import type { NativeTokenSet } from './native-oauth'
import type {
  PhoneLinkFailureReason,
  PhoneLinkMutation,
  PhoneLinkOwner,
  PhoneLinkResult,
  PhoneLinksBridge,
  PhoneLinkStatus
} from './phone-link-types'
import {
  parsePhoneLinkClaim,
  parsePhoneLinkInvitation,
  parsePhoneLinkStatus,
  phoneLinkIdentifier,
  verifiedPhoneLinkAccount
} from './phone-link-wire'

export interface PhoneLinkLocalDescriptor {
  baseUrl: string
  authMode?: string
  gatewayEndpoint?: GatewayEndpoint
}

export interface PhoneLinkManagementDeps {
  withLocal<T>(use: (descriptor: PhoneLinkLocalDescriptor) => Promise<T>): Promise<T>
  request(
    descriptor: PhoneLinkLocalDescriptor,
    path: string,
    options: {
      method?: string
      body?: unknown
      bearer?: string
    }
  ): Promise<unknown>
  login(baseUrl: string, provider: string, authorizeBaseUrl: string): Promise<NativeTokenSet>
  now?: () => number
}

interface AccountGrant {
  owner: PhoneLinkOwner
  hostId: string
  hostKey: string
  bearer: string
  expiresAt: number
  userId: string
  provider: string
}

export function samePhoneManagementOwner(a: PhoneLinkOwner, b: PhoneLinkOwner): boolean {
  return (
    a.origin === b.origin &&
    a.instanceId === b.instanceId &&
    a.profileId === b.profileId &&
    a.authorityEpoch === b.authorityEpoch
  )
}

function localOwner(descriptor: PhoneLinkLocalDescriptor): PhoneLinkOwner {
  const endpoint = descriptor.gatewayEndpoint,
    origin = new URL(descriptor.baseUrl)

  if (
    !endpoint ||
    descriptor.authMode !== 'native' ||
    endpoint.api_origin !== descriptor.baseUrl ||
    !['http:', 'https:'].includes(origin.protocol) ||
    !['127.0.0.1', '[::1]'].includes(origin.hostname) ||
    origin.pathname !== '/' ||
    origin.username ||
    origin.password ||
    origin.search ||
    origin.hash ||
    !endpoint.instance_id ||
    !endpoint.profile_id ||
    !Number.isSafeInteger(endpoint.authority_epoch) ||
    endpoint.authority_epoch < 0 ||
    endpoint.runtime_protocol !== 1 ||
    !endpoint.capabilities.includes('session-authority-v1')
  ) {
    throw new Error('unavailable')
  }

  return {
    origin: descriptor.baseUrl,
    instanceId: endpoint.instance_id,
    profileId: endpoint.profile_id,
    authorityEpoch: endpoint.authority_epoch
  }
}

function validExpectedOwner(value: PhoneLinkOwner | undefined): value is PhoneLinkOwner {
  return Boolean(
    value &&
    typeof value.origin === 'string' &&
    typeof value.instanceId === 'string' &&
    typeof value.profileId === 'string' &&
    Number.isSafeInteger(value.authorityEpoch)
  )
}

function authorizeForProvider(status: PhoneLinkStatus, provider: string, localOrigin: string): string | null {
  const selected = status.ownerLoginProviders.find(value => value.name === provider)

  if (!selected) {
    return null
  }

  return selected.supportsPassword ? localOrigin : status.ownerAuthorizeBaseUrl
}

function failure(error: unknown): PhoneLinkFailureReason {
  const status = readStatusCode(error),
    body = readJsonErrorBody(error)

  const detail = body?.detail

  if (status === 409 && detail === 'owner_sign_in_required') {
    return 'owner_sign_in_required'
  }

  if (status === 404 || status === 405) {
    return 'unsupported'
  }

  if ([400, 401, 403, 409, 429].includes(status)) {
    return 'refused'
  }

  const reason = error instanceof Error ? error.message : ''

  if (['owner_changed', 'owner_sign_in_required', 'invalid_request', 'refused'].includes(reason)) {
    return reason as PhoneLinkFailureReason
  }

  return 'unavailable'
}

/** Only main calls this manager. Native HTTP grants and the verified owner bearer stay there. */
export function createPhoneLinksManager(deps: PhoneLinkManagementDeps): PhoneLinksBridge {
  let grant: AccountGrant | null = null
  let loginGeneration = 0
  const now = deps.now ?? (() => Date.now() / 1000)

  const bind = (descriptor: PhoneLinkLocalDescriptor, expected?: PhoneLinkOwner) => {
    const owner = localOwner(descriptor)

    if (grant && !samePhoneManagementOwner(grant.owner, owner)) {
      grant = null
      loginGeneration += 1
    }

    if (expected && !samePhoneManagementOwner(owner, expected)) {
      throw new Error('owner_changed')
    }

    return owner
  }

  const validGrant = (owner: PhoneLinkOwner) =>
    grant && samePhoneManagementOwner(grant.owner, owner) && grant.expiresAt > now() + 5 ? grant : null

  const read = async (descriptor: PhoneLinkLocalDescriptor, owner: PhoneLinkOwner) => {
    let active = validGrant(owner)
    let raw: unknown

    try {
      raw = await deps.request(descriptor, '/api/device-links', { bearer: active?.bearer })
    } catch (error) {
      if (!active || ![401, 403].includes(readStatusCode(error))) {
        throw error
      }

      grant = null
      active = null
      raw = await deps.request(descriptor, '/api/device-links', {})
    }

    const value = parsePhoneLinkStatus(raw, owner.origin)

    if (active && (active.hostId !== value.hostId || active.hostKey !== value.hostPublicKey)) {
      grant = null
    }

    return value
  }

  const result = async <T>(
    operation: (descriptor: PhoneLinkLocalDescriptor, owner: PhoneLinkOwner) => Promise<T>,
    expected?: PhoneLinkOwner
  ): Promise<PhoneLinkResult<T>> => {
    try {
      return await deps.withLocal(async descriptor => {
        const owner = bind(descriptor, expected),
          value = await operation(descriptor, owner)

        const current = await deps.withLocal(async fresh => samePhoneManagementOwner(bind(fresh), owner))

        if (!current) {
          throw new Error('owner_changed')
        }

        return { ok: true as const, owner, value }
      })
    } catch (error) {
      return { ok: false, reason: failure(error) }
    }
  }

  const mutate = async (mutation: PhoneLinkMutation) => {
    if (!validExpectedOwner(mutation?.owner)) {
      return { ok: false as const, reason: 'invalid_request' as const }
    }

    return result(async (descriptor, owner) => {
      const current = await read(descriptor, owner)

      if (mutation.action === 'create') {
        const active = validGrant(owner)

        if (!active || current.ownerSignInRequired) {
          throw new Error('owner_sign_in_required')
        }

        if (!current.configured || current.hostId !== active.hostId || current.hostPublicKey !== active.hostKey) {
          throw new Error('unavailable')
        }

        const value = parsePhoneLinkInvitation(
          await deps.request(descriptor, '/api/device-links/pairings', {
            method: 'POST',
            body: {},
            bearer: active.bearer
          })
        )

        if (value.hostId !== current.hostId) {
          throw new Error('owner_changed')
        }

        return value
      }

      return executePhoneMutation(mutation, current, descriptor, deps)
    }, mutation.owner)
  }

  return {
    status: () => result(read),
    signInOwner: (expected, provider) => {
      if (!validExpectedOwner(expected)) {
        return Promise.resolve({ ok: false, reason: 'invalid_request' })
      }

      return result(async (descriptor, owner) => {
        const current = await read(descriptor, owner)

        const authorizeBaseUrl = authorizeForProvider(current, provider, descriptor.baseUrl)

        if (!current.hostId || !authorizeBaseUrl) {
          throw new Error('refused')
        }

        const request = ++loginGeneration
        const tokens = await deps.login(descriptor.baseUrl, provider, authorizeBaseUrl)
        const raw = await deps.request(descriptor, '/api/device-links', { bearer: tokens.accessToken })

        const verified = verifiedPhoneLinkAccount(raw),
          fresh = parsePhoneLinkStatus(raw, owner.origin)

        if (
          request !== loginGeneration ||
          authorizeForProvider(fresh, provider, descriptor.baseUrl) !== authorizeBaseUrl ||
          fresh.hostId !== current.hostId ||
          fresh.hostPublicKey !== current.hostPublicKey ||
          !verified ||
          verified.userId !== tokens.userId ||
          verified.provider !== tokens.provider ||
          tokens.expiresAt <= now() + 5
        ) {
          throw new Error('refused')
        }

        const stillCurrent = await deps.withLocal(async freshDescriptor =>
          samePhoneManagementOwner(bind(freshDescriptor), owner)
        )

        if (!stillCurrent || request !== loginGeneration) {
          throw new Error('owner_changed')
        }

        // Refresh credentials are deliberately discarded. This explicit approval session is memory-only.
        grant = {
          owner,
          hostId: current.hostId,
          hostKey: current.hostPublicKey,
          bearer: tokens.accessToken,
          expiresAt: tokens.expiresAt,
          userId: verified.userId,
          provider: verified.provider
        }

        return null
      }, expected)
    },
    createPairing: async owner => {
      const reply = await mutate({ action: 'create', owner })

      return reply as Awaited<ReturnType<PhoneLinksBridge['createPairing']>>
    },
    cancelPairing: async (owner, pairingId) => {
      const reply = await mutate({ action: 'cancel', owner, pairingId })

      return reply as PhoneLinkResult<null>
    },
    approveClaim: async (owner, claim) => {
      const reply = await mutate({ action: 'approve', owner, claim })

      return reply as PhoneLinkResult<null>
    },
    denyClaim: async (owner, claim) => {
      const reply = await mutate({ action: 'deny', owner, claim })

      return reply as PhoneLinkResult<null>
    },
    revokeDevice: async (owner, deviceId) => {
      const reply = await mutate({ action: 'revoke', owner, deviceId })

      return reply as PhoneLinkResult<null>
    }
  }
}

async function executePhoneMutation(
  mutation: Exclude<PhoneLinkMutation, { action: 'create' }>,
  current: PhoneLinkStatus,
  descriptor: PhoneLinkLocalDescriptor,
  deps: PhoneLinkManagementDeps
): Promise<null> {
  if (mutation.action === 'cancel') {
    await deps.request(descriptor, `/api/device-links/pairings/${phoneLinkIdentifier(mutation.pairingId)}`, {
      method: 'DELETE'
    })
  } else if (mutation.action === 'revoke') {
    await deps.request(descriptor, `/api/device-links/devices/${phoneLinkIdentifier(mutation.deviceId)}`, {
      method: 'DELETE'
    })
  } else {
    const claim = parsePhoneLinkClaim({
      claim_id: mutation.claim.id,
      pairing_id: mutation.claim.pairingId,
      device_name: mutation.claim.deviceName,
      device_public_key: mutation.claim.devicePublicKey,
      key_fingerprint: mutation.claim.keyFingerprint,
      comparison: mutation.claim.comparison,
      expires_at: mutation.claim.expiresAt
    })

    const fresh = current.claims.find(value => value.id === claim.id)

    if (
      !fresh ||
      fresh.keyFingerprint !== claim.keyFingerprint ||
      fresh.comparison !== claim.comparison ||
      fresh.devicePublicKey !== claim.devicePublicKey ||
      fresh.expiresAt !== claim.expiresAt
    ) {
      throw new Error('refused')
    }

    await deps.request(descriptor, `/api/device-links/claims/${claim.id}/${mutation.action}`, {
      method: 'POST',
      body: mutation.action === 'approve' ? { key_fingerprint: claim.keyFingerprint, comparison: claim.comparison } : {}
    })
  }

  return null
}
