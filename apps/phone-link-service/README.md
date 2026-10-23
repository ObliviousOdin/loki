# Loki phone-link rendezvous

This service resolves a short-lived code to a registered computer’s stable HTTPS
gateway and public signing identity. The computer owns approval, credentials and
revocation. The service never forwards chat/voice traffic or authorizes a phone.
Its implementation is not evidence of a deployed service.

Run behavioral checks with Node's built-in test runner:

```sh
node --test apps/phone-link-service/worker.test.mjs
```

Runtime qualification uses pinned `wrangler@4.151.3` outside this workspace's
dependency tree, with anonymous CLI metrics disabled. A local-only synthetic smoke
is included; it refuses public endpoints and uses no real account credentials:

```sh
WRANGLER_SEND_METRICS=false wrangler dev --local --ip 127.0.0.1 --port 52781 \
  --config apps/phone-link-service/wrangler.jsonc \
  --var 'GATEWAY_ORIGINS:https://mac.example.test' \
  --var 'REGISTRATION_TOKEN:synthetic-test-only-registration-secret-0001'
node apps/phone-link-service/runtime-check.mjs http://127.0.0.1:52781
```

This verifies real Worker requests and SQLite-backed Durable Object transactions;
it does not establish Cloudflare account access or a public deployment.

Deploy the included Worker/Durable Object configuration to the selected operator
Cloudflare account only after that account and gateway domain are verified.
Use SQLite-backed Durable Objects, which Cloudflare makes available on its Free
plan; exceeding that plan's limits can make pairing temporarily unavailable.
See [official pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/).
Do not upgrade billing or claim uptime from a local test.

Required deployment bindings:

- `REGISTRATION_TOKEN`: at least 32 characters from a secure random source, set
  through the platform secret workflow. Keep it out of source, URLs and phone
  builds. Only the host-side registration agent and deployment operator receive it.
- `GATEWAY_ORIGINS`: comma-separated exact, owned HTTPS origins accepted for this
  operator's computers. There is no wildcard or default origin. The registration
  token is operator-wide; separate operators require separate service credentials
  or a future authenticated tenant-registration layer.

Registration: authenticated `POST /v1/pairings`; resolution: public rate-limited
`POST /v1/pairings/resolve`; cancellation: authenticated
`DELETE /v1/pairings/{pairing_id}`. See
[wire contract](../../docs/loki/PHONE_LINK_PROTOCOL.md).
The host public key uses unpadded base64url P-256 X9.63; host ID is its SHA-256 hex.
Code registrations are atomic and cannot replace another live code. Exact
registration retry is idempotent. Expired codes return the same missing response.
Stored state contains code hashes and public host metadata, never gateway tokens
or plaintext pairing codes. Responses forbid caching. Default logging is disabled.

The bounded single-object registry is intended for this personal release and
small installations, not unqualified global multi-tenant SaaS. It caps active
pairings and IP rate records; saturation refuses instead of growing storage.
Do not publish a bootstrap/native-control listener as its target. Deploy and
verify an explicitly gated phone ingress plus stable named outbound tunnel first.
