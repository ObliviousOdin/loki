'use strict';

const assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {join,resolve}=require('node:path');
const {spawnSync}=require('node:child_process');
const {test}=require('node:test');
const {mkdtemp,mkdir,writeFile,appendFile,unlink,rm}=require('node:fs/promises');
const {tmpdir}=require('node:os');

const repo=resolve(__dirname,'../../..');
const consumer=createRequire(join(repo,'website/package.json'));
const braces=consumer('braces');
const modulePath=consumer.resolve('braces');

function child(body) {
  const code="const assert=require('node:assert/strict');const braces=require("+JSON.stringify(modulePath)+");"+body;
  const run=spawnSync(process.execPath,['--max-old-space-size=64','-e',code],{
    timeout:3000,encoding:'utf8',env:{PATH:process.env.PATH,TMPDIR:process.env.TMPDIR},
  });
  assert.equal(run.error,undefined,run.error?.message);
  assert.equal(run.status,0,run.stderr||run.stdout);
}

for(const api of ['compile','expand','stringify'])for(const ast of [false,true]) {
  test(api+' processes deep '+(ast?'parsed AST':'string')+' without call-stack recursion',()=>{
    child("const p='{'.repeat(4500)+'x'+'}'.repeat(4500);const input="+(ast?'braces.parse(p)':'p')+";assert.deepEqual(braces."+api+"(input),"+(api==='expand'?'[p]':'p')+");");
  });
}
test('parenthesis nesting is also processed without call-stack recursion',()=>{
  child("const p='('.repeat(4500)+'x'+')'.repeat(4500);assert.equal(braces.compile(p),p);assert.deepEqual(braces.expand(p),[p]);");
});
test('brace alternatives, ranges, literals and filtering remain available',()=>{
  assert.deepEqual(braces.expand('**/*.{md,mdx}'),['**/*.md','**/*.mdx']);
  assert.deepEqual(braces.expand('{a,b}/{1..3}'),['a/1','a/2','a/3','b/1','b/2','b/3']);
  assert.deepEqual(braces.expand('\\{a,b\\}'),['{a,b}']);
  assert.deepEqual(braces.expand('$'+'{a,b}'),['$'+'{a,b}']);
  assert.deepEqual(braces.expand('{a,a,,b}',{nodupes:true,noempty:true}),['a','b']);
  assert.equal(braces.compile('a/{b,c}/d'),'a/(b|c)/d');
  assert.equal(braces.stringify(braces.parse('a/{b,c}/d')),'a/{b,c}/d');
  assert.deepEqual(braces(['{a,b}','{1..2}'],{expand:true}),['a','b','1','2']);
});
test('existing character and range limits still reject oversized inputs',()=>{
  assert.throws(()=>braces.parse('x'.repeat(10001)),{name:'SyntaxError'});
  assert.throws(()=>braces.expand('{1..1001}'),{name:'RangeError'});
  assert.deepEqual(braces.expand('{1..3}',{rangeLimit:4}),['1','2','3']);
});
test('a range transform may shorten its containing AST during traversal',()=>{
  const ast=braces.parse('x{1..2}suffix');
  const result=braces.expand(ast,{transform:n=>{ast.nodes.length=2;return String(n);}});
  assert.deepEqual(result,['x1','x2']);
});
test('expansion uses traversal-owned queues rather than foreign parent metadata',()=>{
  child("const ast=braces.parse('(a/{b,c})');const foreign={type:'paren',queue:['foreign']};foreign.parent=foreign;ast.nodes[1].parent=foreign;assert.deepEqual(braces.expand(ast),['(a/b)','(a/c)']);assert.deepEqual(foreign.queue,['foreign']);");
});
for(const api of ['compile','expand','stringify']) {
  test(api+' refuses cyclic children without an unbounded walk',()=>{
    child("const ast={type:'root',nodes:[]};ast.nodes.push(ast);assert.throws(()=>braces."+api+"(ast),{code:'ERR_BRACES_CYCLE'});");
  });
}
test('nested value arrays cannot turn iterative append into an infinite loop',()=>{
  child("const value=[];value.push(value);const ast={type:'root',nodes:[{type:'text',value}]};assert.throws(()=>braces.expand(ast),{code:'ERR_BRACES_CYCLE'});");
});

test('both affected consumers resolve the same private package',()=>{
  assert.match(consumer('braces/package.json').version,/^3\.0\.3-loki\./);
  for(const parent of ['micromatch','chokidar']) {
    const requireParent=createRequire(consumer.resolve(parent+'/package.json'));
    assert.equal(requireParent.resolve('braces'),modulePath);
  }
});

test('actual build globbing retains brace alternatives and nested discovery',async t=>{
  const root=await mkdtemp(join(tmpdir(),'braces discovery with spaces-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  for(const name of ['docs/guide.md','docs/nested/page.mdx','docs/notes.txt','pages/index.js','pages/nested/view.tsx']) {
    const file=join(root,name);await mkdir(resolve(file,'..'),{recursive:true});await writeFile(file,'fixture');
  }
  const globby=consumer('globby');
  assert.deepEqual(globby.sync(['docs/**/*.{md,mdx}','pages/**/*.{js,jsx,ts,tsx}'],{cwd:root}).sort(),[
    'docs/guide.md','docs/nested/page.mdx','pages/index.js','pages/nested/view.tsx',
  ]);
});

test('actual glob watcher discovers later content and retains change and unlink events',async t=>{
  const root=await mkdtemp(join(tmpdir(),'braces watcher with spaces-'));
  const docs=join(root,'docs');await mkdir(docs);
  const changeFile=join(docs,'change.md'),unlinkFile=join(docs,'unlink.mdx');
  await Promise.all([writeFile(changeFile,'before'),writeFile(unlinkFile,'before')]);
  const watcher=consumer('chokidar').watch(join(docs,'**/*.{md,mdx}'),{ignoreInitial:true});
  t.after(async()=>{await watcher.close();await rm(root,{recursive:true,force:true});});
  const waitFor=(event,path)=>new Promise((resolveEvent,reject)=>{
    const finish=error=>{clearTimeout(timer);watcher.off(event,accept);watcher.off('error',fail);error?reject(error):resolveEvent();};
    const accept=observed=>{if(path===undefined||observed===path)finish();};
    const fail=error=>finish(error);
    const timer=setTimeout(()=>finish(new Error('Missing watcher '+event)),5000);
    watcher.on(event,accept);watcher.on('error',fail);
  });
  await waitFor('ready');
  const directory=join(docs,'nested','notes{literal}');await mkdir(directory,{recursive:true});
  const file=join(directory,'new.mdx');
  const added=waitFor('add',file);await writeFile(file,'first');await added;
  // Chokidar coalesces rapid changes to one path; each operation has its own
  // ready file so this checks discovery and events rather than burst timing.
  const changed=waitFor('change',changeFile);await appendFile(changeFile,' after');await changed;
  const removed=waitFor('unlink',unlinkFile);await unlink(unlinkFile);await removed;
});
