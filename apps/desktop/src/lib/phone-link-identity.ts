import type { PhoneLinkClaim, PhoneLinkOwner } from '../../electron/phone-link-types'

export function samePhoneLinkOwner(a: PhoneLinkOwner, b: PhoneLinkOwner): boolean {
  return (
    a.origin === b.origin &&
    a.instanceId === b.instanceId &&
    a.profileId === b.profileId &&
    a.authorityEpoch === b.authorityEpoch
  )
}

export function samePhoneLinkClaim(a: PhoneLinkClaim, b: PhoneLinkClaim): boolean {
  return (
    a.id === b.id &&
    a.devicePublicKey === b.devicePublicKey &&
    a.keyFingerprint === b.keyFingerprint &&
    a.comparison === b.comparison &&
    a.expiresAt === b.expiresAt
  )
}
