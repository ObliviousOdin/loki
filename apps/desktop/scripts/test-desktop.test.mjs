import assert from 'node:assert/strict'
import path from 'node:path'
import { test } from 'vitest'

import { desktopTestApp, isolatedTestEnvironment } from './test-desktop.mjs'

test('packaged harness resolves declared Loki native executable identities', () => {
  const identity = { displayName: 'Loki', windowsExecutableName: 'Loki', artifactNamePascal: 'Loki' }
  const releaseRoot = path.resolve('/sandbox/release')
  const mac = desktopTestApp({ identity, platform: 'darwin', arch: 'arm64', releaseRoot })
  assert.equal(mac.binary, path.join(releaseRoot, 'mac-arm64/Loki.app/Contents/MacOS/Loki'))
  const win = desktopTestApp({ identity, platform: 'win32', arch: 'x64', releaseRoot })
  assert.equal(win.binary, path.join(releaseRoot, 'win-unpacked/Loki.exe'))
  const linux = desktopTestApp({ identity, platform: 'linux', arch: 'x64', releaseRoot })
  assert.equal(linux.binary, path.join(releaseRoot, 'linux-unpacked/Loki'))
})

test('packaged harness starts fresh without credentials or borrowed product activation', () => {
  const inherited = {
    PATH: '/tool/bin', DISPLAY: ':99', OPENAI_API_KEY: 'fixture-secret', openai_api_key: 'lowercase-fixture-secret',
    HERMES_HOME: '/foreign/hermes', LOKI_HOME: '/existing/loki',
    HERMES_RUNTIME_DIR: '/foreign/tools', LOKI_RUNTIME_DIR: '/existing/tools',
    __HERMES_ACTIVATED: 'foreign', __LOKI_ENV_BOUND: '1'
  }
  assert.deepEqual(isolatedTestEnvironment(inherited), { PATH: '/tool/bin', DISPLAY: ':99' })
  assert.equal(inherited.LOKI_HOME, '/existing/loki')
})
