// Local integrity sealing only. A '-' identity is not Developer ID signing or
// notarization, and must never discover/import a certificate or provisioning profile.
import fs from 'node:fs'
import path from 'node:path'

import { createMacSigner } from './mac-sign.mjs'
import { chromiumRoots, isMachO, repairFrameworkLinks } from './sign-nested-chromium.mjs'

export function assertLocalPreviewSealOrder(packager) {
  const config = packager.config
  if (config.mac?.sign !== null || config.mac?.notarize !== false || config.publish != null || config.mac?.publish != null) {
    throw new Error('Local preview sealing requires certificate signing, notarization and publishing disabled')
  }
  if (config.electronFuses != null || config.afterSign != null || config.afterAllArtifactBuild != null || packager.info.framework?.afterPack != null) {
    throw new Error('Local preview sealing must follow every app mutation; move sealing after the configured later hook')
  }
}

export async function sealMacPreview(context) {
  const { packager, appOutDir } = context
  assertLocalPreviewSealOrder(packager)
  const app = path.join(appOutDir, `${packager.appInfo.productFilename}.app`)
  const payload = path.join(app, 'Contents', 'Resources', 'agent-payload')
  for (const root of chromiumRoots(payload)) repairFrameworkLinks(root)
  const entitlements = path.resolve(import.meta.dirname, '../electron/entitlements.mac.plist')
  const entitlementsInherit = path.resolve(import.meta.dirname, '../electron/entitlements.mac.inherit.plist')
  const sign = createMacSigner({
    entitlements, entitlementsInherit, hardenedRuntime: true, timestamp: 'none',
    ignore: file => !fs.lstatSync(file).isDirectory() && !isMachO(file)
  })
  // Calling osx-sign directly avoids builder27's keychain scan even for '-'.
  // Its normal deepest-first traversal and strict verification remain intact.
  await sign({
    app, platform: 'darwin', type: 'development', identity: '-', identityValidation: false,
    version: packager.config.electronVersion, strictVerify: true,
    preAutoEntitlements: false, preEmbedProvisioningProfile: false
  }, packager)
  console.log('[after-pack] local ad-hoc integrity seal verified; preview is untrusted and not notarized')
}
