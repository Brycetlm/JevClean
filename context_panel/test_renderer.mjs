import assert from 'node:assert/strict';
import test from 'node:test';
import {findRenderer, isMainPage} from './renderer.mjs';

const main = {type:'page', url:'app://-/index.html#/local/example', webSocketDebuggerUrl:'ws://fixture/main'};
function clock() {
  let time = 0;
  return {now:()=>time, sleep:async ms=>{time+=ms;}, timeout:1500};
}
function client(ready) {
  return {closed:false, async send(){return {result:{value:ready}};}, close(){this.closed=true;}};
}

test('recognizes the main app page, excludes overlays, ordinary sites and workers',()=>{
  assert.ok(isMainPage(main));
  for(const changes of [{url:'app://-/avatar-overlay.html'}, {url:'https://example.com/index.html'},
    {url:'devtools://devtools/bundled/inspector.html'}, {type:'worker'}, {webSocketDebuggerUrl:''}]) {
    assert.equal(isMainPage({...main,...changes}),false);
  }
});

test('selects a ready DOM without requiring the native prefill bridge',async()=>{
  const expected=client(true);
  const found=await findRenderer({...clock(),list:async()=>[main],connect:async()=>expected});
  assert.equal(found,expected);
  assert.equal(expected.closed,false);
});

test('waits for the target to appear and the document to load',async()=>{
  let lists=0, connects=0;
  const loading=client(false), ready=client(true);
  const found=await findRenderer({...clock(),list:async()=>++lists===1?[]:[main],
    connect:async()=>++connects===1?loading:ready});
  assert.equal(found,ready);
  assert.equal(loading.closed,true);
  assert.equal(lists,3);
});

test('recovers when a startup target disappears or listing initially fails',async()=>{
  let lists=0, connects=0;
  const ready=client(true);
  const found=await findRenderer({...clock(),list:async()=>{if(++lists===1)throw Error('starting');return [main];},
    connect:async()=>{if(++connects===1)throw Error('target disappeared');return ready;}});
  assert.equal(found,ready);
});

test('reports page discovery and document readiness failures separately',async()=>{
  await assert.rejects(findRenderer({...clock(),list:async()=>[{...main,url:'app://-/other.html'}],
    connect:async()=>{throw Error('must not connect to unrelated page');}}),/未发现匹配的主页面/);
  const loading=client(false);
  await assert.rejects(findRenderer({...clock(),list:async()=>[main],connect:async()=>loading}),/页面未就绪/);
  assert.equal(loading.closed,true);
});
