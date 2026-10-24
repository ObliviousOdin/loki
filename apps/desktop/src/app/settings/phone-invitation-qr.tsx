import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

import { phonePairingQR } from '@/lib/phone-pairing-qr'

/** No network QR service: invitation bytes stay in this renderer. */
export function PhoneInvitationQR({
  code,
  expiresAt,
  now,
  label
}: {
  code: string
  expiresAt: number
  now: number
  label: string
}) {
  const payload = phonePairingQR({ code, expiresAt }, now)
  const [image, setImage] = useState<{ payload: string; url: string } | null>(null)
  useEffect(() => {
    let current = true
    setImage(null)

    if (payload) {
      void QRCode.toDataURL(payload, { width: 256, margin: 4, errorCorrectionLevel: 'M' })
        .then(url => {
          if (current) {
            setImage({ payload, url })
          }
        })
        .catch(() => {
          /* The visible manual code remains usable. */
        })
    }

    return () => {
      current = false
    }
  }, [payload])

  return payload && image?.payload === payload ? (
    <img alt={label} className="my-3 rounded bg-white" height={256} src={image.url} width={256} />
  ) : null
}
