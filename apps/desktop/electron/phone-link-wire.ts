import type { PhoneLinkClaim, PhoneLinkDevice, PhoneLinkInvitation, PhoneLinkStatus } from './phone-link-types'

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('invalid_response')
  }

  return value as Record<string, unknown>
}

function text(value: unknown, maximum = 256): string {
  if (
    typeof value !== 'string' ||
    !value ||
    value.length > maximum ||
    [...value].some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
  ) {
    throw new Error('invalid_response')
  }

  return value
}

export function phoneLinkIdentifier(value: unknown): string {
  const result = text(value, 128)

  if (!/^[A-Za-z0-9_-]{16,128}$/.test(result)) {
    throw new Error('invalid_request')
  }

  return result
}

function timestamp(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value <= 0) {
    throw new Error('invalid_response')
  }

  return value
}

function list(value: unknown, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error('invalid_response')
  }

  return value
}

export function phoneLinkPublicOrigin(value: unknown): string {
  const raw = text(value, 2048),
    url = new URL(raw)

  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('invalid_response')
  }

  return url.origin
}

function key(value: unknown, length: number): string {
  const result = text(value, length)

  if (result.length !== length || !/^[A-Za-z0-9_-]+$/.test(result)) {
    throw new Error('invalid_response')
  }

  return result
}

export function parsePhoneLinkClaim(value: unknown): PhoneLinkClaim {
  const row = object(value),
    comparison = text(row.comparison, 7)

  if (!/^\d{3}-\d{3}$/.test(comparison)) {
    throw new Error('invalid_response')
  }

  return {
    id: phoneLinkIdentifier(row.claim_id),
    pairingId: phoneLinkIdentifier(row.pairing_id),
    deviceName: text(row.device_name),
    devicePublicKey: key(row.device_public_key, 87),
    keyFingerprint: key(row.key_fingerprint, 43),
    comparison,
    expiresAt: timestamp(row.expires_at)
  }
}

function parseDevice(value: unknown): PhoneLinkDevice | null {
  const row = object(value)

  if (row.revoked_at !== null) {
    timestamp(row.revoked_at)

    return null
  }

  return {
    id: phoneLinkIdentifier(row.device_id),
    deviceName: text(row.device_name),
    keyFingerprint: key(row.key_fingerprint, 43),
    createdAt: timestamp(row.created_at),
    lastUsedAt: row.last_used_at === null ? null : timestamp(row.last_used_at)
  }
}

function hostFields(value: unknown, ready: boolean) {
  if (value === null) {
    if (ready) {
      throw new Error('invalid_response')
    }

    return { hostId: '', hostName: '', hostPublicKey: '', gatewayUrl: '' }
  }

  const host = object(value)

  return {
    hostId: phoneLinkIdentifier(host.host_id),
    hostName: text(host.host_name),
    hostPublicKey: key(host.host_public_key, 87),
    gatewayUrl: phoneLinkPublicOrigin(host.gateway_url)
  }
}

function readiness(row: Record<string, unknown>): PhoneLinkStatus['unavailableReason'] {
  if (row.owner_sign_in_required) {
    return 'owner_sign_in_required'
  }

  if (row.unavailable_reason === 'transport_missing' || !row.enabled) {
    return 'transport_missing'
  }

  if (row.unavailable_reason === 'transport_unverified') {
    return 'transport_unverified'
  }

  return row.ready ? null : 'offline'
}

function ownerAuthorizeBase(value: unknown, localOrigin: string, phoneOrigin: string): string | null {
  if (
    typeof value !== 'string' ||
    value.length > 2048 ||
    value.includes('\\') ||
    [...value].some(character => character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)
  ) {
    return null
  }

  try {
    const url = new URL(value)

    if (url.username || url.password || url.search || url.hash || url.origin === phoneOrigin) {
      return null
    }

    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && url.origin === localOrigin)) {
      return null
    }

    return `${url.origin}${url.pathname.replace(/\/+$/, '')}`
  } catch {
    return null
  }
}

function ownerLogin(row: Record<string, unknown>, localOrigin: string, phoneOrigin: string) {
  const login = row.owner_login === undefined ? null : object(row.owner_login)

  const loginAvailable =
    login?.authorize_path === '/auth/native/authorize' && login?.token_path === '/auth/native/token'

  const authorizeBaseUrl = loginAvailable
    ? ownerAuthorizeBase(login.authorize_base_url, localOrigin, phoneOrigin)
    : null

  const providers = loginAvailable
    ? list(login.providers, 32).map(value => {
        const provider = object(value)

        return {
          name: text(provider.name, 128),
          displayName: text(provider.display_name, 256),
          supportsPassword: provider.supports_password === true
        }
      })
    : []

  return {
    ownerAuthorizeBaseUrl: authorizeBaseUrl,
    ownerLoginProviders: providers.filter(provider => provider.supportsPassword || authorizeBaseUrl !== null)
  }
}

export function parsePhoneLinkStatus(value: unknown, localOrigin: string): PhoneLinkStatus {
  const row = object(value)

  if (
    typeof row.ready !== 'boolean' ||
    typeof row.configured !== 'boolean' ||
    typeof row.enabled !== 'boolean' ||
    typeof row.owner_sign_in_required !== 'boolean'
  ) {
    throw new Error('invalid_response')
  }

  const host = hostFields(row.host, row.ready)

  return {
    ...host,
    configured: row.enabled && row.configured,
    ready: row.enabled && row.ready,
    transportVerifiedAt: row.transport_verified_at === null ? null : timestamp(row.transport_verified_at),
    unavailableReason: readiness(row),
    ownerSignInRequired: row.owner_sign_in_required,
    ...ownerLogin(row, localOrigin, host.gatewayUrl),
    claims: list(row.claims, 128).map(parsePhoneLinkClaim),
    devices: list(row.devices, 64)
      .map(parseDevice)
      .filter((device): device is PhoneLinkDevice => device !== null)
  }
}

export function parsePhoneLinkInvitation(value: unknown): PhoneLinkInvitation {
  const row = object(value),
    code = text(row.code, 9)

  if (!/^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$/.test(code)) {
    throw new Error('invalid_response')
  }

  return {
    pairingId: phoneLinkIdentifier(row.pairing_id),
    code,
    expiresAt: timestamp(row.expires_at),
    hostId: phoneLinkIdentifier(row.host_id),
    hostName: text(row.host_name)
  }
}

export function verifiedPhoneLinkAccount(value: unknown): { userId: string; provider: string } | null {
  const owner = object(value).owner

  if (owner === null) {
    return null
  }

  const row = object(owner)

  return { userId: text(row.user_id, 4096), provider: text(row.provider, 128) }
}
