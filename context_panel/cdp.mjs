import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { unlinkSync } from 'node:fs';
import { findRenderer } from './renderer.mjs';

export class CDP {
  constructor(url) { this.url=url;this.pending=new Map();this.id=0; }
  async connect() {
    this.ws=new WebSocket(this.url);
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.ws.close();reject(Error('CDP connection timeout'));},5000);
      this.ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
      this.ws.addEventListener('error',()=>{clearTimeout(timer);reject(Error('CDP connection failed'));},{once:true});
    });
    this.ws.addEventListener('message', event=>{const message=JSON.parse(event.data);const pending=this.pending.get(message.id);if(pending){this.pending.delete(message.id);clearTimeout(pending.timer);message.error?pending.reject(Error(message.error.message)):pending.resolve(message.result);}else if(message.method)this.onEvent?.(message);});
    this.ws.addEventListener('close',()=>{for(const value of this.pending.values()){clearTimeout(value.timer);value.reject(Error('CDP disconnected'));}this.pending.clear();});
    return this;
  }
  send(method,params={}) {
    return new Promise((resolve,reject)=>{const id=++this.id;const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('CDP timeout: '+method));},12000);this.pending.set(id,{resolve,reject,timer});this.ws.send(JSON.stringify({id,method,params}));});
  }
  close(){this.ws?.close();}
}

function mount(capability) {
  window.__jevContextCleanup?.();
  const style=document.createElement('style');style.id='jev-context-style';
  style.textContent=`#jev-context-nav[aria-expanded=true]{background:var(--color-background-primary-ghost-hover,#8882)}#jev-context-dock{position:fixed;z-index:2147483646;border:1px solid var(--jev-line,#d4e5de);border-radius:13px;overflow:hidden;background:var(--jev-bg,#f3faf7);box-shadow:0 20px 75px #0006;box-sizing:border-box}#jev-context-dock iframe{display:block;width:100%;height:calc(100% - 34px);border:0}#jev-context-handle{height:34px;display:flex;align-items:center;gap:8px;padding:0 10px;background:var(--jev-bg,#f3faf7);border-bottom:1px solid var(--jev-line,#d4e5de);color:var(--jev-ink,#587269);font:500 11px -apple-system,sans-serif;cursor:grab;touch-action:none;user-select:none;box-sizing:border-box}#jev-context-handle span{flex:1}#jev-context-handle button{border:0;background:transparent;color:inherit;cursor:pointer;font:11px -apple-system,sans-serif;padding:4px 6px}#jev-context-dock[hidden]{display:none}`;
  document.head.append(style);
  const button=document.createElement('button');button.id='jev-context-nav';button.type='button';button.title='JevClean';button.setAttribute('aria-controls','jev-context-dock');button.setAttribute('aria-expanded','false');
  const attachNavigation=()=>{
    const items=[...document.querySelectorAll('button.sidebar-item')];
    const anchor=items.find(e=>['探索','Explore'].includes(e.textContent.trim()))||items.find(e=>['插件','Plugins'].includes(e.textContent.trim()));
    if(!anchor)return;
    if(button.className!==anchor.className)button.className=anchor.className;
    if(!button.firstElementChild){
      const content=anchor.firstElementChild.cloneNode(true);
      const label=content.querySelector('.text-fade-truncate');if(label)label.textContent='JevClean';
      const icon=content.querySelector('.icon-leading-slot');if(icon)icon.innerHTML='<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 3.5h10M3 7h7M3 10.5h4M10 10l2 2 3-4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      button.append(content);
    }
    if(anchor.nextElementSibling!==button)anchor.after(button);
  };
  attachNavigation();
  const dock=document.createElement('section');dock.id='jev-context-dock';dock.hidden=true;
  const handle=document.createElement('div');handle.id='jev-context-handle';
  handle.innerHTML='<span>⠿ JevClean · 拖动移动</span><button type="button" data-reset title="恢复默认位置">复位</button><button type="button" data-close title="收起侧栏" aria-label="收起侧栏">✕</button>';
  dock.append(handle);
  const frame=document.createElement('iframe');frame.id='jev-context-frame';frame.title='JevClean';frame.setAttribute('sandbox','allow-scripts allow-downloads');
  frame.setAttribute('allow','clipboard-write');frame.src='about:blank';dock.append(frame);
  document.body.append(dock);
  const layoutKey='jev-context-layout-v1';let layout={};
  try{layout=JSON.parse(localStorage.getItem(layoutKey)||'{}')||{};}catch{}
  if(typeof layout!=='object'||Array.isArray(layout))layout={};
  const save=()=>{try{localStorage.setItem(layoutKey,JSON.stringify(layout));}catch{}};
  const clamp=(n,min,max)=>Math.max(min,Math.min(n,Math.max(min,max)));
  const place=(element,key,point)=>{
    const rect=element.getBoundingClientRect();
    const x=clamp(point.x,8,innerWidth-rect.width-8),y=clamp(point.y,8,innerHeight-rect.height-8);
    Object.assign(element.style,{left:x+'px',top:y+'px',right:'auto',bottom:'auto'});
    layout[key]={x,y};
  };
  const arrange=()=>{
    // Measure hidden docks without revealing them on screen.
    const hidden=dock.hidden;if(hidden){dock.style.visibility='hidden';dock.hidden=false;}
    dock.style.width=Math.max(0,Math.min(540,innerWidth-16))+'px';
    dock.style.height=Math.max(36,innerHeight-130)+'px';
    for(const [element,key,fallback] of [[dock,'dock',{x:innerWidth-dock.offsetWidth-16,y:76}]]){
      const p=layout[key];place(element,key,p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?p:fallback);
    }
    if(hidden){dock.hidden=true;dock.style.visibility='';}
  };
  arrange();window.addEventListener('resize',arrange);
  const makeDraggable=(grip,element,key)=>{
    let drag=null;
    grip.addEventListener('pointerdown',event=>{
      if(event.button!==0||event.target.closest('button'))return;
      const r=element.getBoundingClientRect();drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:r.left,top:r.top,moved:false};
      grip.setPointerCapture(event.pointerId);
    });
    grip.addEventListener('pointermove',event=>{
      if(!drag||drag.id!==event.pointerId)return;
      const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
      if(!drag.moved&&Math.hypot(dx,dy)<4)return;
      drag.moved=true;grip.style.cursor='grabbing';frame.style.pointerEvents='none';
      place(element,key,{x:drag.left+dx,y:drag.top+dy});
    });
    const end=event=>{
      if(!drag||drag.id!==event.pointerId)return;
      if(drag.moved)save();
      drag=null;grip.style.cursor='';frame.style.pointerEvents='';
      if(grip.hasPointerCapture(event.pointerId))grip.releasePointerCapture(event.pointerId);
    };
    grip.addEventListener('pointerup',end);grip.addEventListener('pointercancel',end);grip.addEventListener('lostpointercapture',end);
  };
  makeDraggable(handle,dock,'dock');
  const setOpen=open=>{dock.hidden=!open;button.setAttribute('aria-expanded',String(open));};
  handle.querySelector('[data-close]').onclick=()=>setOpen(false);
  handle.querySelector('[data-reset]').onclick=()=>{layout={};arrange();save();};
  let ready=false,lastThread='';
  const currentThread=()=>location.pathname.match(/\/local\/([a-f0-9-]{36})/)?.[1];
  const sync=()=>{const id=currentThread();if(ready&&id&&id!==lastThread){lastThread=id;frame.contentWindow.postMessage({type:'jev-context:thread',id},'*');}};
  const receive=event=>{
    if(event.source!==frame.contentWindow||event.origin!=='null')return;
    if(event.data?.type==='jev-context:api'&&event.data.capability===capability)window.__jevContextApi(JSON.stringify(event.data));
    if(event.data?.type==='jev-context:language'&&['zh','en'].includes(event.data.language)){
      const english=event.data.language==='en';
      handle.querySelector('span').textContent='⠿ JevClean · '+(english?'Drag to move':'拖动移动');
      const reset=handle.querySelector('[data-reset]'),close=handle.querySelector('[data-close]');
      reset.textContent=english?'Reset':'复位';reset.title=english?'Reset position':'恢复默认位置';
      close.title=english?'Close panel':'收起侧栏';close.setAttribute('aria-label',close.title);
    }
    if(event.data?.type==='jev-context:theme'){
      const palettes={fresh:['#f3faf7','#d4e5de','#587269'],colorful:['#faf7ff','#e3daf0','#756484'],tech:['#0d192b','#2c4764','#9bb3cd'],plain:['#faf9f6','#e0ddd5','#706c64']};
      const colors=Object.hasOwn(palettes,event.data.theme)?palettes[event.data.theme]:null;
      if(colors)colors.forEach((color,i)=>dock.style.setProperty(['--jev-bg','--jev-line','--jev-ink'][i],color));
    }
    if(event.data?.type==='jev-context:ready'){ready=true;dock.dataset.ready='true';sync();}
    if(event.data?.type==='jev-context:open-thread'&&/^[a-f0-9-]{36}$/.test(event.data.id))window.postMessage({type:'navigate-to-route',path:'/local/'+event.data.id},location.origin);
  };
  window.addEventListener('message',receive);
  window.__jevContextReply=data=>frame.contentWindow.postMessage({type:'jev-context:api-reply',...data},'*');
  button.onclick=()=>{setOpen(dock.hidden);if(!dock.hidden){arrange();sync();}};
  const observer=new MutationObserver(()=>{attachNavigation();if(!document.getElementById(dock.id))document.body.append(dock);sync();});
  observer.observe(document.body,{childList:true,subtree:true});
  const timer=setInterval(sync,1500);
  window.__jevContextCleanup=()=>{observer.disconnect();clearInterval(timer);window.removeEventListener('message',receive);window.removeEventListener('resize',arrange);dock.remove();button.remove();style.remove();delete window.__jevContextCleanup;delete window.__jevContextReply;};
  return {mounted:true,ready:false};
}

async function main() {
  const args=process.argv.slice(2), option=(name,fallback)=>args.includes(name)?args[args.indexOf(name)+1]:fallback;
  const endpoint=option('--cdp','http://127.0.0.1:9231');
  const runtimePath=option('--runtime',path.join(os.homedir(),'Library/Application Support/JevContext/runtime.json'));
  const runtime=JSON.parse(await fs.readFile(runtimePath,'utf8'));
  const lockPath=path.join(path.dirname(runtimePath),'bridge-runtime.json');
  try{const old=JSON.parse(await fs.readFile(lockPath,'utf8'));let alive=false;try{process.kill(old.pid,0);alive=true;}catch{}if(alive){console.log('Jev CDP 桥已在运行，不重复注入。若整页刷新后面板消失，请先退出旧桥进程再启动。');return;}}catch{}
  const health=await fetch(runtime.url+'/api/status',{headers:{Authorization:'Bearer '+runtime.token}});
  if(!health.ok)throw Error('本地服务不可用，请先启动 Python 服务');
  console.log('正在等待 Codex 主页面加载（最多约 30 秒）…');
  const client=await findRenderer({
    list:async()=>{const response=await fetch(endpoint+'/json/list',{signal:AbortSignal.timeout(2000)});if(!response.ok)throw Error('CDP target list unavailable');const targets=await response.json();return Array.isArray(targets)?targets:[];},
    connect:url=>new CDP(url).connect(),
  });
  await client.send('Page.enable');
  await client.send('Page.setBypassCSP',{enabled:true});
  const contexts=[];
  client.onEvent=event=>{if(event.method==='Runtime.executionContextCreated')contexts.push(event.params.context);};
  await client.send('Runtime.enable');
  const rootFrame=(await client.send('Page.getFrameTree')).frameTree.frame.id;
  const mainContext=contexts.find(context=>context.auxData?.isDefault&&context.auxData.frameId===rootFrame)?.id;
  if(!mainContext)throw Error('Cannot identify host execution context');
  await client.send('Runtime.addBinding',{name:'__jevContextApi',executionContextId:mainContext});
  const capability=randomBytes(24).toString('hex');
  const here=path.dirname(fileURLToPath(import.meta.url));
  const prefill=await fs.readFile(path.join(here,'prefill.js'),'utf8');
  client.onEvent=async event=>{
    if(event.method!=='Runtime.bindingCalled'||event.params.name!=='__jevContextApi'||event.params.executionContextId!==mainContext)return;
    let data;
    try{
      data=JSON.parse(event.params.payload);
      if(data.capability!==capability||typeof data.id!=='string'||event.params.payload.length>200000)return;
      if(data.path==='/host/prefill'){
        if(typeof data.body?.prompt!=='string'||data.body.prompt.length>100000||typeof data.body.cwd!=='string')throw Error('交接稿过大或缺少项目，请使用 Markdown 文件');
        const result=await client.send('Runtime.evaluate',{expression:prefill+'('+JSON.stringify(data.body)+')',awaitPromise:true,returnByValue:true});
        if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||'原生新任务预填失败');
        await client.send('Runtime.evaluate',{expression:'window.__jevContextReply?.('+JSON.stringify({id:data.id,status:200,text:JSON.stringify(result.result.value)})+')'});return;
      }
      if(typeof data.id!=='string'||typeof data.path!=='string'||!/^\/api\/[a-z0-9/?=&%._-]+$/i.test(data.path)||data.path.includes('..'))throw Error('Invalid bridge path');
      const response=await fetch(runtime.url+data.path,{method:data.body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+runtime.token,'Content-Type':'application/json'},body:data.body===undefined?undefined:JSON.stringify(data.body)});
      const text=await response.text();
      await client.send('Runtime.evaluate',{expression:'window.__jevContextReply?.('+JSON.stringify({id:data.id,status:response.status,text})+')'});
    }catch(error){if(data?.id)await client.send('Runtime.evaluate',{expression:'window.__jevContextReply?.('+JSON.stringify({id:data.id,status:500,text:JSON.stringify({error:error.message})})+')'}).catch(()=>{});}
  };
  const source='('+mount.toString()+')('+JSON.stringify(capability)+')';
  const result=await client.send('Runtime.evaluate',{expression:source,returnByValue:true});
  if(result.exceptionDetails)throw Error('侧栏脚本执行失败');
  const bridge=`<script>(()=>{const capability=${JSON.stringify(capability)};const pending=new Map();window.jevBridge=(path,body)=>new Promise((resolve,reject)=>{const id=crypto.randomUUID();const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP bridge timeout'));},15000);pending.set(id,{resolve,timer});parent.postMessage({type:'jev-context:api',id,path,body,capability},'*');});window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='jev-context:api-reply')return;const p=pending.get(event.data.id);if(p){clearTimeout(p.timer);pending.delete(event.data.id);p.resolve(event.data);}});})();</script>`;
  let html=await fs.readFile(path.join(here,'web/index.html'),'utf8');
  html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+await fs.readFile(path.join(here,'web/style.css'),'utf8')+'</style>');
  html=html.replace('<script src="/i18n.js"></script>','<script>'+await fs.readFile(path.join(here,'web/i18n.js'),'utf8')+'</script>');
  html=html.replace('<script src="/flow.js"></script>','<script>'+await fs.readFile(path.join(here,'web/flow.js'),'utf8')+'</script>');
  html=html.replace('<script src="/app.js"></script>',bridge+'<script>'+await fs.readFile(path.join(here,'web/app.js'),'utf8')+'</script>');
  const tree=await client.send('Page.getFrameTree');
  const frames=[];const walk=t=>{frames.push(t.frame);for(const child of t.childFrames||[])walk(child);};walk(tree.frameTree);
  let frameId;
  for(const f of frames.filter(f=>f.parentId)){try{const owner=await client.send('DOM.getFrameOwner',{frameId:f.id});const node=await client.send('DOM.describeNode',{backendNodeId:owner.backendNodeId});if(node.node.attributes?.includes('jev-context-frame'))frameId=f.id;}catch{}}
  if(!frameId)throw Error('Could not find Jev iframe');
  await client.send('Page.setDocumentContent',{frameId,html});
  let ready=false;
  for(let i=0;i<30;i++){await new Promise(r=>setTimeout(r,300));const state=await client.send('Runtime.evaluate',{expression:'document.getElementById("jev-context-dock")?.dataset.ready === "true"',returnByValue:true});if(state.result?.value){ready=true;break;}}
  console.log(ready?'Jev CDP 侧栏已加载，已收到 UI ready。':'侧栏已挂载，但未收到 UI ready，请检查 iframe 加载。');
  if(ready){await fs.writeFile(lockPath,JSON.stringify({pid:process.pid,endpoint}),{mode:0o600});process.on('exit',()=>{try{unlinkSync(lockPath);}catch{}});}
  process.on('SIGINT',async()=>{try{await client.send('Runtime.evaluate',{expression:'window.__jevContextCleanup?.()'});}finally{client.close();process.exit(0);}});
  if(!ready){client.close();process.exitCode=1;}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(error.message);process.exitCode=1;});
