import assert from 'node:assert/strict'
import { exec as execCallback } from 'node:child_process'
import { promisify } from 'node:util'

import { test } from 'vitest'

import { locateHermes, probeRemoteHermesHome } from './remote-lifecycle'

const exec = promisify(execCallback)

test('remote automatic discovery never selects an installed foreign Hermes command', async () => {
  const calls: string[] = []

  const ssh = {
    async exec(command: string): Promise<string> {
      calls.push(command)

      if (command.includes('command -v hermes')) {return '/foreign/bin/hermes'}

      if (command.includes('command -v loki')) {return '/owned/bin/loki'}

      return 'OK'
    }
  }

  assert.equal(await locateHermes(ssh, ''), '/owned/bin/loki')
  assert.equal(calls.some(command => command.includes('command -v hermes')), false)
})

test.skipIf(process.platform === 'win32')('remote home shell probe ignores foreign Hermes state', async () => {
  const probe = async (override?: string): Promise<string> => probeRemoteHermesHome({
    async exec(command: string): Promise<string> {
      return (await exec(command, {
        shell: '/bin/sh',
        env: { HOME: '/owned-home', HERMES_HOME: '/foreign-hermes', ...(override ? { LOKI_HOME: override } : {}) }
      })).stdout
    }
  })

  assert.equal(await probe(), '/owned-home/.loki')
  assert.equal(await probe('/owned-profile'), '/owned-profile')
})
