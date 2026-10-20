import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import test from 'node:test';
import {pathToFileURL} from 'node:url';

const rootRequire=createRequire(new URL('../../../package.json',import.meta.url));
const {DomUtils, Parser, parseDocument, Tokenizer}=await import(pathToFileURL(rootRequire.resolve('htmlparser2')).href);

function parsed(chunks,options={}) {
  const result={text:'',comments:[],tags:[]};
  const parser=new Parser({
    ontext:value=>{result.text+=value;},
    oncomment:value=>result.comments.push(value),
    onopentag:name=>result.tags.push(name),
  },options);
  for(const chunk of chunks)parser.write(chunk);
  parser.end();
  return result;
}

test('ordinary HTML CDATA spelling is a bogus comment ending at the first greater-than',()=>{
  const result=parsed(['<![CDATA[ x > <noscript>]]><a href="https://example.invalid/loki-link">hidden</a></noscript>']);
  assert.deepEqual(result.comments,['[CDATA[ x ']);
  assert.deepEqual(result.tags,['noscript','a']);
  assert.equal(result.text,' ]]>hidden');
});

test('XML CDATA retains literal markup as text',()=>{
  const document=parseDocument('<root><![CDATA[<literal> && text]]></root>',{xmlMode:true});
  assert.equal(DomUtils.textContent(document),'<literal> && text');
  assert.deepEqual(parsed(['<root><![CDATA[<literal> && text]]></root>'],{xmlMode:true}).tags,['root']);
});

test('explicit recognizeCDATA preserves ordinary HTML literal CDATA',()=>{
  const document=parseDocument('<root><![CDATA[<literal>]]></root>',{recognizeCDATA:true});
  assert.equal(DomUtils.textContent(document),'<literal>');
  const result=parsed(['<root><![CDATA[<literal>]]></root>'],{recognizeCDATA:true});
  assert.deepEqual(result.tags,['root']);
  assert.deepEqual(result.comments,[]);
  assert.equal(result.text,'<literal>');
});

test('explicit recognizeCDATA false keeps ordinary HTML bogus-comment behavior',()=>{
  const input='<![CDATA[ x > <noscript>]]><a>hidden</a></noscript>';
  assert.deepEqual(parsed([input],{recognizeCDATA:false}),parsed([input]));
});

for(const [name,input,text,tags] of [
  ['SVG','<svg><![CDATA[<circle title="literal"/>]]><circle /></svg>','<circle title="literal"/>',['svg','circle']],
  ['MathML','<math><![CDATA[x < y]]><mi>x</mi></math>','x < yx',['math','mi']],
]) {
  test(name+' retains the upstream foreign-content CDATA path',()=>{
    const result=parsed([input]);
    assert.deepEqual(result.comments,[]);
    assert.equal(result.text,text);
    assert.deepEqual(result.tags,tags);
  });
}

for(const [name,input,expected] of [
  ['script','<script>if (a < b) { marker = "<![CDATA[" }</script><p>after</p>','if (a < b) { marker = "<![CDATA[" }after'],
  ['style','<style>p::before { content: "<![CDATA[" }</style><p>after</p>','p::before { content: "<![CDATA[" }after'],
  ['textarea','<textarea>safe &amp; <literal></textarea><p>after</p>','safe & <literal>after'],
]) {
  test(name+' content preserves its raw-text or entity behavior',()=>{
    assert.equal(parsed([input]).text,expected);
  });
}

test('declaration context is preserved across every streaming chunk boundary',()=>{
  for(const [input,options] of [
    ['<!DOCTYPE html><!-- comment --><p>normal &amp; text</p>',{}],
    ['<![CDATA[ x > <noscript>]]><a>hidden</a></noscript>',{}],
    ['<svg><![CDATA[<circle/>]]><circle /></svg>',{}],
    ['<root><![CDATA[x < y]]></root>',{xmlMode:true}],
  ])assert.deepEqual(parsed([...input],options),parsed([input],options));
});

test('CJS and ESM retain the same public parser exports',()=>{
  const required=rootRequire('htmlparser2');
  assert.equal(required.Parser,Parser);
  assert.equal(required.Tokenizer,Tokenizer);
  assert.equal(required.parseDocument,parseDocument);
});

test('low-level Tokenizer callers may omit the optional foreign-context callback',()=>{
  const callbacks=Object.fromEntries([
    'onattribdata','onattribentity','onattribend','onattribname','oncdata',
    'onclosetag','oncomment','ondeclaration','onend','onopentagend',
    'onopentagname','onprocessinginstruction','onselfclosingtag','ontext','ontextentity',
  ].map(name=>[name,()=>{}]));
  const tokenizer=new Tokenizer({},callbacks);
  tokenizer.write('<![CDATA[x > text');
  tokenizer.end();
});
