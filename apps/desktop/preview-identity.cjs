// Build-only opt-in for the primary Loki preview. Exact source custody stays
// with the upstream commit builder; this selects names, never update authority.
// @ts-check
/// <reference types="node" />
'use strict'

const { version } = require('./package.json')
const repository = 'ObliviousOdin/loki'

/** @param {NodeJS.ProcessEnv} env */
function primaryPreviewEnabled(env = process.env) {
  if (!env.LOKI_PREVIEW_PRIMARY) return false
  if (env.LOKI_PREVIEW_PRIMARY !== '1' || env.GITHUB_REPOSITORY !== repository ||
      env.HERMES_DESKTOP_VARIANT !== 'bundled' || !/^[a-f0-9]{40}$/.test(env.HERMES_BUILD_COMMIT || '') ||
      env.HERMES_PAYLOAD_VERSION !== version || !/^\d+\.\d+\.\d+-(?:alpha|beta|rc)\.\d+$/.test(version) ||
      env.HERMES_PAYLOAD_TAG || env._HERMES_CHANNEL_REQUEST_JSON) {
    throw new Error('Primary Loki preview identity requires an owned bundled exact-commit preview build')
  }
  return true
}

/** Reconstruct build selectors solely from the immutable, validated stamp.
 * @param {{lokiPreviewPrimary?: unknown, source?: string, payload?: string, dirty?: boolean, tag?: unknown, channelBuild?: unknown, commit?: string}} stamp
 * @param {NodeJS.ProcessEnv} env
 */
function previewIdentityEnvironment(stamp, env = process.env) {
  const selected = { ...env, LOKI_PREVIEW_PRIMARY: '' }
  if (stamp.lokiPreviewPrimary === undefined) return selected
  if (stamp.lokiPreviewPrimary !== true || stamp.source !== 'commit-build' || stamp.payload !== 'bundled' ||
      stamp.dirty !== false || stamp.tag || stamp.channelBuild) {
    throw new Error('Invalid primary Loki preview stamp')
  }
  Object.assign(selected, {
    LOKI_PREVIEW_PRIMARY: '1', GITHUB_REPOSITORY: repository,
    HERMES_DESKTOP_VARIANT: 'bundled', HERMES_BUILD_COMMIT: stamp.commit,
    HERMES_PAYLOAD_VERSION: version, HERMES_PAYLOAD_TAG: '', _HERMES_CHANNEL_REQUEST_JSON: ''
  })
  primaryPreviewEnabled(selected)
  return selected
}

module.exports = { primaryPreviewEnabled, previewIdentityEnvironment }
