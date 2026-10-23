/** Renderer-facing phone management values. No access grants or private keys cross this bridge. */
export interface PhoneLinkOwner {
  origin: string
  instanceId: string
  profileId: string
  authorityEpoch: number
}

export interface PhoneLinkClaim {
  id: string
  pairingId: string
  deviceName: string
  devicePublicKey: string
  keyFingerprint: string
  comparison: string
  expiresAt: number
}

export interface PhoneLinkDevice {
  id: string
  deviceName: string
  keyFingerprint: string
  createdAt: number
  lastUsedAt: number | null
}

export interface PhoneLinkStatus {
  hostId: string
  hostName: string
  hostPublicKey: string
  gatewayUrl: string
  configured: boolean
  ready: boolean
  transportVerifiedAt: number | null
  ownerSignInRequired: boolean
  ownerAuthorizeBaseUrl: string | null
  ownerLoginProviders: { name: string; displayName: string; supportsPassword: boolean }[]
  unavailableReason: 'transport_missing' | 'transport_unverified' | 'owner_sign_in_required' | 'offline' | null
  claims: PhoneLinkClaim[]
  devices: PhoneLinkDevice[]
}

export interface PhoneLinkInvitation {
  pairingId: string
  code: string
  expiresAt: number
  hostId: string
  hostName: string
}

export type PhoneLinkFailureReason =
  'unavailable' | 'unsupported' | 'owner_changed' | 'owner_sign_in_required' | 'refused' | 'invalid_request'

export type PhoneLinkResult<T> =
  { ok: true; owner: PhoneLinkOwner; value: T } | { ok: false; reason: PhoneLinkFailureReason }

export type PhoneLinkMutation =
  | { action: 'create'; owner: PhoneLinkOwner }
  | { action: 'cancel'; owner: PhoneLinkOwner; pairingId: string }
  | { action: 'approve' | 'deny'; owner: PhoneLinkOwner; claim: PhoneLinkClaim }
  | { action: 'revoke'; owner: PhoneLinkOwner; deviceId: string }

export interface PhoneLinksBridge {
  status(): Promise<PhoneLinkResult<PhoneLinkStatus>>
  signInOwner(owner: PhoneLinkOwner, provider: string): Promise<PhoneLinkResult<null>>
  createPairing(owner: PhoneLinkOwner): Promise<PhoneLinkResult<PhoneLinkInvitation>>
  cancelPairing(owner: PhoneLinkOwner, pairingId: string): Promise<PhoneLinkResult<null>>
  approveClaim(owner: PhoneLinkOwner, claim: PhoneLinkClaim): Promise<PhoneLinkResult<null>>
  denyClaim(owner: PhoneLinkOwner, claim: PhoneLinkClaim): Promise<PhoneLinkResult<null>>
  revokeDevice(owner: PhoneLinkOwner, deviceId: string): Promise<PhoneLinkResult<null>>
}
