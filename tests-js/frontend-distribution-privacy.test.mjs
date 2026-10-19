import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { afterEach, expect, test } from 'vitest'
import { FileMatcher } from 'app-builder-lib/internal'
import { copyDir } from 'builder-util'
import { buildInputs, productCurrent, recordProduct } from '../scripts/build/freshness.mjs'

const require = createRequire(import.meta.url)
const roots = []
afterEach(() => roots.splice(0).forEach(root => rmSync(root, { recursive: true, force: true })))
function put(root, name, data) {
  const file = path.join(root, name)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, data)
  return file
}

test('native distribution omits local freshness paths while source provenance gates remain strict', async () => {
  const root = mkdtempSync(path.join(tmpdir(), 'frontend private build host '))
  roots.push(root)
  const source = path.join(root, 'source')
  const app = path.join(source, 'apps/desktop')
  const out = path.join(app, 'dist')
  const icons = path.join(root, 'private prepared icons')
  put(source, 'package.json', '{"private":true}')
  put(source, 'package-lock.json', '{}')
  put(app, 'package.json', '{"name":"loki-fixture"}')
  put(app, 'src/main.ts', 'export const name = "Loki"')
  put(app, 'assets/NOTICE.txt', 'Retain vendor attribution')
  put(app, 'public/favicon.ico', 'retained favicon')
  put(out, 'electron-main.mjs', 'export const ready = true')
  put(out, 'assets/main.js', 'runtime renderer bytes')
  put(out, 'assets/hermes-build.json', 'public asset with same basename')
  put(icons, 'icon.ico', 'prepared icon bytes')
  const inputs = buildInputs(source, 'desktop', { icons })
  recordProduct({ source, product: 'desktop', out, inputs })
  const receiptPath = path.join(out, 'hermes-build.json')
  const receipt = readFileSync(receiptPath)
  expect(JSON.parse(receipt).inputs.prepared[0].path).toBe(icons)
  expect(productCurrent({ source, product: 'desktop', out })).toBe(true)

  const config = require('../apps/desktop/electron-builder.config.cjs')
  const packaged = path.join(root, 'packaged app')
  const matcher = new FileMatcher(app, packaged, value => value, config.files)
  await copyDir(app, packaged, { filter: matcher.createFilter(), isUseHardLink: () => false })
  expect(existsSync(path.join(packaged, 'dist/hermes-build.json'))).toBe(false)
  expect(readFileSync(path.join(packaged, 'dist/electron-main.mjs'), 'utf8')).toBe('export const ready = true')
  expect(readFileSync(path.join(packaged, 'dist/assets/main.js'), 'utf8')).toBe('runtime renderer bytes')
  expect(readFileSync(path.join(packaged, 'dist/assets/hermes-build.json'), 'utf8')).toBe('public asset with same basename')
  expect(readFileSync(path.join(packaged, 'assets/NOTICE.txt'), 'utf8')).toBe('Retain vendor attribution')
  expect(readFileSync(path.join(packaged, 'public/favicon.ico'), 'utf8')).toBe('retained favicon')
  expect(readFileSync(receiptPath)).toEqual(receipt)
  expect(productCurrent({ source, product: 'desktop', out })).toBe(true)

  put(icons, 'icon.ico', 'tampered icon')
  expect(productCurrent({ source, product: 'desktop', out })).toBe(false)
  put(icons, 'icon.ico', 'prepared icon bytes')
  expect(productCurrent({ source, product: 'desktop', out })).toBe(true)
  put(out, 'assets/main.js', 'tampered renderer')
  expect(productCurrent({ source, product: 'desktop', out })).toBe(false)
})
