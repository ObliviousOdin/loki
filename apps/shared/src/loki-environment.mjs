import os from 'node:os'
import path from 'node:path'

/** Bind the public Loki environment once; child runtimes retain their profile scope. */
export function bindLokiEnvironment(env = process.env, home = os.homedir(), platform = process.platform) {
  if (env.__LOKI_ENV_BOUND === '1') return env
  const overrides = Object.entries(env).filter(([key]) => key.startsWith('LOKI_'))
  for (const key of Object.keys(env)) {
    if (key.startsWith('HERMES_') || key.startsWith('__HERMES_')) delete env[key]
  }
  for (const [key, value] of overrides) env[`HERMES_${key.slice(5)}`] = value
  const suffix = env.LOKI_DATA_DIR_SUFFIX || ''
  env.HERMES_HOME = (env.HERMES_HOME || '').trim() || (platform === 'win32'
    ? path.win32.join(env.LOCALAPPDATA || path.win32.join(home, 'AppData', 'Local'), `loki${suffix}`)
    : path.posix.join(home, `.loki${suffix}`))
  env.__LOKI_ENV_BOUND = '1'
  return env
}

