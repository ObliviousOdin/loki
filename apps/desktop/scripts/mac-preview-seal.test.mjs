import assert from 'node:assert/strict'
import childProcess from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { MacTargetHelper } from 'app-builder-lib/internal'
import { test, vi } from 'vitest'
import { assertLocalPreviewSealOrder, sealMacPreview } from './mac-preview-seal.mjs'

const require = createRequire(import.meta.url)
const config = require('../electron-builder.config.cjs')
const desktop = path.resolve(import.meta.dirname, '..')

function fixture(real = false) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'loki-local-seal-'))
  const app = path.join(root, 'Loki.app')
  const nested = path.join(app, 'Contents/Frameworks/Local Helper.app')
  const binaries = []
  for (const [bundle, name, id] of [[app, 'Loki', 'com.obliviousodin.loki.seal-fixture'], [nested, 'Local Helper', 'com.obliviousodin.loki.seal-fixture.helper']]) {
    const binary = path.join(bundle, 'Contents/MacOS', name)
    fs.mkdirSync(path.dirname(binary), { recursive: true })
    fs.mkdirSync(path.join(bundle, 'Contents/Resources'), { recursive: true })
    fs.writeFileSync(path.join(bundle, 'Contents/Info.plist'), `<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>${id}</string><key>CFBundleExecutable</key><string>${name}</string><key>CFBundleName</key><string>${name}</string><key>CFBundlePackageType</key><string>APPL</string><key>CFBundleVersion</key><string>1.0.0</string></dict></plist>`)
    if (real) fs.copyFileSync('/usr/bin/true', binary)
    else { const bytes = Buffer.alloc(64); bytes.writeUInt32LE(0xfeedfacf); bytes.writeUInt32LE(0x100000c, 4); fs.writeFileSync(binary, bytes) }
    fs.chmodSync(binary, 0o755)
    binaries.push(binary)
  }
  const packager = {
    config, appInfo: { productFilename: 'Loki', type: 'module' }, info: { framework: {} },
    buildResourcesDir: path.join(desktop, 'build'), resourceList: Promise.resolve([]),
    getResource: async value => path.resolve(desktop, value)
  }
  packager.helper = new MacTargetHelper(packager)
  return { root, app, nested, binaries, context: { appOutDir: root, packager, electronPlatformName: 'darwin' } }
}

test('local preview sealing refuses every configured later mutation and certificate path', () => {
  const packager = { config, info: { framework: {} } }
  assert.doesNotThrow(() => assertLocalPreviewSealOrder(packager))
  for (const patch of [{ electronFuses: {} }, { afterSign: 'late-hook.mjs' }, { afterAllArtifactBuild: 'late-artifact-hook.mjs' }, { mac: { ...config.mac, sign: { identity: 'unexpected certificate' } } }, { mac: { ...config.mac, notarize: true } }, { publish: { provider: 'github' } }]) {
    assert.throws(() => assertLocalPreviewSealOrder({ ...packager, config: { ...config, ...patch } }))
  }
  assert.throws(() => assertLocalPreviewSealOrder({ ...packager, info: { framework: { afterPack() {} } } }))
})

async function observedSeal(f, real) {
  const commands = []
  const original = childProcess.execFile
  vi.stubEnv('CSC_LINK', '/must-not-open/unowned-certificate.p12')
  vi.stubEnv('CSC_NAME', 'must-not-discover-a-certificate')
  const native = vi.spyOn(childProcess, 'execFile').mockImplementation((command, args, options, callback) => {
    assert.equal(command, 'codesign', 'no keychain, provisioning profile, timestamp or signing provider process may run')
    assert.ok(!args.includes('--keychain'))
    commands.push(args)
    if (args.includes('--sign')) {
      assert.equal(args[args.indexOf('--sign') + 1], '-')
      assert.ok(args.includes('--timestamp=none'))
    }
    if (real) return original(command, args, options, callback)
    callback(null, '', '')
    return undefined
  })
  try { await sealMacPreview(f.context) } finally { native.mockRestore(); vi.unstubAllEnvs() }
  assert.equal(commands.filter(args => args.includes('--sign')).at(-1).at(-1), f.app)
  assert.ok(commands.some(args => args.includes('--verify') && args.includes('--deep') && args.includes('--strict')))
  return commands
}

test('official signer seals children before the app without credential/profile discovery or timestamp network access', async () => {
  const f = fixture()
  try {
    const commands = await observedSeal(f, false)
    const targets = commands.filter(args => args.includes('--sign')).map(args => args.at(-1))
    for (const binary of f.binaries) assert.ok(targets.includes(binary))
    assert.ok(targets.includes(f.nested))
  } finally { fs.rmSync(f.root, { recursive: true, force: true }) }
})

test.runIf(process.platform === 'darwin')('real nested macOS bundle passes strict verification with only a local ad-hoc identity', async () => {
  const f = fixture(true)
  try {
    assert.notEqual(childProcess.spawnSync('codesign', ['--verify', '--deep', '--strict', f.app]).status, 0)
    await observedSeal(f, true)
    childProcess.execFileSync('codesign', ['--verify', '--deep', '--strict', f.app])
    const info = childProcess.spawnSync('codesign', ['--display', '--verbose=4', f.app], { encoding: 'utf8' }).stderr
    assert.match(info, /Signature=adhoc/)
    assert.doesNotMatch(info, /Authority=Developer ID/)
    fs.appendFileSync(f.binaries[1], 'changed after sealing')
    assert.notEqual(childProcess.spawnSync('codesign', ['--verify', '--deep', '--strict', f.app]).status, 0, 'native verification must detect later mutations')
  } finally { fs.rmSync(f.root, { recursive: true, force: true }) }
})
