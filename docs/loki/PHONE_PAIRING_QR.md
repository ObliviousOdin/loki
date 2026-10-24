# Phone pairing QR contract

The Desktop Phones settings page renders an existing server-issued invitation locally
with `qrcode`; it does not call an image service or mint another credential.
The scanner-only payload is exactly:

```text
loki://pair?v=1&code=XXXX-XXXX&expires=UNIX_SECONDS
```

`code` is uppercase Crockford Base32 (the existing eight-character invitation).
`expires` is a positive decimal integer with no leading zeros. Both surfaces
reject malformed/expired invitations or expiry more than 300 seconds ahead of
their current clock, matching the gateway's `PAIR_TTL`. A substantially incorrect
phone/computer clock can prevent QR use; manual entry still uses server expiry.
No alternate versions, escaping, extra query fields, fragments, credentials,
gateway addresses, rendezvous overrides, host-local paths or private keys are
accepted. The JSON fixture beside this document is shared with the native Core
fixture; keep them byte-identical when integrating native and public source.

This is **not** a browser login or an OS deep-link registration. Open Loki on
the iPhone, choose pairing, then Scan QR code, or enter the displayed code.
The app only resolves through the trusted rendezvous supplied by its build.
The result still requires the existing host confirmation, signed host metadata,
comparison on both devices, explicit Desktop approval and atomic device-only
Keychain commit. A QR cannot approve itself or select a foreign server.
Server expiry, cancellation, rate limiting, owner/host binding and revocation
remain authoritative; editing the QR's expiry cannot extend the invitation.

Camera access is requested only on explicit Scan. AVFoundation decodes locally;
no frames are saved or uploaded and no microphone/photo-library access is used.
The scanner stops on background/disappearance and consumes only one payload.
Denied permission, missing camera and cancellation leave manual entry available.

## Transport is a separate prerequisite

The rendezvous resolves a code to a gateway origin and public host key; it is
not a traffic relay. QR support does **not** make a Windows or Mac gateway
Internet-reachable. Each computer still needs its own configured, verified,
authenticated HTTPS phone ingress, an approved rendezvous registration and a
running reachable gateway. A working deployment for one computer does not
establish another computer's readiness. Never share another computer's tunnel
credentials; transport provisioning/onboarding is outside this QR change.

## Acceptance boundaries

Automated qualification covers payload validation on both surfaces, locally
rendered Desktop QR retirement/cancellation, native scan lifecycle fencing and
the unchanged explicit pairing approval flow. Simulator builds do not prove
physical camera focus/permission UX or Internet reachability. Before release,
scan the actual Desktop QR on a physical iPhone; test deny/cancel/background,
foreign/malformed/expired/cancelled codes, mismatched comparison and explicit
approval; verify reconnection against the intended computer over mobile data.
Native/TestFlight and public Desktop are separate integration/release paths.
