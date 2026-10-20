import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, test } from 'vitest'
import * as prepared from './prepared-packaging.mjs'
import { validatePreparedBuilderArgs } from './run-electron-builder.mjs'
import { spawnSync } from 'node:child_process'
import { zipSync, strToU8 } from 'fflate'
import { createRequire } from 'node:module'

/** @type {string[]} */
const roots = []
afterEach(() => roots.splice(0).forEach(root => fs.rmSync(root, { recursive: true, force: true })))

/** @returns {{ source: string, out: string, electron: string, sevenZip: string, icons: string }} */
function fixture() {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'prepared-packager-'))
  roots.push(source)
  const out = path.join(source, 'work')
  fs.mkdirSync(path.join(source, 'apps/desktop'), { recursive: true })
  fs.writeFileSync(path.join(source, 'package-lock.json'), '{}')
  fs.writeFileSync(path.join(source, 'apps/desktop/package.json'), '{}')
  fs.writeFileSync(path.join(source, 'apps/desktop/electron-builder.config.cjs'), 'module.exports = {}')
  const electron = path.join(out, 'electron.zip')
  const sevenZip = path.join(out, 'sevenZip')
  const icons = path.join(out, 'icons')
  fs.mkdirSync(path.join(sevenZip, 'bin'), { recursive: true })
  fs.mkdirSync(icons)
  fs.writeFileSync(electron, 'verified archive fixture')
  fs.writeFileSync(path.join(sevenZip, 'bin', process.platform === 'win32' ? '7za.exe' : '7za'), 'archive utility fixture')
  fs.writeFileSync(path.join(icons, 'icon-tool.js'), 'icon tool fixture')
  return { source, out, electron, sevenZip, icons }
}

test('a failed preparation invalidates an earlier completion claim before loading suppliers', () => {
  const { source, out } = fixture()
  const manifest = path.join(out, 'prepared.json')
  fs.writeFileSync(manifest, '{}')
  const result = spawnSync(process.execPath, [path.join(import.meta.dirname, 'prepare-packaging-tools.mjs'),
    '--source', source, '--out', out, '--cache', path.join(source, 'cache')], { encoding: 'utf8' })
  assert.notEqual(result.status, 0)
  assert.equal(fs.existsSync(manifest), false)
  assert.match(result.stderr, /lock|install|pinned/i)
})

test('prepared inputs are path-bound and reject changed or missing bytes without repair', async () => {
  const inputs = fixture()
  const manifest = await prepared.publishPackagingInputs({
    ...inputs, target: 'linux-x64', formats: ['dir'],
    toolsets: { sevenZip: inputs.sevenZip, icons: inputs.icons },
  })
  const result = prepared.readPackagingInputs(manifest, inputs.source, 'linux-x64')
  assert.equal(result.electron, inputs.electron)
  assert.throws(() => validatePreparedBuilderArgs([], result), /run preparation again/)
  assert.throws(() => validatePreparedBuilderArgs(['--dir', '-c.electronDist=/another.zip'], result), /run preparation again/)
  validatePreparedBuilderArgs(['--dir', '-c.extraMetadata.version=1.2.3'], result)
  fs.writeFileSync(inputs.electron, 'corrupt')
  assert.throws(() => prepared.readPackagingInputs(manifest, inputs.source, 'linux-x64'), /run preparation again/i)
  assert.equal(fs.readFileSync(inputs.electron, 'utf8'), 'corrupt')
  fs.rmSync(inputs.electron)
  assert.throws(() => prepared.readPackagingInputs(manifest, inputs.source, 'linux-x64'), /run preparation again/i)
})

test('Electron notices come byte-for-byte from the selected distribution and survive packaged validation', () => {
  const { out, electron } = fixture()
  const expected = { LICENSE: strToU8('Electron target license\r\n'), 'LICENSES.chromium.html': strToU8('<html>Chromium notices: \u03bb</html>\n') }
  fs.writeFileSync(electron, zipSync({ ...expected, 'Electron.app/ignored-resource': strToU8('not a notice') }))
  const appRoot = path.join(out, 'app')
  const staged = path.join(appRoot, 'build/electron-runtime-licenses')
  prepared.stageElectronLicenseNotices(electron, staged)
  assert.deepEqual(fs.readdirSync(staged).sort(), Object.keys(expected).sort())
  for (const [name, bytes] of Object.entries(expected)) assert.deepEqual(fs.readFileSync(path.join(staged, name)), Buffer.from(bytes))
  const config = createRequire(import.meta.url)('../electron-builder.config.cjs')
  const resources = config.extraResources.filter(entry => typeof entry === 'object' && entry.to?.startsWith('licenses/electron/'))
  assert.equal(resources.length, 2, 'the actual builder configuration must retain both vendor notices')
  for (const { from, to } of resources) {
    const destination = path.join(appRoot, 'resources', to)
    fs.mkdirSync(path.dirname(destination), { recursive: true })
    fs.copyFileSync(path.join(appRoot, from), destination)
  }
  const packaged = path.join(appRoot, 'resources/licenses/electron')
  prepared.verifyElectronLicenseNotices(packaged, staged)
  fs.appendFileSync(path.join(packaged, 'LICENSE'), 'changed')
  assert.throws(() => prepared.verifyElectronLicenseNotices(packaged, staged), /differs from the admitted distribution/)
  fs.rmSync(path.join(packaged, 'LICENSE'))
  assert.throws(() => prepared.verifyElectronLicenseNotices(packaged, staged), /Missing Electron distribution notice/)
})

test('the actual native configuration retains both Pilk and codec notices byte-for-byte', () => {
  const { out } = fixture()
  const config = createRequire(import.meta.url)('../electron-builder.config.cjs')
  const app = path.resolve(import.meta.dirname, '..')
  const resources = config.extraResources.filter(entry => entry.to?.startsWith('licenses/pilk/'))
  assert.deepEqual(resources.map(entry => entry.to).sort(), ['licenses/pilk/LICENSE', 'licenses/pilk/SILK-NOTICES.txt'])
  for (const { from, to } of resources) {
    const source = path.resolve(app, from)
    const destination = path.join(out, to)
    fs.mkdirSync(path.dirname(destination), { recursive: true })
    fs.copyFileSync(source, destination)
    assert.deepEqual(fs.readFileSync(destination), fs.readFileSync(source))
    assert.ok(fs.statSync(destination).size > 0)
  }
})

test.each(['missing', 'empty'])('Electron distribution with %s Chromium notice fails before publishing staged notices', kind => {
  const { out, electron } = fixture()
  const contents = { LICENSE: strToU8('Electron license') }
  if (kind === 'empty') contents['LICENSES.chromium.html'] = new Uint8Array()
  fs.writeFileSync(electron, zipSync(contents))
  const staged = path.join(out, 'staged-notices')
  assert.throws(() => prepared.stageElectronLicenseNotices(electron, staged), /Missing Electron distribution notice: LICENSES.chromium.html/)
  assert.equal(fs.existsSync(staged), false, 'an incomplete distribution cannot publish or reuse stale notice bytes')
})
