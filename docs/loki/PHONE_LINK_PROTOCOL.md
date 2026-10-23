# Phone linking v1 implementation contract

Status: implementation in progress. Nothing in this file establishes a deployed
service or phone acceptance. Existing private connectivity stays available while
the new path is built. User request: enter a code to link this iPhone to a computer,
then use it remotely without Tailscale.

## Product contract

Desktop: Settings → Gateway → Phones → Connect an iPhone. Show an expiring grouped
code. Phone: Connect to your computer → enter code → verify computer name/comparison →
wait for approval. Desktop reviews that exact phone/comparison and approves it once.
The phone opens the existing canonical bot roster. Devices can be revoked
individually. The code alone never grants gateway access.

This first version pairs directly with the computer; it does not require inventing a
global Loki account or using Nous hosted-agent discovery. An approved phone has
the existing dashboard's owner-equivalent access to this Loki home and served
profiles. Explain bots, files and tools in the approval. Do not advertise narrower
roles that the gateway does not enforce. Work executes on the awake, online computer.

## Transport and deployment

Keep canonical authenticated HTTPS REST and WSS. Use a stable named outbound
tunnel to an explicitly gated phone ingress, plus a small public rendezvous
service for code lookup. A temporary random tunnel URL is development evidence
only. The initial deployment adapter targets Cloudflare Workers/Durable Objects
for rendezvous and a named Cloudflare Tunnel; account/domain choice is pending.
The protocol does not require a particular DNS vendor.

The app's trusted rendezvous origin comes from build configuration, never from
an untrusted code, redirect or arbitrary incoming link. Actual deployment must
supply it before the pairing UI is considered available. Resolve returns a
stable HTTPS gateway origin, host ID, host name, public signing key and expiry.
No credential from the old Tailscale URL is copied to that origin.

The ingress must refuse all device-management paths and private/native bootstrap
credentials. It must preserve the existing auth gate for REST and WebSocket
upgrades even when the reverse proxy's peer is loopback. Provider keys, private
control tickets and native HTTP grants never leave the computer. The relay/tunnel is
a trusted TLS transport; this slice makes no end-to-end encryption claim.

## Rendezvous routes

- `POST /v1/pairings`: registration authorized with an operator-owned deployment
  secret, never embedded in the phone app. Body: code, pairing_id, gateway_url,
  host_id, host_name, host_public_key and expires_at. Validate bounded fields,
  HTTPS origin, TTL ≤300 seconds and collision atomically. Store only code hash.
- `POST /v1/pairings/resolve`: body `{code}`. Return only the verified registration
  above, excluding code/registration secret. Uniform missing/expired failures;
  rate limits and bounded body/storage. Lookup does not approve or consume a
  gateway claim. No redirects, arbitrary proxying or secret-bearing URL queries.
- Operator cancellation removes that exact pending registration. Expiry removes
  it automatically. New registrations never overwrite another live code.

Eight Crockford base32 characters, displayed `XXXX-XXXX`; five-minute lifetime.
Accept case/space/hyphen formatting only; reject other malformed input. Codes,
claim polling tokens and access credentials must be redacted from logs.

## Desktop management routes

All under `/api/device-links`, requiring the actual OS-local authenticated
`native_http_principal`; IP/Host/Origin or client-provided labels are not authority.
These routes are excluded from public phone ingress:

- `GET /api/device-links`: host/transport readiness, pending claims and approved
  devices with IDs, labels, creation/last-use times. No credentials/private keys.
- `POST /api/device-links/pairings`: create/register one expiring invitation;
  return code, pairing_id, host metadata and expires_at only to local management.
- `DELETE /api/device-links/pairings/{pairing_id}`: cancel that invitation.
- `POST /api/device-links/claims/{claim_id}/approve`: approve exactly the displayed
  claim, key fingerprint and comparison value. Atomic code consumption/grant;
  stale or replaced claims refuse. Bind the server-verified account identity.
- `POST /api/device-links/claims/{claim_id}/deny`: settle the exact claim.
- `DELETE /api/device-links/devices/{device_id}`: revoke one device and its active
  viewer channels, without deleting conversations or affecting another phone.

Approval must preserve a verified existing dashboard account subject for canonical
ownership. Do not alias arbitrary client-supplied provider/user fields, mint a
private-native ticket, silently adopt old receipts, or treat a same email as proof.
If enabling phone access needs initial owner sign-in, use the existing native
browser flow and verify it before issuing an invitation. Keep identity provenance
separate from the paired credential verifier's registration name.

## Public host pairing/authentication routes

These are the only new unauthenticated bootstrap routes. They operate on bounded,
expiring state; normal API requests remain authenticated:

- `POST /auth/device/claims`: pairing_id, code, client_id=`loki-ios`, device_name,
  device_public_key (P-256 X9.63, base64url) and nonce. Require proof of possession
  of that key over the exact canonical claim payload. Return claim_id, opaque
  claim_token, host_id, signed host metadata, comparison and expiry. No bearer yet.
- `POST /auth/device/poll`: claim_id + claim_token; pending/approved/denied/expired.
  An approved result identifies the same device/host, never another endpoint.
- `POST /auth/device/challenge`: approved device_id + host_id; return a single-use,
  short-lived challenge bound to device, host, client and purpose. Unknown devices
  cannot obtain a grant through this route.
- `POST /auth/device/token`: device_id, challenge_id and P-256 signature. Atomically
  consume challenge after validating exact purpose/host/key, issue a short-lived
  gateway bearer with normal verified account identity. No provider key or private
  socket credential. Renewal uses a new signed challenge rather than a reusable
  long-lived refresh secret.

Canonical signed payloads and synthetic JSON examples are frozen in
[the shared wire fixture](phone-link-wire.json). Python and Swift verify the
same claim bytes and raw P-256 signatures; the native test resource mirrors it.
Use CryptoKit and existing Python cryptography support; no home-grown crypto.
Host signing identity is stable and owner-only; the phone pins it from the trusted
registration. Phone private keys stay in device-only Keychain. Secret material is
never Codable application state or preferences.

The paired verifier must not appear as a browser-login choice. Revocation rejects
REST, challenge/token renewal, ticket minting and outstanding ticket upgrades,
and closes existing device viewer channels. An access token's remaining lifetime
does not authorize continued access after revocation. Profile/home binding is
explicit in background/provider callbacks.

## Native lifecycle and verification

Preserve existing gateway URL/account/instance/profile/conversation leases and
durable journals. Pin a stable gateway URL per host; endpoint substitution or an
unexpected redirect refuses before any secret is sent or saved. Cancelling or
replacing pairing prevents late Keychain writes. Keep the same phone key/claim
through a lost reply; after approval, a fresh signed challenge can recover without
creating another device grant. Keychain failure must not report Connected.

First complete isolated contracts for expiry, code collision/rate limits, wrong
host/key/nonce, concurrent claim/redemption, replay, local-only management, endpoint
substitution, cancellation, restart/revocation and existing-device isolation. Then
qualify a real app → public rendezvous → stable tunnel → gateway → canonical
roster/conversation, reconnect and revocation journey with Tailscale disabled on
the test client. Actual phone Wi-Fi/cellular/audio remain separate acceptance.

Deliver the deployed service URL and Desktop readiness check before writing final
remote phone setup instructions. Current TestFlight build 5 cannot pair by code.
