'use strict';

const assert=require('node:assert/strict');
const {cpSync,mkdirSync,mkdtempSync,readFileSync,rmSync,symlinkSync,unlinkSync,writeFileSync,chmodSync,utimesSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve}=require('node:path');
const {spawnSync}=require('node:child_process');
const {afterEach,test}=require('node:test');

const vendor=resolve(__dirname,'..'),repo=resolve(vendor,'../..');
const metadata=JSON.parse(readFileSync(join(vendor,'package.json')));
const archive='braces-'+metadata.version+'.tgz';
const temporary=[];
afterEach(()=>{for(const path of temporary.splice(0))rmSync(path,{recursive:true,force:true});});

function fixture(includeArchive=true) {
  const root=mkdtempSync(join(tmpdir(),'braces package with spaces-'));temporary.push(root);
  const copy=join(root,'vendor/braces');mkdirSync(copy,{recursive:true});mkdirSync(join(root,'website'));
  for(const file of ['index.js','lib','LICENSE','README.md','UPSTREAM.json','FORK.md','package.json','archive.mjs',...(includeArchive?[archive]:[])])cpSync(join(vendor,file),join(copy,file),{recursive:true});
  for(const file of ['package.json','package-lock.json'])cpSync(join(repo,'website',file),join(root,'website',file));
  return {root,copy};
}
function run(root,mode='--check') {
  return spawnSync(process.execPath,[join(root,'vendor/braces/archive.mjs'),mode],{encoding:'utf8',timeout:10000});
}
test('actual installed consumer bytes match the source, archive and lock',()=>{
  const result=run(repo,'--check-installed');
  assert.equal(result.status,0,result.stderr);
});
test('regeneration is identical in another path with different file metadata',()=>{
  const {root,copy}=fixture(false);
  chmodSync(join(copy,'index.js'),0o755);utimesSync(join(copy,'index.js'),1,1);
  const result=run(root,'--write');
  assert.equal(result.status,0,result.stderr);
  assert.deepEqual(readFileSync(join(copy,archive)),readFileSync(join(vendor,archive)));
  assert.equal(run(root).status,0);
});
test('changed archive bytes are refused even when cached npm package bytes are correct',()=>{
  const {root,copy}=fixture();const bytes=readFileSync(join(copy,archive));bytes[4]^=1;writeFileSync(join(copy,archive),bytes);
  const result=run(root);
  assert.notEqual(result.status,0);assert.match(result.stderr,/Archive bytes differ/);
});
test('stale archive after a source edit is refused',()=>{
  const {root,copy}=fixture();const file=join(copy,'lib/compile.js');writeFileSync(file,readFileSync(file,'utf8')+'\n// changed source\n');
  const result=run(root);
  assert.notEqual(result.status,0);assert.match(result.stderr,/Archive bytes differ/);
});
test('lock integrity and source symlinks are independently refused',()=>{
  const first=fixture();const lockPath=join(first.root,'website/package-lock.json');const lock=JSON.parse(readFileSync(lockPath));
  lock.packages['node_modules/braces'].integrity='sha512-invalid';writeFileSync(lockPath,JSON.stringify(lock));
  assert.match(run(first.root).stderr,/Archive integrity differs/);
  const second=fixture();unlinkSync(join(second.copy,'index.js'));symlinkSync(join(vendor,'index.js'),join(second.copy,'index.js'));
  assert.match(run(second.root).stderr,/Nonregular package input/);
});
