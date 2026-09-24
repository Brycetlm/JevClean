// Run with NODE_PATH pointing at a runtime that provides Playwright.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url),{chromium}=require('playwright');
const root=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(execFileSync('python3',['-c','import json; from context_panel.core import DEFAULTS, DEFAULTS_EN; print(json.dumps(dict(settings=DEFAULTS,defaults=DEFAULTS,defaults_en=DEFAULTS_EN)))'],{cwd:path.dirname(root),encoding:'utf8'}));
let keyConfigured=true,keyFailure=false,keyWrites=0;
let prefs={theme:'fresh',language:'zh'},appearanceFailure=false,modelCalls=0;
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:540,height:820},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const thread={id:'11111111-1111-1111-1111-111111111111',title:'用户对话标题不翻译',cwd:'/demo/project',updated_at:1790164000};
let savedSettings=structuredClone(config.settings);
await page.route('http://jev.test/**',async route=>{
 const url=new URL(route.request().url());const body=route.request().postDataJSON();let result={};
 if(!url.pathname.startsWith('/api/')){
  const name=url.pathname==='/'?'index.html':url.pathname.slice(1);
  return route.fulfill({body:await fs.readFile(path.join(root,'web',name)),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
 }
 switch(url.pathname){
 case '/api/settings': if(body)savedSettings=body;result=body?savedSettings:{...config,settings:savedSettings};break;
 case '/api/status':result={key_configured:keyConfigured};break;
 case '/api/credentials':if(keyFailure)return route.fulfill({status:400,json:{error:'failed'}});keyWrites++;keyConfigured=true;result={key_configured:true};break;
 case '/api/appearance':if(body){if(appearanceFailure)return route.fulfill({status:400,json:{error:'请选择中文或英文'}});prefs={...prefs,...body}}result=prefs;break;
 case '/api/threads':result=[thread];break;
 case '/api/preview':result={id:'snapshot',thread_id:thread.id,messages:5,segments:6,characters:1000,protected:2,model_segments:4,requests:1,concurrency:2,snapshot_at:Date.now()/1000,expires_at:Date.now()/1000+300};break;
 case '/api/runs':if(body)modelCalls++;result=[];break;
 default:if(url.pathname.endsWith('/draft'))return route.fulfill({body:url.searchParams.get('language')==='en'?'# Compact conversation\n\n用户正文保留原样':'# 精简会话\n\n用户正文保留原样'});
 }
 return route.fulfill({json:result});
});
async function englishSystemLeaks(){return page.evaluate(()=>{
 const skip='.thread-title,#selected-title,.segment-text,.flow-card p,.bucket-last,textarea,#apply-preview,#omitted-preview p';
 const walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),leaks=[];
 while(walk.nextNode()){
  const node=walk.currentNode,p=node.parentElement;
  if(p.closest('script,style,'+skip)||!p.checkVisibility()||p.id==='language-toggle')continue;
  if(/[\u3400-\u9fff]/.test(node.textContent))leaks.push(node.textContent);
 }
 for(const el of document.querySelectorAll('[title],[placeholder],[aria-label]')){
  if(el.closest(skip)||el.id==='language-toggle'||!el.checkVisibility())continue;
  for(const attr of ['title','placeholder','aria-label'])if(!(attr==='title'&&el.matches('.thread,#action-target'))&&(/[\u3400-\u9fff]/.test(el.getAttribute(attr)||'')))leaks.push(el.id+':'+attr+':'+el.getAttribute(attr));
 }
 return leaks;
});}
try{
 await page.goto('http://jev.test/');await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Gateway'));
 await page.click('#language-toggle');await page.waitForFunction(()=>uiLanguage==='en'&&!savingAppearance);
 assert.equal(prefs.language,'en');assert.equal(await page.title(),'JevClean');assert.deepEqual(await englishSystemLeaks(),[]);
 await page.click('#threads .thread');await page.waitForFunction(()=>!!preview);
 assert.match(await page.locator('#preview-detail').textContent(),/protected/);
 // Missing Key must guide configuration without sending classification requests.
 keyConfigured=false;
 await page.click('#start');await page.waitForFunction(()=>document.querySelector('#key-dialog').open);
 assert.equal(await page.locator('#key-notice').isVisible(),true);
 assert.deepEqual(await englishSystemLeaks(),[]);
 assert.equal(modelCalls,0);
 keyFailure=true;
 await page.fill('#key-input','fixture-ui-private-key-12345');await page.click('#key-save');
 await page.waitForFunction(()=>!savingKey);
 assert.match(await page.locator('#key-notice').textContent(),/Could not save/);
 assert.equal(await page.locator('#key-dialog').evaluate(el=>el.open),true);
 keyFailure=false;await page.click('#key-save');
 await page.waitForFunction(()=>!document.querySelector('#key-dialog').open&&!!preview&&!previewLoading);
 assert.equal(keyWrites,1);assert.equal(modelCalls,0);
 assert.equal(await page.locator('#key-input').inputValue(),'');
 assert.match(await page.locator('#connection').textContent(),/configured/i);
 await page.click('#key-open');assert.equal(await page.locator('#key-input').inputValue(),'');
 assert.deepEqual(await englishSystemLeaks(),[]);
 await page.fill('#key-input','fixture-not-saved-key-12345');await page.keyboard.press('Escape');
 await page.waitForFunction(()=>document.querySelector('#key-input').value==='');
 await page.click('#language-toggle');await page.waitForFunction(()=>uiLanguage==='zh'&&!savingAppearance);
 await page.click('#key-open');assert.match(await page.locator('#key-status').textContent(),/已配置/);
 await page.click('#key-close');
 await page.click('#language-toggle');await page.waitForFunction(()=>uiLanguage==='en'&&!savingAppearance);
 let before=await page.evaluate(()=>({id:preview.id,settings:JSON.stringify(settings)}));
 await page.click('#settings-open');assert.deepEqual(await englishSystemLeaks(),[]);
 assert.equal(await page.locator('input[name=context_window_size]').inputValue(),'3');
 assert.equal(await page.locator('textarea[name=skip_patterns]').inputValue(),'key\napikey');
 await page.locator('textarea[name=skip_patterns]').fill('token\nsecret');
 await page.locator('input[name=context_window_size]').fill('5');
 assert.equal(await page.locator('input[name=classify_user_messages]').isChecked(),true);
 await page.uncheck('input[name=classify_user_messages]');await page.click('#settings-save');
 await page.waitForFunction(()=>!document.querySelector('#settings').open&&settings.classify_user_messages===false);
 assert.equal(savedSettings.classify_user_messages,false);
 assert.equal(savedSettings.context_window_size,5);
 assert.deepEqual(savedSettings.skip_patterns,['token','secret']);
 await page.click('#settings-open');assert.equal(await page.locator('input[name=classify_user_messages]').isChecked(),false);
 assert.equal(await page.locator('input[name=context_window_size]').inputValue(),'5');
 assert.equal(await page.locator('textarea[name=skip_patterns]').inputValue(),'token\nsecret');
 await page.locator('textarea[name=skip_patterns]').fill('');
 await page.locator('input[name=context_window_size]').fill('3');
 await page.check('input[name=classify_user_messages]');await page.click('#settings-save');
 await page.waitForFunction(()=>!document.querySelector('#settings').open&&settings.classify_user_messages===true);
 assert.deepEqual(savedSettings.skip_patterns,[]);
 await page.click('#settings-open');

 assert.equal(await page.locator('#settings textarea:visible').count(),4);
 assert.equal(await page.locator('textarea[name=goal],textarea[name=policy],textarea[name=question]').count(),0);
 assert.match(await page.locator('textarea[name=prompt]').inputValue(),/^Organize/);
 await page.locator('textarea[name=keep]').fill('只留下尚未完成的事项');
 await page.locator('textarea[name=drop]').fill('去掉已完成事项');
 assert.equal(await page.locator('textarea[name=review]').isVisible(),false);
 await page.check('input[name=manual_review]');
 assert.equal(await page.locator('textarea[name=review]').isVisible(),true);
 await page.locator('textarea[name=review]').fill('时间关系不明确');
 await page.uncheck('input[name=manual_review]');
 await page.click('#settings-save');
 await page.waitForFunction(()=>!document.querySelector('#settings').open);
 assert.deepEqual(savedSettings.criteria,{keep:'只留下尚未完成的事项',drop:'去掉已完成事项',review:'时间关系不明确'});
 await page.click('#settings-open');
 assert.equal(await page.locator('textarea[name=keep]').inputValue(),'只留下尚未完成的事项');
 assert.equal(await page.locator('textarea[name=drop]').inputValue(),'去掉已完成事项');
 before=await page.evaluate(()=>({id:preview.id,settings:JSON.stringify(settings)}));
 await page.locator('textarea[name=prompt]').fill('自定义提示词保持原样');await page.click('#settings-close');
 await page.click('#language-toggle');await page.waitForFunction(()=>uiLanguage==='zh'&&!savingAppearance);
 assert.equal(await page.locator('textarea[name=prompt]').inputValue(),'自定义提示词保持原样');
 await page.click('#language-toggle');await page.waitForFunction(()=>uiLanguage==='en'&&!savingAppearance);
 assert.deepEqual(await page.evaluate(()=>({id:preview.id,settings:JSON.stringify(settings)})),before);
 await page.click('#appearance-open');assert.deepEqual(await englishSystemLeaks(),[]);await page.click('[data-theme-choice=tech]');await page.waitForFunction(()=>!savingAppearance);assert.equal(prefs.language,'en');await page.click('#appearance-close');
 await page.reload();await page.waitForFunction(()=>uiLanguage==='en'&&!!settings);assert.equal(await page.locator('html').getAttribute('data-theme'),'tech');
 await page.evaluate(()=>{
 selected={id:'11111111-1111-1111-1111-111111111111',title:'用户对话标题不翻译',cwd:'/demo/project'};
 run={id:'fixture',thread:selected,settings:{...settings,manual_review:true},status:'running',requests:3,retry_pending:1,retry_count:1,retry_exhausted:0,usage:{},revision:0,segments:[
 {id:'s1',role:'user',line:1,text:'用户正文保留原样',status:'keep',protected:true,protection:'用户原始要求'},
 {id:'s2',role:'assistant',line:2,text:'用户正文保留原样',status:'queued',retry_waiting:true,reason:'HTTP 503，已放回队尾，等待第 1 次重试'},
 {id:'s3',role:'assistant',line:3,text:'用户正文保留原样',status:'drop',answer:{probabilities:{keep:.01,drop:.98,review:.01}},reason:'Jev 分类'}]};
 expanded=new Set(['s1','s2','s3']);$('#review-list').open=true;render();
 });
 assert.deepEqual(await englishSystemLeaks(),[]);assert.match(await page.locator('#flow-retry').textContent(),/requeued/);
 await page.evaluate(()=>{run.status='failed';run.retry_pending=0;run.retry_exhausted=1;run.error='Jev HTTP 503: unavailable';run.segments[1].status='review';run.segments[1].retry_waiting=false;run.segments[1].reason='重试次数已用完，自动保留';render()});
 assert.deepEqual(await englishSystemLeaks(),[]);
 await page.click('#apply-open');await page.waitForFunction(()=>!!applyReview);assert.deepEqual(await englishSystemLeaks(),[]);assert.equal(await page.locator('#export').isDisabled(),true);await page.click('#apply-back');
 appearanceFailure=true;await page.click('#language-toggle');await page.waitForFunction(()=>!savingAppearance);assert.equal(await page.locator('html').getAttribute('lang'),'en');appearanceFailure=false;
 await page.setViewportSize({width:380,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.click('#appearance-open');assert.deepEqual(await englishSystemLeaks(),[]);
 if(process.env.JEV_QA_OUTPUT){await page.click('[data-theme-choice=fresh]');await page.waitForFunction(()=>!savingAppearance);await page.setViewportSize({width:540,height:820});await page.evaluate(()=>document.querySelector('#toast').classList.remove('show'));await page.screenshot({path:process.env.JEV_QA_OUTPUT});}
 assert.equal(modelCalls,0);assert.deepEqual(errors,[]);console.log('PASS: zh/en, persistence, prompt isolation, live/retry/failure/apply states, narrow layout; zero model calls.');
}finally{await browser.close()}
