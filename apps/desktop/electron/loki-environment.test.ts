import { bindLokiEnvironment } from '@hermes/shared/loki-environment'
import { describe, expect, it } from 'vitest'

describe('Loki process environment ownership', () => {
  it('starts with owned state and ignores inherited Hermes overrides', () => {
    const env: NodeJS.ProcessEnv = { HERMES_HOME: '/other/hermes', HERMES_SHARED_AUTH_DIR: '/other/auth', PATH: '/bin' }
    bindLokiEnvironment(env, '/fresh-user', 'darwin')
    expect(env.HERMES_HOME).toBe('/fresh-user/.loki')
    expect(env.HERMES_SHARED_AUTH_DIR).toBeUndefined()
    expect(env.PATH).toBe('/bin')
  })

  it('maps explicit Loki settings and preserves a child profile binding', () => {
    const env: NodeJS.ProcessEnv = { LOKI_HOME: '/chosen/loki', LOKI_RUNTIME_DIR: '/chosen/runtime' }
    bindLokiEnvironment(env, '/fresh-user', 'darwin')
    expect(env.HERMES_HOME).toBe('/chosen/loki')
    expect(env.HERMES_RUNTIME_DIR).toBe('/chosen/runtime')
    env.HERMES_HOME = '/chosen/loki/profiles/work'
    bindLokiEnvironment(env, '/fresh-user', 'darwin')
    expect(env.HERMES_HOME).toBe('/chosen/loki/profiles/work')
  })

  it('keeps a preview suffix within Loki-owned platform state', () => {
    const env: NodeJS.ProcessEnv = { LOKI_DATA_DIR_SUFFIX: '-preview', LOCALAPPDATA: 'C:\\Users\\test\\AppData\\Local' }
    bindLokiEnvironment(env, 'C:\\Users\\test', 'win32')
    expect(env.HERMES_HOME).toBe('C:\\Users\\test\\AppData\\Local\\loki-preview')
  })
})
