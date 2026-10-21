import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import test from 'node:test'
import { assessAudit, auditLocks, LOCKFILES } from './audit-npm-locks.mjs'

const cleanReport = () => ({
  auditReportVersion: 2,
  vulnerabilities: {},
  metadata: {
    vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 },
    dependencies: { prod: 1, dev: 1, total: 2 },
  },
})
const execution = (report = cleanReport(), status = 0) => ({ status, stdout: JSON.stringify(report), stderr: '' })

test('only a complete, internally consistent, successful npm audit can pass', () => {
  assert.equal(assessAudit(execution()).passed, true)
  const inconsistent = cleanReport()
  inconsistent.metadata.vulnerabilities.total = 1
  const empty = cleanReport()
  empty.metadata.dependencies.total = 0
  const finding = cleanReport()
  finding.metadata.vulnerabilities.low = 1
  finding.metadata.vulnerabilities.total = 1
  finding.vulnerabilities.dep = { name: 'dep', severity: 'low', nodes: ['node_modules/dep'] }
  for (const result of [
    execution({}, 0),
    execution({ error: { code: 'ECONNREFUSED' } }, 0),
    { status: 0, stdout: 'not JSON', stderr: '' },
    execution(cleanReport(), 1),
    execution(cleanReport(), null),
    { ...execution(), error: 'audit process failed' },
    execution(inconsistent),
    execution(empty),
    execution({ ...cleanReport(), vulnerabilities: 1 }),
    execution(finding),
  ]) assert.equal(assessAudit(result).passed, false, JSON.stringify(result))
})

test('every graph retains its lock, dev inputs and result even after an earlier failure', () => {
  const directory = mkdtempSync(join(tmpdir(), 'loki-audit-contract-'))
  const source = join(directory, 'source')
  mkdirSync(source)
  const root = { name: 'owned-audit-fixture', version: '1.0.0', dependencies: { prod: '1.0.0' }, devDependencies: { dev: '1.0.0' } }
  const lock = JSON.stringify({ lockfileVersion: 3, packages: { '': root, 'node_modules/prod': { version: '1.0.0' }, 'node_modules/dev': { version: '1.0.0', dev: true } } })
  try {
    for (const [, path] of LOCKFILES) {
      mkdirSync(dirname(join(source, path)), { recursive: true })
      writeFileSync(join(source, path), lock)
    }
    const seen = []
    const summary = auditLocks(source, join(directory, 'out'), (cwd, env) => {
      seen.push(cwd)
      assert.equal(readFileSync(join(cwd, 'package-lock.json'), 'utf8'), lock)
      assert.deepEqual(JSON.parse(readFileSync(join(cwd, 'package.json'), 'utf8')), root)
      assert.deepEqual(Object.keys(env).sort(), ['HOME', 'NPM_CONFIG_CACHE', 'NPM_CONFIG_GLOBALCONFIG', 'NPM_CONFIG_OMIT', 'NPM_CONFIG_UPDATE_NOTIFIER', 'NPM_CONFIG_USERCONFIG', 'PATH', 'TMPDIR'].sort())
      assert.equal(readFileSync(env.NPM_CONFIG_USERCONFIG, 'utf8'), '')
      if (seen.length === 1) throw new Error('API unavailable')
      if (seen.length === 3) writeFileSync(join(cwd, 'package-lock.json'), `${lock}\n`)
      return execution(cleanReport(), seen.length === 2 ? 1 : 0)
    })
    assert.equal(seen.length, LOCKFILES.length)
    assert.equal(summary.passed, false)
    assert.equal(summary.results[0].error, 'API unavailable')
    assert.equal(summary.results[1].passed, false)
    assert.equal(summary.results[2].passed, false)
    assert.match(summary.results[2].error, /lock changed/)
    assert.equal(summary.results.at(-1).passed, true)
    for (const [name, path] of LOCKFILES) {
      assert.equal(JSON.parse(readFileSync(join(directory, 'out', `${name}.json`), 'utf8')).name, name)
      assert.equal(readFileSync(join(source, path), 'utf8'), lock)
    }
  } finally {
    rmSync(directory, { recursive: true })
  }
})
