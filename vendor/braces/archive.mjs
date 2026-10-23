import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {lstatSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {deflateRawSync} from 'node:zlib';

const here=dirname(fileURLToPath(import.meta.url));
const names=['FORK.md','LICENSE','README.md','UPSTREAM.json','index.js','lib/compile.js',
  'lib/constants.js','lib/expand.js','lib/parse.js','lib/stringify.js','lib/utils.js','package.json'];
const digest=(bytes,algorithm='sha256')=>createHash(algorithm).update(bytes).digest('hex');
const sri=bytes=>'sha512-'+createHash('sha512').update(bytes).digest('base64');

function regular(root,name) {
  const file=join(root,name);
  assert(lstatSync(file).isFile()&&!lstatSync(file).isSymbolicLink(),'Nonregular package input: '+name);
  assert(lstatSync(file).size<1024*1024,'Oversized package input: '+name);
  if(name.startsWith('lib/'))assert(lstatSync(join(root,'lib')).isDirectory()&&!lstatSync(join(root,'lib')).isSymbolicLink(),'Nonregular lib directory');
  return readFileSync(file);
}

function crc32(bytes) {
  let crc=0xffffffff;
  for(const byte of bytes) {
    crc^=byte;
    for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);
  }
  return (crc^0xffffffff)>>>0;
}

/** A portable USTAR plus fixed gzip envelope; no host paths, clocks or owners. */
export function buildArchive(root=here) {
  const provenance=JSON.parse(regular(root,'UPSTREAM.json'));
  for(const name of ['LICENSE','README.md','index.js','lib/constants.js','lib/parse.js']) {
    assert.equal(digest(regular(root,name)),provenance.upstream_file_sha256[name],'Unexpected upstream input change: '+name);
  }
  const chunks=[];
  for(const name of names) {
    const bytes=regular(root,name),header=Buffer.alloc(512);
    header.write('package/'+name,0,100,'utf8');
    const octal=(number,start,width)=>header.write(number.toString(8).padStart(width-1,'0')+'\0',start,width,'ascii');
    octal(0o644,100,8);octal(0,108,8);octal(0,116,8);octal(bytes.length,124,12);octal(0,136,12);
    header.fill(32,148,156);header.write('0',156,1);header.write('ustar\0',257,6);header.write('00',263,2);
    const checksum=header.reduce((sum,byte)=>sum+byte,0);
    header.write(checksum.toString(8).padStart(6,'0')+'\0 ',148,8);
    chunks.push(header,bytes,Buffer.alloc((512-bytes.length%512)%512));
  }
  chunks.push(Buffer.alloc(1024));
  const tar=Buffer.concat(chunks),trailer=Buffer.alloc(8);
  trailer.writeUInt32LE(crc32(tar),0);trailer.writeUInt32LE(tar.length>>>0,4);
  return Buffer.concat([Buffer.from([31,139,8,0,0,0,0,0,2,255]),deflateRawSync(tar,{level:9}),trailer]);
}

export function checkArchive(root=here) {
  const metadata=JSON.parse(regular(root,'package.json'));
  assert.equal(metadata.name,'braces');assert.equal(metadata.private,true);
  assert.match(metadata.version,/^3\.0\.3-loki\.[1-9]\d*$/);
  const name='braces-'+metadata.version+'.tgz',actual=regular(root,name),expected=buildArchive(root);
  assert(actual.equals(expected),'Archive bytes differ from deterministic source regeneration');
  const repo=resolve(root,'../..');
  const manifest=JSON.parse(readFileSync(join(repo,'website/package.json')));
  const lock=JSON.parse(readFileSync(join(repo,'website/package-lock.json')));
  const spec='file:../vendor/braces/'+name;
  assert.equal(manifest.devDependencies.braces,spec,'Website private dependency reference differs');
  for(const parent of ['chokidar@3.6.0','micromatch@4.0.8']) {
    assert.equal(manifest.overrides[parent].braces,'$braces','Affected parent override differs: '+parent);
  }
  const entry=lock.packages['node_modules/braces'];
  assert.equal(entry.version,metadata.version);assert.equal(entry.resolved,spec);assert(!entry.link);
  assert.equal(entry.integrity,sri(actual),'Archive integrity differs from website lock');
  return {status:'verified',package:metadata.name,version:metadata.version,bytes:actual.length,sha256:digest(actual),integrity:sri(actual)};
}

export function checkInstalled(root=here) {
  const result=checkArchive(root);
  const manifest=join(resolve(root,'../..'),'website/package.json');
  const installed=dirname(createRequire(manifest).resolve('braces/package.json'));
  assert.equal(resolve(installed),join(dirname(manifest),'node_modules/braces'),'Unexpected installed fork location');
  for(const name of names)assert(regular(installed,name).equals(regular(root,name)),'Installed fork differs: '+name);
  return {...result,installed:true};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const mode=process.argv[2];
  if(mode==='--write') {
    const pkg=JSON.parse(regular(here,'package.json'));
    assert.match(pkg.version,/^3\.0\.3-loki\.[1-9]\d*$/);
    const target=join(here,'braces-'+pkg.version+'.tgz'),bytes=buildArchive();
    writeFileSync(target,bytes,{flag:'wx'});
    console.log(JSON.stringify({status:'created',bytes:bytes.length,sha256:digest(bytes),integrity:sri(bytes)}));
  } else {
    assert(['--check','--check-installed'].includes(mode),'Use --check, --check-installed or --write; --write requires a new archive filename');
    console.log(JSON.stringify(mode==='--check-installed'?checkInstalled():checkArchive()));
  }
}
