import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { test } from 'vitest'

import previewIdentity from '../preview-identity.cjs'
import { productIdentity } from './bundle-electron-main.mjs'
import { buildStampPayload, stageDesktopLaunchers } from './write-build-stamp.mjs'

const source = resolve(import.meta.dirname, '../../..')
const commit = 'b'.repeat(40)
const env = {
  LOKI_PREVIEW_PRIMARY: '1', GITHUB_REPOSITORY: 'ObliviousOdin/loki',
  HERMES_DESKTOP_VARIANT: 'bundled', HERMES_BUILD_COMMIT: commit,
  HERMES_PAYLOAD_VERSION: JSON.parse(readFileSync(join(source, 'apps/desktop/package.json'))).version
}
const provenance = { commit, source: 'ci', dirty: false, branch: 'main' }
const runtime = { commands: { hermes: 'bin/loki', 'hermes-agent': 'bin/loki-agent' } }

function configuredIdentity(selectors) {
  return JSON.parse(execFileSync(process.execPath, ['-e', 'console.log(JSON.stringify(require(process.argv[1])))',
    join(source, 'apps/desktop/product-identity.cjs')], { env: selectors, encoding: 'utf8' }))
}

test('primary preview preserves Loki names through packaging, stamp and baked identity', () => {
  const identity = configuredIdentity(env)
  assert.equal(identity.displayName, 'Loki')
  assert.equal(identity.appId, 'com.obliviousodin.loki')
  assert.equal(identity.cliName, 'loki')
  assert.equal(identity.channel, null)
  const stamp = buildStampPayload(provenance, env, 'darwin', { runtime })
  assert.equal(stamp.commit, commit)
  assert.equal(stamp.source, 'commit-build')
  assert.equal(stamp.lokiPreviewPrimary, true)
  assert.equal(stamp.updateMechanism, 'external')
  assert.equal(stamp.tag, null)
  assert.deepEqual(JSON.parse(productIdentity(source, stamp)), identity)

  const root = mkdtempSync(join(tmpdir(), 'loki-preview-launchers-'))
  try {
    mkdirSync(join(root, 'bin'))
    for (const name of ['loki', 'loki-agent']) writeFileSync(join(root, 'bin', name), 'launcher')
    writeFileSync(join(root, 'manifest.json'), JSON.stringify({ target: 'darwin-arm64', runtime }))
    const manifest = stageDesktopLaunchers(root, identity)
    assert.deepEqual(manifest.launchers, ['loki', 'loki-agent'])
    assert.deepEqual(manifest.runtime, runtime)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('primary preview refuses unrelated repositories, variants, versions and release selectors', () => {
  for (const invalid of [
    { LOKI_PREVIEW_PRIMARY: 'true' }, { GITHUB_REPOSITORY: 'NousResearch/hermes-agent' },
    { HERMES_DESKTOP_VARIANT: 'light' }, { HERMES_BUILD_COMMIT: '' },
    { HERMES_PAYLOAD_VERSION: '1.0.0' }, { HERMES_PAYLOAD_TAG: 'v0.1.0-alpha.1' },
    { _HERMES_CHANNEL_REQUEST_JSON: '{}' }
  ]) {
    assert.throws(() => previewIdentity.primaryPreviewEnabled({ ...env, ...invalid }), /owned bundled exact-commit/)
  }
  assert.throws(() => buildStampPayload({ ...provenance, dirty: true }, env, 'darwin', { runtime }), /clean source/)
  assert.throws(() => buildStampPayload({ ...provenance, dirty: undefined }, env, 'darwin', { runtime }), /clean source/)
  assert.throws(() => buildStampPayload({ ...provenance, commit: 'c'.repeat(40) }, env, 'darwin', { runtime }), /stamp commit/)
})

test('baked identity ignores ambient primary selectors and rejects malformed preview stamps', () => {
  const ordinary = buildStampPayload(provenance, { ...env, LOKI_PREVIEW_PRIMARY: '' }, 'darwin', { runtime })
  assert.equal(ordinary.lokiPreviewPrimary, undefined)
  assert.equal(previewIdentity.previewIdentityEnvironment(ordinary, env).LOKI_PREVIEW_PRIMARY, '')
  assert.equal(JSON.parse(productIdentity(source, ordinary)).cliName, 'loki-bbbbbbb')
  const stamp = buildStampPayload(provenance, env, 'darwin', { runtime })
  for (const invalid of [
    { source: 'build' }, { payload: 'bootstrap' }, { dirty: true }, { tag: 'v0.1.0-alpha.1' },
    { channelBuild: {} }, { lokiPreviewPrimary: 'true' }, { commit: 'short' }
  ]) {
    assert.throws(() => productIdentity(source, { ...stamp, ...invalid }), /primary Loki preview|owned bundled exact-commit/)
  }
})
