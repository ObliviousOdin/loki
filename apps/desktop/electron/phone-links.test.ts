import { describe, expect, it, vi } from 'vitest'

import fixture from '../../../docs/loki/phone-link-wire.json'

import type { NativeTokenSet } from './native-oauth'
import type { PhoneLinkClaim, PhoneLinkOwner } from './phone-link-types'
import { createPhoneLinksManager, type PhoneLinkLocalDescriptor, type PhoneLinkManagementDeps } from './phone-links'

const now = 2_000_000_000
const metadata = fixture.host_metadata_decoded
const syntheticAccess = 'unusable-phone-owner-access-token'
const syntheticRefresh = 'unusable-phone-owner-refresh-token'

const account = {
  user_id: fixture.token_response.user_id,
  provider: fixture.token_response.provider,
  issuer: 'fixture-issuer'
}

const tokens: NativeTokenSet = {
  accessToken: syntheticAccess,
  refreshToken: syntheticRefresh,
  expiresAt: now + 900,
  provider: account.provider,
  userId: account.user_id
}

const owner: PhoneLinkOwner = {
  origin: 'http://127.0.0.1:9119',
  instanceId: 'phone-test-instance',
  profileId: '/fixture/loki',
  authorityEpoch: 7
}

function descriptor(): PhoneLinkLocalDescriptor {
  return {
    baseUrl: owner.origin,
    authMode: 'native',
    gatewayEndpoint: {
      api_origin: owner.origin,
      instance_id: owner.instanceId,
      profile_id: owner.profileId,
      authority_epoch: owner.authorityEpoch,
      runtime_protocol: 1,
      supervisor: 'fixture',
      capabilities: ['session-authority-v1']
    }
  }
}

function claimWire() {
  return {
    claim_id: metadata.claim_id,
    pairing_id: metadata.pairing_id,
    device_name: fixture.claim_request.device_name,
    device_public_key: fixture.claim_request.device_public_key,
    key_fingerprint: metadata.key_fingerprint,
    comparison: metadata.comparison,
    expires_at: metadata.expires_at
  }
}

function claim(): PhoneLinkClaim {
  return {
    id: metadata.claim_id,
    pairingId: metadata.pairing_id,
    deviceName: fixture.claim_request.device_name,
    devicePublicKey: fixture.claim_request.device_public_key,
    keyFingerprint: metadata.key_fingerprint,
    comparison: metadata.comparison,
    expiresAt: metadata.expires_at
  }
}

function invitationWire() {
  return {
    pairing_id: metadata.pairing_id,
    code: fixture.claim_request.code,
    expires_at: metadata.expires_at,
    host_id: metadata.host_id,
    host_name: metadata.host_name
  }
}

function overview(verifiedOwner: unknown, overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    configured: true,
    ready: false,
    transport_verified_at: null,
    unavailable_reason: 'transport_unverified',
    owner_sign_in_required: verifiedOwner === null,
    owner: verifiedOwner,
    host: {
      host_id: metadata.host_id,
      host_name: metadata.host_name,
      host_public_key: metadata.host_public_key,
      gateway_url: metadata.gateway_url
    },
    owner_login: {
      authorize_base_url: 'https://dashboard.example.test/loki',
      authorize_path: '/auth/native/authorize',
      token_path: '/auth/native/token',
      providers: [{ name: account.provider, display_name: 'Fixture owner', supports_password: false }]
    },
    claims: [],
    devices: [],
    ...overrides
  }
}

function harness() {
  const state = {
    descriptor: descriptor(),
    verifiedOwner: account as unknown,
    overrides: {} as Record<string, unknown>
  }

  const request = vi.fn<PhoneLinkManagementDeps['request']>().mockImplementation(async (_descriptor, path, options) => {
    if (path === '/api/device-links') {
      return overview(options.bearer === syntheticAccess ? state.verifiedOwner : null, state.overrides)
    }

    if (path === '/api/device-links/pairings' && options.method === 'POST') {
      return invitationWire()
    }

    return { ok: true, access_token: 'synthetic-response-token-must-stay-in-main' }
  })

  const login = vi.fn<PhoneLinkManagementDeps['login']>().mockResolvedValue(tokens)

  const deps: PhoneLinkManagementDeps = {
    withLocal: async operation => operation(state.descriptor),
    request,
    login,
    now: () => now
  }

  return { state, request, login, deps, manager: createPhoneLinksManager(deps) }
}

function mutations(request: ReturnType<typeof harness>['request']) {
  return request.mock.calls.filter(([, , options]) => options.method === 'POST' || options.method === 'DELETE')
}

describe('phone management main-process authority', () => {
  it.each([
    null,
    undefined,
    metadata.gateway_url,
    'http://remote.example.test',
    'http://127.0.0.1:9220',
    'https://user:password@dashboard.example.test',
    'https://dashboard.example.test?query=1',
    'https://dashboard.example.test#fragment',
    'https://dashboard.example.test/\\bad',
    'https://dashboard.example.test/\ninvalid'
  ])('refuses unavailable or unsafe owner authorize base %# before opening a browser', async authorizeBaseUrl => {
    const test = harness()
    test.state.overrides = {
      owner_login: {
        authorize_path: '/auth/native/authorize',
        token_path: '/auth/native/token',
        authorize_base_url: authorizeBaseUrl,
        providers: [{ name: account.provider, display_name: 'Fixture owner' }]
      }
    }
    expect(await test.manager.status()).toMatchObject({
      ok: true,
      value: { ownerAuthorizeBaseUrl: null, ownerLoginProviders: [] }
    })
    expect(await test.manager.signInOwner(owner, account.provider)).toEqual({ ok: false, reason: 'refused' })
    expect(test.login).not.toHaveBeenCalled()
    expect(mutations(test.request)).toEqual([])
  })

  it.each([null, metadata.gateway_url, 'https://dashboard.tailnet.example.test/loki'])(
    'keeps password owner sign-in local despite common OAuth base %#',
    async authorizeBaseUrl => {
      const test = harness()
      test.state.overrides = {
        owner_login: {
          authorize_path: '/auth/native/authorize',
          token_path: '/auth/native/token',
          authorize_base_url: authorizeBaseUrl,
          providers: [{ name: account.provider, display_name: 'Fixture owner', supports_password: true }]
        }
      }
      expect(await test.manager.signInOwner(owner, account.provider)).toEqual({ ok: true, owner, value: null })
      expect(test.login).toHaveBeenCalledExactlyOnceWith(owner.origin, account.provider, owner.origin)
      expect(mutations(test.request)).toEqual([])
    }
  )

  it.each(['remote', 'oauth', 'missing-native-endpoint', 'missing-authority-capability'] as const)(
    'refuses %s before any management request',
    async kind => {
      const test = harness()

      if (kind === 'remote') {
        test.state.descriptor.baseUrl = 'https://remote.example.test'
        test.state.descriptor.gatewayEndpoint!.api_origin = test.state.descriptor.baseUrl
      } else if (kind === 'oauth') {
        test.state.descriptor.authMode = 'oauth'
      } else if (kind === 'missing-authority-capability') {
        test.state.descriptor.gatewayEndpoint!.capabilities = []
      } else {
        delete test.state.descriptor.gatewayEndpoint
      }

      expect(await test.manager.status()).toEqual({ ok: false, reason: 'unavailable' })
      expect(test.request).not.toHaveBeenCalled()
      expect(test.login).not.toHaveBeenCalled()
    }
  )

  it('rejects a different native owner before reading or sending a mutation', async () => {
    const test = harness()
    const old = { ...owner, authorityEpoch: owner.authorityEpoch - 1 }
    expect(await test.manager.revokeDevice(old, 'device_synthetic00001')).toEqual({
      ok: false,
      reason: 'owner_changed'
    })
    expect(test.request).not.toHaveBeenCalled()
    expect(test.login).not.toHaveBeenCalled()
  })

  it.each(['absent', 'different-user', 'different-provider'] as const)(
    'cannot create from an %s verified dashboard account',
    async mismatch => {
      const test = harness()
      test.state.verifiedOwner =
        mismatch === 'absent'
          ? null
          : {
              ...account,
              ...(mismatch === 'different-user' ? { user_id: 'foreign-subject' } : { provider: 'foreign-provider' })
            }
      expect(await test.manager.createPairing(owner)).toEqual({ ok: false, reason: 'owner_sign_in_required' })
      expect(await test.manager.signInOwner(owner, account.provider)).toEqual({ ok: false, reason: 'refused' })
      expect(await test.manager.createPairing(owner)).toEqual({ ok: false, reason: 'owner_sign_in_required' })
      expect(mutations(test.request)).toEqual([])
    }
  )

  it('keeps a verified account bearer in this manager and sends it only on authenticated local requests', async () => {
    const test = harness()
    const initial = await test.manager.status()
    expect(initial).toMatchObject({ ok: true, owner, value: { configured: true, ready: false } })
    expect(test.request.mock.calls.map(([, path]) => path)).toEqual(['/api/device-links'])
    expect(test.login).not.toHaveBeenCalled()
    const signedIn = await test.manager.signInOwner(owner, account.provider)
    expect(signedIn).toEqual({ ok: true, owner, value: null })
    expect(test.login).toHaveBeenCalledExactlyOnceWith(
      owner.origin,
      account.provider,
      'https://dashboard.example.test/loki'
    )
    const status = await test.manager.status()
    expect(status).toMatchObject({ ok: true, value: { configured: true, ready: false, ownerSignInRequired: false } })
    expect(mutations(test.request)).toEqual([])
    const created = await test.manager.createPairing(owner)
    expect(created).toEqual({
      ok: true,
      owner,
      value: {
        pairingId: metadata.pairing_id,
        code: fixture.claim_request.code,
        expiresAt: metadata.expires_at,
        hostId: metadata.host_id,
        hostName: metadata.host_name
      }
    })
    const sent = mutations(test.request)
    expect(sent).toHaveLength(1)
    expect(sent[0]).toEqual([
      test.state.descriptor,
      '/api/device-links/pairings',
      {
        method: 'POST',
        body: {},
        bearer: syntheticAccess
      }
    ])
    expect(test.request.mock.calls.every(([target]) => target === test.state.descriptor)).toBe(true)
    const rendererResults = JSON.stringify([initial, signedIn, status, created])
    expect(rendererResults).not.toContain(syntheticAccess)
    expect(rendererResults).not.toContain(syntheticRefresh)
    expect(JSON.stringify(test.request.mock.calls)).not.toContain(syntheticRefresh)
    const freshManager = createPhoneLinksManager(test.deps)
    expect(await freshManager.createPairing(owner)).toEqual({ ok: false, reason: 'owner_sign_in_required' })
    expect(mutations(test.request)).toHaveLength(1)
  })

  it('does not commit a held account login after the native owner changes', async () => {
    const test = harness()
    let finish!: (value: NativeTokenSet) => void
    test.login.mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve
        })
    )
    const signingIn = test.manager.signInOwner(owner, account.provider)
    await vi.waitFor(() => expect(test.login).toHaveBeenCalledTimes(1))
    test.state.descriptor = descriptor()
    test.state.descriptor.gatewayEndpoint!.instance_id = 'replacement-instance'
    test.state.descriptor.gatewayEndpoint!.authority_epoch = 8
    finish(tokens)
    expect(await signingIn).toEqual({ ok: false, reason: 'owner_changed' })
    const replacement = { ...owner, instanceId: 'replacement-instance', authorityEpoch: 8 }
    expect(await test.manager.createPairing(replacement)).toEqual({ ok: false, reason: 'owner_sign_in_required' })
    expect(mutations(test.request)).toEqual([])
  })

  it('does not publish a held overview from a retired native owner', async () => {
    const test = harness()
    let finish!: (value: unknown) => void
    test.request.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve
        })
    )
    const reading = test.manager.status()
    await vi.waitFor(() => expect(test.request).toHaveBeenCalledTimes(1))
    test.state.descriptor = descriptor()
    test.state.descriptor.gatewayEndpoint!.authority_epoch = 8
    finish(overview(null))
    expect(await reading).toEqual({ ok: false, reason: 'owner_changed' })
    expect(mutations(test.request)).toEqual([])
  })

  it.each(['fingerprint', 'comparison'] as const)('refuses a claim whose %s changed before approval', async field => {
    const test = harness()
    const current = claimWire()

    if (field === 'fingerprint') {
      current.key_fingerprint = 'z'.repeat(43)
    } else {
      current.comparison = '654-321'
    }

    test.state.overrides = { claims: [current] }
    expect(await test.manager.approveClaim(owner, claim())).toEqual({ ok: false, reason: 'refused' })
    expect(mutations(test.request)).toEqual([])
  })

  it('approves only the reviewed claim using the exact fingerprint and comparison body', async () => {
    const test = harness()
    test.state.overrides = { claims: [claimWire()] }
    const result = await test.manager.approveClaim(owner, claim())
    expect(result).toEqual({ ok: true, owner, value: null })
    expect(mutations(test.request)).toEqual([
      [
        test.state.descriptor,
        `/api/device-links/claims/${metadata.claim_id}/approve`,
        {
          method: 'POST',
          body: fixture.local_approve_body
        }
      ]
    ])
    expect(test.login).not.toHaveBeenCalled()
    expect(JSON.stringify(result)).not.toContain('synthetic-response-token-must-stay-in-main')
  })

  it('revokes exactly one selected device with no account token in its body', async () => {
    const test = harness()

    const device = (id: string) => ({
      device_id: id,
      device_name: id,
      key_fingerprint: metadata.key_fingerprint,
      created_at: now - 300,
      last_used_at: null,
      revoked_at: null
    })

    test.state.overrides = { devices: [device('device_synthetic00001'), device('device_synthetic00002')] }
    expect(await test.manager.revokeDevice(owner, 'device_synthetic00002')).toEqual({ ok: true, owner, value: null })
    expect(mutations(test.request)).toEqual([
      [test.state.descriptor, '/api/device-links/devices/device_synthetic00002', { method: 'DELETE' }]
    ])
    expect(test.login).not.toHaveBeenCalled()
  })
})
