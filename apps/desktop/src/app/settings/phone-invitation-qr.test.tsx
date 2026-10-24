import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'

import { PhoneInvitationQR } from './phone-invitation-qr'

afterEach(cleanup)

it('removes the QR at expiry while keeping generation local and one-shot', async () => {
  const view = render(
    <PhoneInvitationQR code="ABCD-2345" expiresAt={2000000300} label="Invitation QR" now={2000000000} />
  )

  const image = await screen.findByRole('img', { name: 'Invitation QR' })
  expect(image.getAttribute('src')).toMatch(/^data:image\/png;base64,/)
  view.rerender(<PhoneInvitationQR code="ABCD-2345" expiresAt={2000000300} label="Invitation QR" now={2000000300} />)
  expect(screen.queryByRole('img')).toBeNull()
})

it('never presents the previous QR as the replacement invitation', async () => {
  const view = render(
    <PhoneInvitationQR code="ABCD-2345" expiresAt={2000000300} label="Invitation QR" now={2000000000} />
  )

  const before = (await screen.findByRole('img')).getAttribute('src')
  await act(async () => {
    view.rerender(<PhoneInvitationQR code="2345-ABCD" expiresAt={2000000300} label="Invitation QR" now={2000000000} />)
  })
  await waitFor(() => expect(screen.getByRole('img').getAttribute('src')).not.toBe(before))
})
