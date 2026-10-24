/** Scanner-only invitation, not a login URL. The phone uses its build-pinned rendezvous. */
export function phonePairingQR(invitation: { code: string; expiresAt: number }, now: number): string | null {
  if (
    !/^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$/.test(invitation.code) ||
    !Number.isSafeInteger(invitation.expiresAt) ||
    !Number.isFinite(now) ||
    invitation.expiresAt <= now ||
    invitation.expiresAt > now + 300
  ) {
    return null
  }

  return `loki://pair?v=1&code=${invitation.code}&expires=${invitation.expiresAt}`
}
