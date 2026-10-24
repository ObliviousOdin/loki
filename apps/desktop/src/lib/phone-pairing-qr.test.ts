import { describe, expect, it } from 'vitest'

import fixture from '../../../../docs/loki/phone-pairing-qr.json'

import { phonePairingQR } from './phone-pairing-qr'

describe('phone pairing QR invitation', () => {
  it('encodes only the existing short-lived code and expiry, never host or owner data', () => {
    expect(phonePairingQR(fixture, fixture.now)).toBe(fixture.payload)
  })
  it.each([
    { code: 'ABCD-2345', expiresAt: 2000000000 },
    { code: 'ABCD-2345', expiresAt: 2000000301 },
    { code: 'ABCI-2345', expiresAt: 2000000300 },
    { code: 'abcd-2345', expiresAt: 2000000300 },
    { code: 'ABCD-2345\n', expiresAt: 2000000300 },
    { code: 'ABCD-2345\r', expiresAt: 2000000300 },
    { code: 'ABCD-2345&token=secret', expiresAt: 2000000300 },
    { code: 'ABCD-2345', expiresAt: NaN }
  ])('does not render expired, malformed or long-lived invitations: %j', invitation => {
    expect(phonePairingQR(invitation, 2000000000)).toBeNull()
  })
})
