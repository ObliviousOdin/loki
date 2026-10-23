// Audit committed graphs without installing packages or consulting user npm configuration.
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const LOCKFILES = [
  ['root', 'package-lock.json'],
  ['website', 'website/package-lock.json'],
  ['photon', 'plugins/platforms/photon/sidecar/package-lock.json'],
  ['whatsapp', 'scripts/whatsapp-bridge/package-lock.json'],
  ['nix-node-gyp', 'nix/node-gyp-11-4-0-package-lock.json'],
]

const REGISTRY = 'https://registry.npmjs.org'
const LEVELS = ['info', 'low', 'moderate', 'high', 'critical']
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')
const record = (path, value) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`)

export function assessAudit(result) {
  try {
    if (result.error) throw new Error(result.error)
    const report = JSON.parse(result.stdout)
    const counts = report.metadata?.vulnerabilities
    const vulnerabilities = report.vulnerabilities
    if (report.auditReportVersion !== 2 || Object.hasOwn(report, 'error') ||
        !counts || !vulnerabilities || typeof vulnerabilities !== 'object' || Array.isArray(vulnerabilities) ||
        !Number.isInteger(report.metadata?.dependencies?.total) || report.metadata.dependencies.total <= 0) {
      throw new Error('Incomplete npm audit report')
    }
    const levels = LEVELS.map(level => counts[level])
    if (!levels.every(count => Number.isInteger(count) && count >= 0) ||
        counts.total !== levels.reduce((sum, count) => sum + count, 0) ||
        counts.total !== Object.keys(vulnerabilities).length) {
      throw new Error('Inconsistent npm audit vulnerability counts')
    }
    for (const [name, vulnerability] of Object.entries(vulnerabilities)) {
      if (vulnerability.name !== name || !LEVELS.includes(vulnerability.severity) ||
          !Array.isArray(vulnerability.nodes) || !vulnerability.nodes.every(node => typeof node === 'string')) {
        throw new Error('Incomplete npm audit vulnerability entry')
      }
    }
    return { passed: result.status === 0 && counts.total === 0, vulnerabilities: counts, dependencies: report.metadata.dependencies }
  } catch (error) {
    return { passed: false, error: error.message }
  }
}

function executeAudit(cwd, env) {
  const result = spawnSync('npm', [
    'audit', '--package-lock-only', '--ignore-scripts', '--json',
    `--registry=${REGISTRY}`, '--include=dev', '--include=optional', '--include=peer',
  ], { cwd, env, encoding: 'utf8', timeout: 120_000, maxBuffer: 16 * 1024 * 1024 })
  return { status: result.status, stdout: result.stdout ?? '', stderr: result.stderr ?? '', error: result.error?.message }
}

function stageGraph(source, output, lockPath) {
  const raw = readFileSync(join(source, lockPath))
  const lock = JSON.parse(raw)
  const root = lock.packages?.['']
  if (lock.lockfileVersion !== 3 || !root || typeof root !== 'object') {
    throw new Error(`Unsupported or incomplete npm lock: ${lockPath}`)
  }
  mkdirSync(output)
  for (const directory of ['home', 'tmp', 'cache']) mkdirSync(join(output, directory))
  writeFileSync(join(output, 'package-lock.json'), raw)
  // The nonstandard Nix lock has no adjacent package.json. Its root metadata
  // includes both production and dev dependencies and is the audit manifest.
  record(join(output, 'package.json'), root)
  writeFileSync(join(output, 'user.npmrc'), '')
  writeFileSync(join(output, 'global.npmrc'), '')
  const env = {
    PATH: process.env.PATH,
    HOME: join(output, 'home'),
    TMPDIR: join(output, 'tmp'),
    NPM_CONFIG_USERCONFIG: join(output, 'user.npmrc'),
    NPM_CONFIG_GLOBALCONFIG: join(output, 'global.npmrc'),
    NPM_CONFIG_CACHE: join(output, 'cache'),
    NPM_CONFIG_UPDATE_NOTIFIER: 'false',
    NPM_CONFIG_OMIT: '',
  }
  return { env, sourceSha256: sha256(raw) }
}

export function auditLocks(source, output, execute = executeAudit) {
  mkdirSync(output)
  const results = []
  for (const [name, lockPath] of LOCKFILES) {
    const directory = join(output, name)
    let result
    try {
      const prepared = stageGraph(source, directory, lockPath)
      const execution = execute(directory, prepared.env)
      writeFileSync(join(directory, 'stdout.json'), execution.stdout)
      writeFileSync(join(directory, 'stderr.log'), execution.stderr)
      console.log(`::group::npm audit ${name}`)
      console.log(execution.stdout)
      if (execution.stderr) console.error(execution.stderr)
      console.log('::endgroup::')
      result = { name, lockPath, sourceSha256: prepared.sourceSha256, ...execution, ...assessAudit(execution) }
      delete result.stdout
      delete result.stderr
      if (sha256(readFileSync(join(source, lockPath))) !== prepared.sourceSha256 ||
          sha256(readFileSync(join(directory, 'package-lock.json'))) !== prepared.sourceSha256) {
        result.passed = false
        result.error = 'Source or staged lock changed during audit'
      }
    } catch (error) {
      result = { name, lockPath, passed: false, error: error.message }
    }
    record(join(output, `${name}.json`), result)
    console.log(JSON.stringify(result))
    results.push(result)
  }
  const summary = { passed: results.every(result => result.passed), registry: REGISTRY, results }
  record(join(output, 'summary.json'), summary)
  return summary
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 3) throw new Error('Usage: node audit-npm-locks.mjs <new-output-directory>')
  process.exitCode = auditLocks(process.cwd(), resolve(process.argv[2])).passed ? 0 : 1
}
