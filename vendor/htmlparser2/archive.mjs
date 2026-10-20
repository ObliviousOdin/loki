import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {lstatSync, readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {deflateRawSync} from 'node:zlib';

const here=dirname(fileURLToPath(import.meta.url));
const digest=(bytes,algorithm='sha256')=>createHash(algorithm).update(bytes).digest('hex');
const sri=bytes=>'sha512-'+createHash('sha512').update(bytes).digest('base64');
const originalGuard='if (c === CharCodes.OpeningSquareBracket) {';
const patchedGuard='if (c === CharCodes.OpeningSquareBracket && (this.xmlMode || this.recognizeCDATA || this.cbs.isInForeignContext?.())) {';

function restoreTokenizer(name,bytes) {
  let text=bytes.toString('utf8');
  const changes=name==='src/Tokenizer.ts'?[
    ['    private readonly recognizeCDATA: boolean;\n',''],
    ['            recognizeCDATA = xmlMode,\n',''],
    ['            recognizeCDATA?: boolean;\n',''],
    ['        this.recognizeCDATA = recognizeCDATA;\n',''],
    [patchedGuard,originalGuard],
  ]:name==='dist/Tokenizer.js'?[
    ['    recognizeCDATA;\n',''],
    ['recognizeSelfClosing = xmlMode, recognizeCDATA = xmlMode,','recognizeSelfClosing = xmlMode,'],
    ['        this.recognizeCDATA = recognizeCDATA;\n',''],
    [patchedGuard,originalGuard],
  ]:[
    ['    private readonly recognizeCDATA;\n',''],
    ['recognizeSelfClosing, recognizeCDATA,','recognizeSelfClosing,'],
    ['        recognizeCDATA?: boolean;\n',''],
  ];
  for(const [patched,original] of changes) {
    assert.equal(text.split(patched).length,2,'Unexpected tokenizer option/guard patch: '+name);
    text=text.replace(patched,original);
  }
  return Buffer.from(text);
}

function regular(root,name) {
  assert(!name.startsWith('/')&&!name.split('/').includes('..'),'Invalid package input');
  const parts=name.split('/');
  for(let index=1;index<parts.length;index++) {
    const directory=lstatSync(join(root,...parts.slice(0,index)));
    assert(directory.isDirectory()&&!directory.isSymbolicLink(),'Nonregular package directory');
  }
  const file=join(root,name),info=lstatSync(file);
  assert(info.isFile()&&!info.isSymbolicLink()&&info.size<1024*1024,'Nonregular or oversized package input: '+name);
  return readFileSync(file);
}

function packageNames(root) {
  const provenance=JSON.parse(regular(root,'UPSTREAM.json'));
  const names=Object.keys(provenance.upstream_file_sha256).sort();
  assert.equal(names.length,28,'Unexpected upstream package file set');
  for(const name of names) {
    const bytes=regular(root,name);
    if(name==='package.json')continue;
    if(['src/Tokenizer.ts','dist/Tokenizer.js','dist/Tokenizer.d.ts'].includes(name)) {
      assert.equal(digest(restoreTokenizer(name,bytes)),provenance.upstream_file_sha256[name],'Unexpected runtime/source divergence: '+name);
    } else if(!['dist/Tokenizer.js.map','dist/Tokenizer.d.ts.map'].includes(name)) {
      assert.equal(digest(bytes),provenance.upstream_file_sha256[name],'Unexpected upstream input change: '+name);
    }
  }
  for(const [name,expected] of Object.entries(provenance.patch_file_sha256))assert.equal(digest(regular(root,name)),expected,'Changed patch bytes: '+name);
  const metadata=JSON.parse(regular(root,'package.json'));
  assert.equal(metadata.name,'htmlparser2');assert.equal(metadata.private,true);
  assert.match(metadata.version,/^12\.0\.0-loki\.[1-9]\d*$/);
  const restored={...metadata,version:'12.0.0'};delete restored.private;
  assert.deepEqual(restored,provenance.upstream_package_json,'Unexpected package API or supplier metadata change');
  return [...names,'FORK.md','UPSTREAM.json'].sort();
}

function crc32(bytes) {
  let crc=0xffffffff;
  for(const byte of bytes) {
    crc^=byte;
    for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);
  }
  return (crc^0xffffffff)>>>0;
}

/** The same portable USTAR and fixed gzip envelope used by the braces fork. */
export function buildArchive(root=here) {
  const chunks=[];
  for(const name of packageNames(root)) {
    assert(Buffer.byteLength('package/'+name)<=100,'USTAR path is too long');
    const bytes=regular(root,name),header=Buffer.alloc(512);
    header.write('package/'+name,0,100,'utf8');
    const octal=(number,start,width)=>header.write(number.toString(8).padStart(width-1,'0')+'\0',start,width,'ascii');
    octal(0o644,100,8);octal(0,108,8);octal(0,116,8);octal(bytes.length,124,12);octal(0,136,12);
    header.fill(32,148,156);header.write('0',156,1);header.write('ustar\0',257,6);header.write('00',263,2);
    header.write(header.reduce((sum,byte)=>sum+byte,0).toString(8).padStart(6,'0')+'\0 ',148,8);
    chunks.push(header,bytes,Buffer.alloc((512-bytes.length%512)%512));
  }
  chunks.push(Buffer.alloc(1024));
  const tar=Buffer.concat(chunks),trailer=Buffer.alloc(8);
  trailer.writeUInt32LE(crc32(tar),0);trailer.writeUInt32LE(tar.length>>>0,4);
  return Buffer.concat([Buffer.from([31,139,8,0,0,0,0,0,2,255]),deflateRawSync(tar,{level:9}),trailer]);
}

export function checkArchive(root=here) {
  const metadata=JSON.parse(regular(root,'package.json'));
  const name='htmlparser2-'+metadata.version+'.tgz',actual=regular(root,name),expected=buildArchive(root);
  assert(actual.equals(expected),'Archive differs from deterministic corresponding source');
  const repo=resolve(root,'../..'),manifest=JSON.parse(readFileSync(join(repo,'package.json')));
  const lock=JSON.parse(readFileSync(join(repo,'package-lock.json'))),spec='file:vendor/htmlparser2/'+name;
  assert.equal(manifest.devDependencies.htmlparser2,spec,'Root private dependency differs');
  assert.equal(manifest.overrides['sanitize-html@2.18.0'].htmlparser2,'$htmlparser2','Sanitizer scope differs');
  assert.equal(manifest.scripts.preinstall,'node vendor/htmlparser2/archive.mjs --check','Root archive lifecycle guard differs');
  assert.equal(lock.packages['node_modules/sanitize-html'].version,'2.18.0','Sanitizer needs requalification');
  const entry=lock.packages['node_modules/htmlparser2'];
  assert.equal(entry.version,metadata.version);assert.equal(entry.resolved,spec);assert(!entry.link);
  assert.equal(entry.integrity,sri(actual),'Archive integrity differs from root lock');
  return {status:'verified',package:metadata.name,version:metadata.version,bytes:actual.length,sha256:digest(actual),integrity:sri(actual)};
}

export function checkInstalled(root=here) {
  const result=checkArchive(root),repo=resolve(root,'../..');
  const consumer=createRequire(join(repo,'package.json')).resolve('sanitize-html');
  const installed=dirname(dirname(createRequire(consumer).resolve('htmlparser2')));
  assert.equal(resolve(installed),join(repo,'node_modules/htmlparser2'),'Unexpected selected installed fork');
  for(const name of packageNames(root))assert(regular(installed,name).equals(regular(root,name)),'Installed fork differs: '+name);
  return {...result,installed:true};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const mode=process.argv[2];
  if(mode==='--write') {
    const metadata=JSON.parse(regular(here,'package.json')),bytes=buildArchive();
    writeFileSync(join(here,'htmlparser2-'+metadata.version+'.tgz'),bytes,{flag:'wx'});
    console.log(JSON.stringify({status:'created',bytes:bytes.length,sha256:digest(bytes),integrity:sri(bytes)}));
  } else {
    assert(['--check','--check-installed'].includes(mode),'Use --check, --check-installed or --write; changed archives need a new private version');
    console.log(JSON.stringify(mode==='--check-installed'?checkInstalled():checkArchive()));
  }
}
