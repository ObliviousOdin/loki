import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import { registerHooks } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

// Node's built-in TS support does not resolve the app's extensionless imports.
// Only supply that extension; import the actual product module unchanged.
registerHooks({
  resolve(specifier, context, next) {
    try {
      return next(specifier, context)
    } catch (error) {
      if (error.code !== 'ERR_MODULE_NOT_FOUND' || !specifier.startsWith('.') || path.extname(specifier)) {
        throw error
      }

      return next(`${specifier}.ts`, context)
    }
  }
})

const lifecycle = await import('./windows-remote-lifecycle.ts')
const shell = process.env.LOKI_TEST_POWERSHELL || (process.platform === 'win32' ? 'powershell.exe' : undefined)
const skip = !shell
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')

function execute(command, args, env, input = '', cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { env, cwd, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
    const stdout = []
    const stderr = []
    const timer = setTimeout(() => child.kill(), 25_000)

    child.stdout.on('data', chunk => stdout.push(chunk))
    child.stderr.on('data', chunk => stderr.push(chunk))
    child.once('error', error => {
      clearTimeout(timer)
      reject(error)
    })
    child.once('close', code => {
      clearTimeout(timer)
      const output = Buffer.concat(stdout).toString('utf8')

      if (code === 0) {
        resolve(output)
      } else {
        reject(new Error(Buffer.concat(stderr).toString('utf8') || `exit ${code}`))
      }
    })
    child.stdin.end(input)
  })
}

async function fixture(nativeInputEncoding = '') {
  const root = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'loki-remote-'))
  const home = path.join(root, 'home with spaces')
  const local = path.join(home, 'AppData', 'Local')
  const state = path.join(local, 'loki')
  const env = { ...process.env }

  for (const key of Object.keys(env)) {
    if (/^(?:HERMES_|LOKI_|__HERMES_|__LOKI_)/i.test(key) || /^path$/i.test(key)) {
      delete env[key]
    }
  }

  await fs.mkdir(state, { recursive: true })
  Object.assign(env, { HOME: home, USERPROFILE: home, LOCALAPPDATA: local, PROCESSOR_ARCHITECTURE: process.env.PROCESSOR_ARCHITECTURE || process.arch })
  env.PATH = process.platform === 'win32'
    ? [path.join(process.env.SystemRoot, 'System32'), path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0'), path.join(process.env.ProgramFiles, 'PowerShell', '7')].join(path.delimiter)
    : '/usr/bin:/bin:/usr/sbin:/sbin'
  const ssh = {
    async exec(command, options = {}) {
      const encoded = command.match(/-EncodedCommand\s+(\S+)$/)?.[1]
      const policy = nativeInputEncoding === 'ASCII'
        ? '$OutputEncoding=[Text.Encoding]::ASCII;'
        : nativeInputEncoding === 'UTF8' ? '$OutputEncoding=[Text.UTF8Encoding]::new($false);' : ''
      const configured = encoded && policy ? Buffer.from(policy + Buffer.from(encoded, 'base64').toString('utf16le'), 'utf16le').toString('base64') : encoded

      return configured
        ? execute(shell, ['-NoProfile', '-NonInteractive', '-EncodedCommand', configured], env, '', root)
        : execute(shell, ['-NoProfile', '-NonInteractive', '-Command', `${policy}[ScriptBlock]::Create([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd()))).Invoke()`], env, options.stdinData, root)
    }
  }

  return { root, home, local, state, env, ssh, async close() { await fs.rm(root, { recursive: true, force: true }) } }
}

async function launcher(directory, f) {
  await fs.mkdir(directory, { recursive: true })

  // Use the real publisher: Windows produces its PE/command-file launcher.
  const python = process.env.HERMES_PYTHON || process.env.LOKI_TEST_PYTHON ||
    (await execute('python', ['-I', '-c', 'import sys;print(sys.executable)'], process.env)).trim()
  const code = 'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from hermes_cli._launchers import mint_launcher;p=mint_launcher("loki",Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.executable).resolve(),None);assert p;print(p)'
  const published = (await execute(python, ['-I', '-c', code, repo, directory], f.env)).trim()

  if (process.platform === 'win32') {
    return published
  }

  // On macOS this remains a POSIX launcher: portable PowerShell proof, not PE.
  const target = path.join(directory, 'loki.exe')

  await fs.copyFile(published, target)
  await fs.chmod(target, 0o755)

  return target
}

test('remote probe discovers the public Loki bin without an adjacent Python or foreign state', { skip }, async () => {
  const f = await fixture()

  try {
    const installed = await launcher(path.join(f.state, 'bin'), f)
    const foreign = path.join(f.local, 'hermes')

    await fs.mkdir(foreign)
    await fs.writeFile(path.join(foreign, 'canary'), 'foreign home unchanged')
    f.env.HERMES_HOME = foreign
    const result = await lifecycle.probeWindowsRemote(f.ssh)

    assert.equal(result.hermesPath, installed)
    assert.equal(result.hermesHome, f.state)
    assert.equal(await fs.readFile(path.join(foreign, 'canary'), 'utf8'), 'foreign home unchanged')
    await assert.rejects(fs.stat(path.join(path.dirname(installed), 'python.exe')), { code: 'ENOENT' })
  } finally {
    await f.close()
  }
})

test('remote probe discovers the checkout-local Loki launcher for a custom public home', { skip }, async () => {
  const f = await fixture()

  try {
    const custom = path.join(f.root, 'custom Loki home')
    const installed = await launcher(path.join(custom, 'hermes-agent', '.loki', 'bin'), f)

    f.env.LOKI_HOME = custom
    const result = await lifecycle.probeWindowsRemote(f.ssh)

    assert.equal(result.hermesPath, installed)
    assert.equal(result.hermesHome, custom)
  } finally {
    await f.close()
  }
})

test('remote probe uses the Loki command on PATH', { skip }, async () => {
  const f = await fixture()

  try {
    const directory = path.join(f.root, 'commands')
    const installed = await launcher(directory, f)

    f.env.PATH = `${directory}${path.delimiter}${f.env.PATH || ''}`
    const result = await lifecycle.probeWindowsRemote(f.ssh)

    assert.equal(result.hermesPath, installed)
  } finally {
    await f.close()
  }
})

test('remote runtime uses the published launcher bootstrap instead of adjacent Python', { skip }, async () => {
  const f = await fixture()

  try {
    const installed = await launcher(path.join(f.state, 'bin'), f)
    const selected = await lifecycle.probeWindowsRemote(f.ssh)
    const runtime = await lifecycle.resolveWindowsRemoteRuntime(f.ssh, selected)

    assert.equal(runtime.hermesPath, installed)
    assert.equal(path.isAbsolute(runtime.python), true)
    assert.notEqual(path.dirname(runtime.python), path.dirname(installed))
  } finally {
    await f.close()
  }
})

for (const encoding of ['UTF8', 'ASCII']) {
  test(`atomic spawn preserves JSON and ownership over ${encoding} native input within cmd limits`, { skip }, async t => {
    const f = await fixture(encoding)

    try {
      const python = process.env.HERMES_PYTHON || process.env.LOKI_TEST_PYTHON ||
        (await execute('python', ['-I', '-c', 'import sys;print(sys.executable)'], process.env)).trim()
      const packageDir = path.join(f.root, 'hermes_cli')
      const state = path.join(f.state, '한글😀')

      await fs.mkdir(state)

      await fs.mkdir(packageDir)
      await fs.writeFile(path.join(packageDir, '__init__.py'), '')
      await fs.writeFile(path.join(packageDir, 'windows_ssh_runtime.py'), [
        'import json,sys',
        'from pathlib import Path',
        'operation=sys.argv[1]',
        'if operation == "read-lock": sys.exit(1)',
        'payload=json.load(sys.stdin)',
        'if operation == "write-lock":',
        '    Path("lock.json").write_text(json.dumps(payload),encoding="utf-8")',
        '    sys.exit(0)',
        'assert operation == "spawn"',
        'Path("payload.json").write_text(json.dumps(payload),encoding="utf-8")',
        'print(json.dumps({"pid":4242,"creationTimeNs":"1234567890"}))'
      ].join('\n'))
      const payload = { ownershipId: 'fixture-owner', spawnNonce: 'fixture-nonce', profile: "o'neil\n한글😀", hermesPath: "C:\\Users\\O'Neil\\한글\\loki.exe" }
      const calls = []
      const ssh = { exec(command, options) { calls.push({ command, options }); return f.ssh.exec(command, options) } }
      const reservation = { ...payload, hermesHome: state, tokenFingerprint: 'a'.repeat(32), startedAt: '2026-10-19T00:00:00.000Z' }
      const result = await lifecycle.atomicWindowsSpawn(ssh, { python, hermesHome: state }, JSON.stringify(payload), reservation)

      assert.equal(result.pid, 4242)
      assert.equal(calls.length, 1)
      assert.ok(calls[0].command.length < 8191)
      assert.equal(calls[0].command, lifecycle.powerShellStdinCommand())
      assert.ok(calls[0].options.stdinData.trim().length > 8191)
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(f.root, 'payload.json'), 'utf8')), payload)
      const lock = JSON.parse(await fs.readFile(path.join(f.root, 'lock.json'), 'utf8'))

      assert.deepEqual(lock, { ...reservation, schemaVersion: 2, protocolVersion: 1, pid: 4242, creationTimeNs: '1234567890', port: 0 })
      t.diagnostic(JSON.stringify({ commandCharacters: calls[0].command.length, encodedScriptCharacters: calls[0].options.stdinData.trim().length, jsonAndOwnershipRecordPreserved: true }))
    } finally {
      await f.close()
    }
  })
}


test('remote probe honors an explicit launcher without adjacent Python', { skip }, async () => {
  const f = await fixture()

  try {
    const installed = await launcher(path.join(f.root, 'explicit commands'), f)
    const result = await lifecycle.probeWindowsRemote(f.ssh, installed)

    assert.equal(result.hermesPath, installed)
    assert.equal(result.hermesHome, f.state)
  } finally {
    await f.close()
  }
})

test('a foreign Hermes install alone is not discovered or changed', { skip }, async () => {
  const f = await fixture()

  try {
    const foreign = path.join(f.local, 'hermes')
    const bin = path.join(foreign, 'hermes-agent', 'venv', 'Scripts')

    await fs.mkdir(bin, { recursive: true })
    await fs.writeFile(path.join(bin, 'hermes.exe'), 'foreign executable bytes')
    f.env.HERMES_HOME = foreign
    await assert.rejects(lifecycle.probeWindowsRemote(f.ssh), /Loki is not installed/)
    assert.equal(await fs.readFile(path.join(bin, 'hermes.exe'), 'utf8'), 'foreign executable bytes')
  } finally {
    await f.close()
  }
})

test('remote probe rejects a linked launcher directory', { skip }, async () => {
  const f = await fixture()

  try {
    const target = path.join(f.root, 'actual commands')

    await launcher(target, f)
    await fs.symlink(target, path.join(f.state, 'bin'), process.platform === 'win32' ? 'junction' : 'dir')
    await assert.rejects(lifecycle.probeWindowsRemote(f.ssh), /link or reparse point/)
  } finally {
    await f.close()
  }
})

async function runtimeFixture(f, checkout) {
  const python = process.env.HERMES_PYTHON || process.env.LOKI_TEST_PYTHON ||
    (await execute('python', ['-I', '-c', 'import sys;print(sys.executable)'], process.env)).trim()
  const bin = path.join(checkout, '.loki', 'bin')
  const command = path.join(bin, 'loki.cmd')

  await fs.mkdir(bin, { recursive: true })
  await fs.writeFile(path.join(f.root, 'fixture_runtime.py'), [
    'import json,sys',
    'from pathlib import Path',
    'Path("runtime-called.json").write_text(json.dumps(sys.argv[1:]))',
    'assert sys.argv[1:] == ["--run-module","hermes_cli.windows_ssh_runtime","spawn"]',
    'json.loads(sys.stdin.buffer.read())',
    'print(json.dumps({"pid":4242,"creationTimeNs":"1234567890"}))'
  ].join('\n'))
  // A real command-file fixture, not a PowerShell script named as an exe.
  const quoted = process.platform === 'win32' ? `"${python}"` : `'${python.replace(/'/g, "'\\''")}'`

  await fs.writeFile(command, process.platform === 'win32'
    ? `@echo off\r\n${quoted} -m fixture_runtime %*\r\n`
    : `#!/bin/sh\nexec ${quoted} -m fixture_runtime "$@"\n`)
  await fs.chmod(command, 0o755)

  return { python, hermesPath: command, hermesHome: f.state }
}

async function holdCheckoutLock(f, checkout) {
  const git = path.join(checkout, '.git')

  await fs.mkdir(git, { recursive: true })
  const script = `$f=[IO.File]::Open(${lifecycle.psLiteral(path.join(git, 'hermes-update.lock'))},'OpenOrCreate','ReadWrite','ReadWrite');$f.Lock(1048576,17);try{Write-Output 'held';[Console]::Out.Flush();Start-Sleep -Seconds 25}finally{$f.Unlock(1048576,17);$f.Dispose()}`
  const child = spawn(shell, ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { env: f.env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
  const closed = new Promise(resolve => child.once('close', resolve))

  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('fixture checkout lock did not start')), 10_000)

      child.once('error', error => { clearTimeout(timer); reject(error) })
      child.once('close', code => { clearTimeout(timer); reject(new Error(`fixture checkout lock exited ${code}`)) })
      child.stdout.once('data', chunk => {
        clearTimeout(timer)
        if (String(chunk).includes('held')) resolve()
        else reject(new Error('fixture checkout lock did not report held'))
      })
    })
  } catch (error) {
    child.kill()
    await closed
    throw error
  }

  return async () => { child.kill(); await closed }
}

for (const policy of ['held-checkout', 'unknown-public-bin', 'dead-checkout']) {
  test(`pending update topology ${policy} preserves the checkout ownership boundary`, { skip }, async () => {
    const f = await fixture()
    let release = async () => {}

    try {
      const checkout = path.join(f.root, 'custom checkout')
      const runtime = await runtimeFixture(f, checkout)
      const marker = path.join(f.state, '.hermes-update-in-progress')
      const claim = '0\n0\n'

      if (policy === 'unknown-public-bin') {
        const publicBin = path.join(f.state, 'bin')
        const publicCommand = path.join(publicBin, 'loki.cmd')

        await fs.mkdir(publicBin)
        await fs.copyFile(runtime.hermesPath, publicCommand)
        await fs.chmod(publicCommand, 0o755)
        runtime.hermesPath = publicCommand
      }
      if (policy === 'held-checkout') release = await holdCheckoutLock(f, checkout)
      await fs.writeFile(marker, claim)
      if (policy === 'dead-checkout') {
        const result = await lifecycle.atomicWindowsSpawn(f.ssh, runtime, '{}')

        assert.equal(result.pid, 4242)
        await assert.rejects(fs.stat(marker), { code: 'ENOENT' })
        assert.deepEqual(JSON.parse(await fs.readFile(path.join(f.root, 'runtime-called.json'), 'utf8')), ['--run-module', 'hermes_cli.windows_ssh_runtime', 'spawn'])
      } else {
        if (process.platform === 'win32') {
          let calls = 0
          const ssh = { exec(command, options) { calls++; return f.ssh.exec(command, options) } }

          await assert.rejects(lifecycle.resolveWindowsRemoteRuntime(ssh, runtime), error => error.kind === 'update-in-progress')
          assert.equal(calls, 1, 'the pending marker must refuse before the launcher query')
        }
        await assert.rejects(lifecycle.atomicWindowsSpawn(f.ssh, runtime, '{}'), policy === 'held-checkout' ? /HELD/ : /UNCERTAIN/)
        assert.equal(await fs.readFile(marker, 'utf8'), claim)
        await assert.rejects(fs.stat(path.join(f.root, 'runtime-called.json')), { code: 'ENOENT' })
      }
    } finally {
      await release()
      await f.close()
    }
  })
}

test('an uncertain install marker prevents executing the runtime query', { skip }, async () => {
  const f = await fixture()

  try {
    await launcher(path.join(f.state, 'bin'), f)
    const selected = await lifecycle.probeWindowsRemote(f.ssh)
    const marker = path.join(f.state, '.hermes-update-in-progress')
    const original = 'not a valid update claim\n'

    await fs.writeFile(marker, original)
    let calls = 0
    const ssh = { exec(command, options) { calls++; return f.ssh.exec(command, options) } }

    await assert.rejects(lifecycle.resolveWindowsRemoteRuntime(ssh, selected), error => error.kind === 'update-in-progress')
    assert.equal(calls, 1)
    assert.equal(await fs.readFile(marker, 'utf8'), original)
  } finally {
    await f.close()
  }
})
