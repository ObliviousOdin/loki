import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {chmodSync, cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import {fileURLToPath} from 'node:url';

const source = process.env.NPM_SOURCE_ROOT;
const deps = process.env.NPM_DEPS_ROOT;
const json = path => JSON.parse(readFileSync(path, 'utf8'));

test('offline dependency resolution retains the admitted local archive bytes', () => {
  const original = json(join(source, 'package-lock.json')).packages['node_modules/htmlparser2'];
  const offline = json(join(deps, 'package-lock.json')).packages['node_modules/htmlparser2'];
  const manifest = json(join(deps, 'package.json'));
  const expected = readFileSync(join(source, original.resolved.slice('file:'.length)));
  assert.equal(offline.version, original.version);
  assert.equal(offline.link, undefined);
  assert.equal(manifest.devDependencies.htmlparser2, offline.resolved);
  const selected = readFileSync(fileURLToPath(offline.resolved));
  assert.deepEqual(selected, expected);
  const integrity = 'sha512-' + createHash('sha512').update(selected).digest('base64');
  assert.equal(integrity, original.integrity);
  assert.equal(offline.integrity, original.integrity);
});

test('filtered build inputs retain corresponding source and refuse archive tampering', () => {
  const guard = ['vendor/htmlparser2/archive.mjs', '--check'];
  const valid = spawnSync(process.execPath, guard, {cwd: source, encoding: 'utf8'});
  assert.equal(valid.status, 0, valid.stderr);
  const temporary = mkdtempSync(join(tmpdir(), 'loki-nix-archive-'));
  try {
    const root = join(temporary, 'workspace');
    cpSync(join(source, 'vendor/htmlparser2'), join(root, 'vendor/htmlparser2'), {recursive: true});
    for (const name of ['package.json', 'package-lock.json']) {
      writeFileSync(join(root, name), readFileSync(join(source, name)));
    }
    const entry = json(join(root, 'package-lock.json')).packages['node_modules/htmlparser2'];
    const archive = join(root, entry.resolved.slice('file:'.length));
    chmodSync(archive, 0o600);
    writeFileSync(archive, Buffer.concat([readFileSync(archive), Buffer.from('tampered')]));
    const rejected = spawnSync(process.execPath, guard, {cwd: root, encoding: 'utf8'});
    assert.notEqual(rejected.status, 0);
    assert.match(rejected.stderr, /Archive differs from deterministic corresponding source/);
  } finally {
    rmSync(temporary, {recursive: true, force: true});
  }
});
