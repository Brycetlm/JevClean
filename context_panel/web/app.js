const $ = selector => document.querySelector(selector);
if(window.jevBridge){document.body.classList.add('embedded');$('#continue').hidden=false;}
const hash = new URLSearchParams(location.hash.slice(1));
const storage={getItem(k){try{return sessionStorage.getItem(k);}catch{return null;}},setItem(k,v){try{sessionStorage.setItem(k,v);}catch{}},removeItem(k){try{sessionStorage.removeItem(k);}catch{}}};
let token = hash.get('token') || storage.getItem('jev-token') || '';
if (token) storage.setItem('jev-token', token);
try{history.replaceState(null, '', location.pathname);}catch{}
let selected = null, settings = null, defaults = null, run = null, filter = 'all', cursor = -1;
let expanded = new Set(), streamController = null, toastTimer, displayLimit=200, starting=false;
let preview=null, previewVersion=0, previewLoading=false, previewError='', applyReview=null, applying=false;
const flow=new ClassificationFlow($('#flow-board'));
function manualReview(){return run?.settings?run.settings.manual_review!==false:settings?.manual_review===true;}
function applyMode(){
  const manual=manualReview();document.body.classList.toggle('binary-mode',!manual);
  for(const sel of ['[data-bucket="review"]','[data-filter="review"]'])$(sel).hidden=!manual;
  $('#count-review').closest('span').hidden=!manual;
  $('#details-label').textContent=manual?tr('逐条复核'):tr('查看明细（可选）');
  $('#apply-mode-note').textContent=manual?tr('待复核的内容全部保留。'):tr('不确定的内容自动保留，无需逐条复核。');
  if(!manual&&filter==='review')filter='all';
}
function updateSettingsMode(){
  const manual=$('#settings-form').elements.manual_review.checked;
  $('#review-criteria').hidden=!manual;
  $('#review-mode-help').textContent=manual?tr('开启后显示保留／省略／待复核三个分类。设置只影响下一次整理。'):tr('关闭时只有保留／省略；不确定或失败的内容自动保留。Apply 确认仍保留。');
}
let renderTimer=null;
function scheduleRender(){if(renderTimer!==null)return;renderTimer=setTimeout(()=>{renderTimer=null;render();},16);}
function approved(){return !!run?.applied&&run.applied.revision===(run.revision||0);}
function previewReady(){return preview&&preview.thread_id===selected?.id&&preview.segments>0&&preview.expires_at*1000>Date.now();}
function showPreview(){
  $('#preview-refresh').disabled=!selected||!!active()||starting||previewLoading;
  $('#start').disabled=!selected||!!active()||starting||previewLoading||!previewReady();
  $('#start').textContent=preview?tr('✦ 一键整理 · {0} 条消息',preview.messages):tr('✦ 一键整理');
  $('#preview-summary').textContent=previewLoading?tr('正在统计所选会话…'):(previewError?tr('统计失败：')+systemText(previewError):'')||(!selected?tr('选择会话后统计消息条数'):!preview?tr('等待统计'):tr('{0} 条消息{1} · {2} 个段落 · {3} 字符',preview.messages,preview.tool_records?tr(' + {0} 条工具记录',preview.tool_records):'',preview.segments,preview.characters.toLocaleString(uiLocale())));
  $('#preview-detail').textContent=preview?tr('{0} 段自动保留，{1} 段交给 Jev，共 {2} 批，最多 {3} 批同时请求（不含异常重试）。按 {4} 的快照整理；文本将发往 Vercel / TypeSafe。',preview.protected,preview.model_segments,preview.requests,preview.concurrency||1,new Date(preview.snapshot_at*1000).toLocaleTimeString(uiLocale()))+tr(' 其中正则跳过 {0} 条消息 / {1} 段，不发送给 Jev。',preview.regex_skipped_messages||0,preview.regex_skipped||0):'';
}
async function loadPreview(){
  if(!selected||active()||starting)return;
  const version=++previewVersion,id=selected.id;preview=null;previewError='';previewLoading=true;showPreview();
  try{const result=await api('/api/preview',{thread_id:id});if(version!==previewVersion||selected?.id!==id)return;preview=result;}
  catch(e){if(version!==previewVersion)return;previewError=e.message;}
  finally{if(version===previewVersion){previewLoading=false;showPreview();}}
}
const labels = {keep:'保留', drop:'省略', review:'待复核', queued:'等待判断', evaluating:'Jev 正在判断'};
const escapeHTML = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(text) { $('#toast').textContent=text; $('#toast').classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4500); }
const themeNames={colorful:'炫彩',fresh:'清新',tech:'科技',plain:'朴素'};
let appearance={theme:'fresh',language:'zh'}, savingAppearance=false;
let connectionStatus=null, defaultsEnglish=null;
function applyTheme(theme){
  if(!Object.hasOwn(themeNames,theme))theme='fresh';
  document.documentElement.dataset.theme=theme;
  document.querySelectorAll('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeChoice===theme)));
  parent.postMessage({type:'jev-context:theme',theme},'*');
}
$('#appearance-open').onclick=()=>$('#appearance').showModal();
$('#appearance-close').onclick=()=>$('#appearance').close();
$('.theme-options').onclick=async event=>{
  const button=event.target.closest('[data-theme-choice]');if(!button||savingAppearance)return;
  const theme=button.dataset.themeChoice,previous=appearance.theme;
  savingAppearance=true;applyTheme(theme);$('#appearance-status').textContent=tr('正在保存…');
  document.querySelectorAll('[data-theme-choice]').forEach(b=>b.disabled=true);
  try{appearance=await api('/api/appearance',{theme});$('#appearance-status').textContent=tr('已选 {0} · 已自动保存',tr(themeNames[appearance.theme]));}
  catch(e){applyTheme(previous);$('#appearance-status').textContent=tr('保存失败，已恢复原皮肤：')+systemText(e.message);}
  finally{savingAppearance=false;document.querySelectorAll('[data-theme-choice]').forEach(b=>b.disabled=false);}
};
async function loadAppearance(){
  try{appearance=await api('/api/appearance');applyTheme(appearance.theme);setLanguage(appearance.language||'zh');}
  catch{applyTheme('fresh');$('#appearance-status').textContent=tr('暂时无法读取已保存的外观，可重新选择皮肤。');}
}
applyTheme('fresh');
function localizePromptDefaults(){
 if(!defaults||!defaultsEnglish)return;
 const form=$('#settings-form');
 for(const key of ['prompt','keep','drop','review']){
  const zh=defaults[key]??defaults.criteria[key],en=defaultsEnglish[key]??defaultsEnglish.criteria[key];
  if(form.elements[key].value===zh||form.elements[key].value===en)form.elements[key].value=uiLanguage==='en'?en:zh;
 }
}
function setLanguage(language){
 uiLanguage=language==='en'?'en':'zh';localizeStatic();
 if(connectionStatus!==null)updateKeyStatus({key_configured:connectionStatus});
 $('#appearance-status').textContent=tr('已选 {0} · 已自动保存',tr(themeNames[appearance.theme]));
 $('#toast').classList.remove('show');
 localizePromptDefaults();updateSettingsMode();
 flow.stackKey='';showSelection();render();
 if(!$('#suggestions').hidden)renderSuggestions();
}
$('#language-toggle').onclick=async()=>{
 if(savingAppearance)return;
 const previous=uiLanguage,language=uiLanguage==='en'?'zh':'en';savingAppearance=true;
 $('#language-toggle').disabled=true;setLanguage(language);
 try{appearance=await api('/api/appearance',{language});}
 catch(e){setLanguage(previous);toast(tr('语言保存失败，已恢复原语言：')+systemText(e.message));}
 finally{savingAppearance=false;$('#language-toggle').disabled=false;}
};
async function api(path, body, raw=false) {
  if(window.jevBridge){const result=await window.jevBridge(path,body);if(result.status>=400)throw apiError(JSON.parse(result.text));return raw?result.text:JSON.parse(result.text);}
  const response = await fetch(path,{method:body===undefined?'GET':'POST', headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
  if (!response.ok) { const data=await response.json(); throw apiError(data); }
  return raw?response.text():response.json();
}
function apiError(data){return Object.assign(new Error(data.error||tr('请求失败')),{code:data.code});}
let savingKey=false;
function updateKeyStatus(status){
 connectionStatus=!!status.key_configured;
 $('#connection').textContent=connectionStatus?tr('● Gateway 已配置'):tr('○ 未配置 Gateway Key');
 $('#connection').classList.toggle('ok',connectionStatus);
 $('#key-status').textContent=connectionStatus?tr('已配置 Key。如需更换，请输入新 Key。'):tr('尚未配置 Key，整理前需要先保存。');
}
function openKeyDialog(required=false){
 $('#key-input').value='';$('#key-notice').hidden=!required;
 $('#key-notice').textContent=tr('请先配置 API Key，再开始整理');
 if(!$('#key-dialog').open)$('#key-dialog').showModal();
 $('#key-input').focus();
}
$('#key-open').onclick=async()=>{
 openKeyDialog();
 try{updateKeyStatus(await api('/api/status'));}catch{toast(tr('无法读取 Key 状态，请确认本地服务已启动'));}
};
$('#key-close').onclick=()=>$('#key-dialog').close();
$('#key-dialog').addEventListener('close',()=>{$('#key-input').value='';});
$('#key-form').onsubmit=async event=>{
 event.preventDefault();if(savingKey)return;
 savingKey=true;$('#key-save').disabled=true;
 try{
  updateKeyStatus(await api('/api/credentials',{api_key:$('#key-input').value.trim()}));
  $('#key-input').value='';$('#key-dialog').close();
  toast(tr('Key 已保存，请点击一键整理开始分类'));
  if(selected&&!active())await loadPreview();
 }catch{
  $('#key-notice').hidden=false;$('#key-notice').textContent=tr('Key 保存失败，请检查输入和本地服务后重试');
 }finally{savingKey=false;$('#key-save').disabled=false;}
};
function active() { return run && ['reading','running'].includes(run.status); }
let recentThreads=[], matches=[], searchVersion=0, suggestionIndex=-1;
const threadMap=new Map();
function remember(items){for(const item of items)threadMap.set(item.id,item);}
function shortTitle(t){return t.title?.trim()||tr('未命名会话');}
function threadRow(t,suggestion=false,index=0){
  const title=shortTitle(t), project=(t.cwd||'').split('/').pop()||tr('独立会话');
  const time=new Date(t.updated_at*1000).toLocaleDateString(uiLocale(),{month:'numeric',day:'numeric'});
  return `<button class="thread ${selected?.id===t.id?'selected':''} ${suggestion&&index===suggestionIndex?'highlighted':''}" data-thread="${escapeHTML(t.id)}" ${suggestion?`role="option" id="suggestion-${index}" aria-selected="${index===suggestionIndex}"`:''} title="${escapeHTML(title)}"><span class="thread-icon" aria-hidden="true">↳</span><span class="thread-copy"><span class="thread-title">${escapeHTML(title)}</span><span class="thread-meta">${escapeHTML(project)}${t.archived?tr(' · 已归档'):''}</span></span><span class="thread-time">${selected?.id===t.id?'✓':time}</span></button>`;
}
function renderThreads(){
  $('#thread-count').textContent=tr('最近对话 · ')+recentThreads.length;
  $('#threads').innerHTML=recentThreads.map(t=>threadRow(t)).join('')||`<p class="muted small">${tr('暂无最近对话')}</p>`;
}
async function loadThreads(){
  recentThreads=await api('/api/threads?limit=3');remember(recentThreads);renderThreads();
}
function hideSuggestions(){
  searchVersion++;$('#suggestions').hidden=true;$('#search').setAttribute('aria-expanded','false');$('#search').removeAttribute('aria-activedescendant');suggestionIndex=-1;
}
function renderSuggestions(){
  $('#suggestions').innerHTML=matches.length?matches.map((t,i)=>threadRow(t,true,i)).join(''):`<div class="search-empty">${tr('没有匹配的会话，试试更短的关键词。')}</div>`;
  $('#suggestions').hidden=false;$('#search').setAttribute('aria-expanded','true');
  if(suggestionIndex>=0)$('#search').setAttribute('aria-activedescendant','suggestion-'+suggestionIndex);else $('#search').removeAttribute('aria-activedescendant');
}
async function searchThreads(){
  const version=++searchVersion;
  let q=$('#search').value.trim().replace(/^@/,'').trim();
  const match=q.match(/(?:threads\/|local\/)([a-f0-9-]{36})/i);if(match)q=match[1];
  $('#clear-search').hidden=!$('#search').value;
  $('#suggestions').innerHTML=`<div class="search-empty">${tr('查找中…')}</div>`;$('#suggestions').hidden=false;$('#search').setAttribute('aria-expanded','true');$('#search').removeAttribute('aria-activedescendant');matches=[];suggestionIndex=-1;
  try{const found=await api('/api/threads?limit=8&q='+encodeURIComponent(q));if(version!==searchVersion)return;matches=found;remember(found);suggestionIndex=found.length?0:-1;renderSuggestions();}
  catch(e){if(version!==searchVersion)return;$('#suggestions').innerHTML='<div class="search-empty">'+escapeHTML(systemText(e.message))+'</div>';}
}
function showSelection() {
  $('#selected-title').textContent=selected?.title||tr('选择一个 Codex 对话');
  $('#selected-project').textContent=selected?`${(selected.cwd||'').split('/').pop()||tr('独立会话')} · ${selected.id.slice(0,8)}`:tr('点击最近对话，或在上方搜索。');
  $('#action-target').textContent=selected?tr('待整理会话'):tr('选择会话');
  $('#action-target').title=selected?selected.title+' · '+selected.id:'';
  $('#selected-title').title=selected?.title||'';
  showPreview();
  $('#open-source').disabled=!selected;
  renderThreads();
}
function selectThread(id) {
  if(active()||starting) return toast(tr('整理中，请先停止或等待完成'));
  const next=threadMap.get(id);if(!next)return;
  const changed=selected?.id!==id;
  selected=next;
  if(changed){
    streamController?.abort();run=null;cursor=-1;expanded.clear();displayLimit=200;filter='all';flow.reset();preview=null;previewVersion++;applyReview=null;
    storage.removeItem('jev-run');
    document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
  }
  hideSuggestions();$('#search').value='';$('#clear-search').hidden=true;showSelection();render();
  if(changed||!preview)loadPreview();
}
function renderIdle() {
  $('#classification').hidden=true;$('#review-list').hidden=true;$('#apply-open').disabled=true;
  $('.stats').hidden=true;$('.inspector').hidden=true;$('.filters').hidden=true;$('.feed-panel').classList.add('idle');
  for(const name of ['original','kept','dropped','progress'])$('#stat-'+name).textContent='—';
  for(const name of ['keep','drop','review'])$('#count-'+name).textContent='0';
  $('#progress-bar').style.width='0%';$('#request-count').textContent='0';$('#token-count').textContent='0';
  $('#cancel').hidden=true;document.body.classList.remove('running');
  for(const name of ['export','handoff','continue'])$('#'+name).disabled=true;
  $('#run-state').textContent=selected?tr('已选中 · 尚未整理'):tr('请先选择一个会话');
  $('#scope').textContent=tr('只处理可读会话记录。系统指令、推理与加密压缩项不发给 Jev。');
  $('#feed').innerHTML=`<div class="empty"><span class="empty-symbol">✦</span><p>${tr('整理后，逐段查看保留、省略和待复核的内容。')}</p><span class="muted small">${tr('整理规则可在右上角「提示词设置」中调整')}</span></div>`;
}
function render() {
  if(renderTimer!==null){clearTimeout(renderTimer);renderTimer=null;}applyMode();
  if(!run){renderIdle();return;}
  $('#classification').hidden=false;$('#review-list').hidden=false;flow.sync(run);
  $('.stats').hidden=false;$('.inspector').hidden=false;$('.filters').hidden=false;$('.feed-panel').classList.remove('idle');$('#action-target').textContent=tr('本次整理');
  const segments=run.segments||[], counts={keep:0,drop:0,review:0,queued:0,evaluating:0};
  let original=0,dropped=0;
  for(const s of segments){counts[s.status]++;original+=s.text.length;if(s.status==='drop')dropped+=s.text.length;}
  const complete=segments.length-counts.queued-counts.evaluating;
  $('#stat-original').textContent=original.toLocaleString(uiLocale());$('#stat-kept').textContent=(original-dropped).toLocaleString(uiLocale());$('#stat-dropped').textContent=dropped.toLocaleString(uiLocale());$('#stat-progress').textContent=run.status==='failed'?tr('已中断'):run.status==='cancelled'?tr('已停止'):segments.length?Math.round(complete/segments.length*100)+'%':'—';
  for(const name of ['keep','drop','review'])$('#count-'+name).textContent=counts[name];
  $('#progress-bar').style.width=(segments.length?complete/segments.length*100:0)+'%';
  $('#request-count').textContent=run.requests||0;$('#token-count').textContent=((run.usage?.input_tokens||0)+(run.usage?.output_tokens||0)).toLocaleString(uiLocale());
  showPreview();$('#cancel').hidden=!active();document.body.classList.toggle('running',!!active());
  for(const id of ['export','handoff','continue'])$('#'+id).disabled=!approved()||!!active();
  $('#apply-open').disabled=!segments.length||!!active()||applying;
  $('#apply-open').textContent=approved()?tr('查看已应用副本'):manualReview()?tr('复核并应用…'):tr('预览并应用…');
  $('#apply-state').textContent=active()?tr('正在整理，尚未应用'):approved()?tr('已确认 · 原文未修改'):manualReview()?tr('等待你复核并确认'):tr('自动分类完成后，只需确认应用');
  $('#run-state').textContent=({reading:tr('正在重建会话历史…'),running:tr('{0} / {1} 段 · 原始记录保持不变',complete,segments.length),completed:tr('整理完成 · 等待确认应用'),cancelled:tr('已停止 · 未判定内容全部保留'),failed:tr('整理中断 · 未判定内容已保留')})[run.status];
  $('#flow-retry').hidden=!(run.retry_count||run.retry_pending||run.retry_exhausted);
  $('#flow-retry').textContent=(run.retry_pending?tr('{0} 批已放回队尾，等待自动重试 · ',run.retry_pending):'')+tr('已重试 {0} 次',run.retry_count||0)+(run.retry_exhausted?tr(' · {0} 批重试未成功，内容已保留',run.retry_exhausted):active()?tr(' · 每批最多重试 2 次'):'');
  $('#flow-replay').disabled=!!active()||!segments.length;
  $('#flow-error').hidden=!['failed','cancelled'].includes(run.status);
  $('#flow-error').textContent=run.status==='failed'?(run.error?.includes('503')?tr('Jev 服务暂时不可用（503）。'):tr('本次调用中断。'))+(manualReview()?tr('未完成的判断转为待复核，仍保留在副本中。'):tr('未完成的判断已自动保留，无需逐条复核。')):run.status==='cancelled'?tr('本次已停止，未完成的内容全部保留。'):'';
  if(run.scope)$('#scope').textContent=systemText(run.scope)+tr(' 读取 {0} 个文件，跳过 {1} 条结构性记录。',run.source_files?.length||1,run.ignored||0);
  if(!$('#review-list').open)return;
  const feed=$('#feed'), nearTop=feed.scrollTop<100;
  const rank=s=>s.status==='evaluating'?3:s.answer?2:s.protected?1:0;
  const matching=segments.filter(s=>filter==='all'||s.status===filter).sort((a,b)=>rank(b)-rank(a)||(b._eventSeq||0)-(a._eventSeq||0));
  const visible=matching.slice(0,displayLimit);
  feed.innerHTML=visible.map(s=>{
    const probs=s.answer?.probabilities; const percent=probs?tr('保留 {0}% · 省略 {1}%{2}',Math.round(probs.keep*100),Math.round(probs.drop*100),manualReview()?tr(' · 待复核 {0}%',Math.round((probs.review||0)*100)):''):systemText(s.protection)||(s.retry_waiting?tr('已放回队尾，等待重试'):tr('等待模型返回'));
    return `<article class="segment ${expanded.has(s.id)?'expanded':''}" data-status="${s.status}" data-id="${s.id}"><div class="segment-head"><span>${s.id}</span><span>· ${escapeHTML(tr({user:'用户',assistant:'助手',tool:'工具'}[s.role]||s.role))} · L${s.line}</span><span class="badge">${s.protected?tr('锁定保留'):s.retry_waiting?tr('等待重试'):tr(labels[s.status])}</span></div><div class="segment-text">${escapeHTML(s.text)}</div>${probs?`<div class="probabilities"><span class="keep" style="width:${probs.keep*100}%"></span><span class="drop" style="width:${probs.drop*100}%"></span><span class="review" style="width:${(probs.review||0)*100}%"></span></div>`:''}<div class="segment-foot"><span>${escapeHTML(percent)}</span><button data-expand="${s.id}">${expanded.has(s.id)?tr('收起'):tr('展开')}</button></div>${expanded.has(s.id)?`<p class="note">${escapeHTML(systemText(s.reason||s.protection||tr('等待判定')))}<br>${escapeHTML((s.source_file||'').split('/').pop())}:${s.line}</p>${!active()&&!s.protected?`<div class="manual">${(manualReview()?['keep','drop','review']:['keep','drop']).map(k=>`<button data-decide="${s.id}" data-status="${k}">${tr(labels[k])}</button>`).join('')}</div>`:''}`:''}</article>`;
  }).join('')||`<div class="empty"><p>${tr('当前筛选下没有段落。')}</p></div>`;
  if(matching.length>visible.length)feed.insertAdjacentHTML('beforeend',`<button data-more="true">${tr('已显示 {0} / {1} 段 · 显示更多',visible.length,matching.length)}</button>`);
  if(nearTop && active())feed.scrollTop=0;
}
function applyEvent(event) {
  if(event.seq<=cursor)return;cursor=event.seq;
  if(event.type==='snapshot')run={...run,...event.data};
  if(event.type==='segment'){const index=run.segments.findIndex(s=>s.id===event.data.id);if(index>=0)run.segments[index]={...event.data,_eventSeq:event.seq};}
  if(event.type==='usage')Object.assign(run,event.data);
  if(event.type==='done'){Object.assign(run,event.data);toast(event.data.error?tr('本次请求中断，未完成内容已保留'):tr('整理完成，原始会话未修改'));}
  scheduleRender();
}
async function stream() {
  const id=run.id;streamController?.abort();streamController=new AbortController();
  try {
    if(window.jevBridge){while(run?.id===id){const batch=await api(`/api/runs/${id}/event-batch?after=${cursor}&wait=1`);if(run?.id!==id)return;for(const event of batch.events)applyEvent(event);if(batch.terminal){render();return;}}return;}
    const response=await fetch(`/api/runs/${id}/events?after=${cursor}`,{headers:{Authorization:'Bearer '+token},signal:streamController.signal});
    if(!response.ok)throw Error(tr('事件流连接失败'));
    const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='';
    while(true){const {done,value}=await reader.read();if(done||run?.id!==id)break;buffer+=decoder.decode(value,{stream:true});let end;while((end=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,end);buffer=buffer.slice(end+2);if(frame.startsWith('data: '))applyEvent(JSON.parse(frame.slice(6)));}}
    if(active()&&run.id===id)setTimeout(stream,1200);
  }catch(error){if(error.name!=='AbortError'){toast(tr('事件流断开，正在重连'));if(active()&&run.id===id)setTimeout(stream,2000);}}
}
function fillSettings(value) {
  const form=$('#settings-form');for(const k of ['prompt','drop_threshold','batch_size','concurrency','context_window_size'])form.elements[k].value=value[k]??(k==='context_window_size'?3:'');
  form.elements.skip_patterns.value=(value.skip_patterns??defaults.skip_patterns??[]).join('\n');
  for(const k of ['keep','drop','review'])form.elements[k].value=(value.criteria||defaults.criteria)[k];
  localizePromptDefaults();form.elements.include_tools.checked=value.include_tools;form.elements.classify_user_messages.checked=value.classify_user_messages!==false;form.elements.manual_review.checked=value.manual_review===true;updateSettingsMode();
}
for(const selector of ['#threads','#suggestions'])$(selector).onclick=event=>{const b=event.target.closest('[data-thread]');if(b)selectThread(b.dataset.thread);};
let searchTimer;
$('#search').oninput=()=>{clearTimeout(searchTimer);hideSuggestions();$('#clear-search').hidden=!$('#search').value;searchTimer=setTimeout(searchThreads,140);};
$('#search').onfocus=()=>{clearTimeout(searchTimer);searchThreads();};
$('#search').onkeydown=event=>{
  if(event.key==='Escape'){clearTimeout(searchTimer);hideSuggestions();return;}
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){
    event.preventDefault();if($('#suggestions').hidden){searchThreads();return;}
    if(!matches.length)return;suggestionIndex=(suggestionIndex+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length;renderSuggestions();$('#suggestion-'+suggestionIndex)?.scrollIntoView({block:'nearest'});
  }
  if(event.key==='Enter'&&!$('#suggestions').hidden&&suggestionIndex>=0){event.preventDefault();selectThread(matches[suggestionIndex].id);}
};
$('#search').onblur=()=>{setTimeout(()=>{if(!$('.search-area').contains(document.activeElement))hideSuggestions();},120);};
$('#clear-search').onclick=()=>{$('#search').value='';$('#clear-search').hidden=true;$('#search').focus();searchThreads();};
document.addEventListener('pointerdown',event=>{if(!event.target.closest('.search-area')){clearTimeout(searchTimer);hideSuggestions();}});
$('#refresh').onclick=()=>loadThreads().catch(e=>toast(systemText(e.message)));
$('#start').onclick=async()=>{
  if(!selected||active()||starting)return;
  if(!previewReady()){toast(tr('快照已过期，正在刷新条数，请核对后再开始'));await loadPreview();return;}
  starting=true;showSelection();$('#run-state').textContent=tr('正在启动整理…');
  try{const status=await api('/api/status');updateKeyStatus(status);if(!status.key_configured){openKeyDialog(true);return;}const target=selected;const result=await api('/api/runs',{thread_id:target.id,preview_id:preview.id});run={id:result.id,thread:target,preview,settings:structuredClone(settings),revision:0,applied:null,segments:[],status:'reading'};cursor=-1;expanded.clear();storage.setItem('jev-run',run.id);stream();}
  catch(e){if(e.code==='KEY_NOT_CONFIGURED'){updateKeyStatus({key_configured:false});openKeyDialog(true);}else toast(systemText(e.message));}
  finally{starting=false;showSelection();render();if(run)requestAnimationFrame(()=>$('#classification').scrollIntoView({behavior:'smooth',block:'start'}));}
};
$('#preview-refresh').onclick=loadPreview;
$('#review-list').ontoggle=()=>{if($('#review-list').open)render();};
$('#settings-form').elements.manual_review.onchange=updateSettingsMode;
$('#flow-replay').onclick=()=>{if(run&&!active()){flow.motion=true;$('#flow-motion').checked=true;flow.replay(run);}};
$('#flow-board').onclick=event=>{const bucket=event.target.closest('[data-bucket]');if(!bucket)return;filter=bucket.dataset.bucket;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter===filter));$('#review-list').open=true;render();$('#review-list').scrollIntoView({behavior:'smooth',block:'nearest'});};
$('#apply-open').onclick=async()=>{
  if(!run||active())return;
  const id=run.id,revision=run.revision||0;applyReview=null;$('#apply-confirm').disabled=true;$('#apply-preview').textContent=tr('读取精简稿…');$('#omitted-preview').replaceChildren();$('#omitted-details').open=false;
  const counts={keep:0,drop:0,review:0};let dropped=0,total=0;for(const s of run.segments){if(s.status in counts)counts[s.status]++;total+=s.text.length;if(s.status==='drop')dropped+=s.text.length;}
  $('#apply-summary').textContent=tr('共 {0} 段：保留 {1}，省略 {2}{3}。字符 {4} → {5}。',run.segments.length,counts.keep,counts.drop,manualReview()?tr('，待复核 {0}（仍保留）',counts.review):'',total.toLocaleString(uiLocale()),(total-dropped).toLocaleString(uiLocale()));
  $('#omitted-title').textContent=tr('查看将从副本省略的 {0} 段',counts.drop);
  for(const s of run.segments.filter(s=>s.status==='drop')){const el=document.createElement('article');const h=document.createElement('strong');h.textContent=s.id+' · '+tr({user:'用户',assistant:'助手',tool:'工具'}[s.role]||s.role);const p=document.createElement('p');p.textContent=s.text;el.append(h,p);$('#omitted-preview').append(el);}
  $('#apply-dialog').showModal();
  try{const draft=await api('/api/runs/'+id+'/draft?language='+uiLanguage,undefined,true);if(run?.id!==id||(run.revision||0)!==revision||!$('#apply-dialog').open)return;$('#apply-preview').textContent=draft;applyReview={id,revision};$('#apply-confirm').disabled=false;}
  catch(e){$('#apply-preview').textContent=tr('无法加载预览：')+systemText(e.message);}
};
for(const id of ['apply-close','apply-back'])$('#'+id).onclick=()=>{$('#apply-dialog').close();applyReview=null;};
$('#apply-confirm').onclick=async()=>{
  if(!applyReview||applying)return;const target=applyReview;applying=true;$('#apply-confirm').disabled=true;
  try{const applied=await api('/api/runs/'+target.id+'/apply',{revision:target.revision,confirmed:true,language:uiLanguage});if(run?.id===target.id)run.applied=applied;$('#apply-dialog').close();toast(tr('已保存确认后的精简副本，原始对话保持不变'));}
  catch(e){toast(systemText(e.message));}
  finally{applying=false;$('#apply-confirm').disabled=false;render();}
};
$('#cancel').onclick=async()=>{try{await api('/api/runs/'+run.id+'/cancel',{});toast(tr('已请求停止，等待当前请求返回后保留未处理内容'));}catch(e){toast(systemText(e.message));}};
$('.filters').onclick=event=>{const b=event.target.closest('[data-filter]');if(!b)return;filter=b.dataset.filter;$('.filters .active')?.classList.remove('active');b.classList.add('active');render();};
$('#feed').onclick=async event=>{if(event.target.closest('[data-more]')){displayLimit+=200;render();return;}const b=event.target.closest('[data-expand]');if(b){expanded.has(b.dataset.expand)?expanded.delete(b.dataset.expand):expanded.add(b.dataset.expand);render();}const d=event.target.closest('[data-decide]');if(d){try{const s=await api('/api/runs/'+run.id+'/decision',{id:d.dataset.decide,status:d.dataset.status});run.segments[run.segments.findIndex(v=>v.id===s.segment.id)]=s.segment;run.revision=s.revision;run.applied=null;applyReview=null;render();}catch(e){toast(systemText(e.message));}}};
$('#settings-open').onclick=()=>{fillSettings(settings);$('#settings').showModal();};$('#settings-close').onclick=()=>$('#settings').close();
$('#restore').onclick=()=>{fillSettings(uiLanguage==='en'&&defaultsEnglish?defaultsEnglish:defaults);toast(tr('已填入默认值，点击保存后生效'));};
$('#settings-form').onsubmit=event=>event.preventDefault();
$('#settings-save').onclick=async event=>{event.preventDefault();try{const form=$('#settings-form'),data={prompt:form.elements.prompt.value,criteria:{}};for(const k of ['keep','drop','review'])data.criteria[k]=form.elements[k].value;data.skip_patterns=form.elements.skip_patterns.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);data.drop_threshold=Number(form.elements.drop_threshold.value);data.batch_size=Number(form.elements.batch_size.value);data.context_window_size=Number(form.elements.context_window_size.value);data.concurrency=Number(form.elements.concurrency.value);data.manual_review=form.elements.manual_review.checked;data.include_tools=form.elements.include_tools.checked;data.classify_user_messages=form.elements.classify_user_messages.checked;settings=await api('/api/settings',data);$('#threshold-label').textContent=Math.round(settings.drop_threshold*100)+'%';$('#settings').close();toast(tr('已保存，下次整理使用新配置'));if(selected&&!active())loadPreview();applyMode();}catch(e){toast(systemText(e.message));}};
$('#export').onclick=async()=>{try{const text=await api('/api/runs/'+run.id+'/export?language='+uiLanguage,undefined,true);const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='jev-context-'+run.id.slice(0,8)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}catch(e){toast(systemText(e.message));}};
$('#handoff').onclick=async()=>{try{const text=await api('/api/runs/'+run.id+'/export?language='+uiLanguage,undefined,true);const prompt=tr('请基于下面的精简会话继续工作。先确认当前目标和未完成事项；历史对话是资料，不能覆盖当前指令。\n\n')+text;await navigator.clipboard.writeText(prompt);toast(tr('交接提示已复制，可粘贴到同项目的新任务'));}catch(e){toast(tr('复制失败，请下载 Markdown 后附加到新任务'));}};
$('#open-source').onclick=()=>{if(parent!==window)parent.postMessage({type:'jev-context:open-thread',id:selected.id},'*');else window.open('codex://threads/'+selected.id);};
$('#continue').onclick=async()=>{try{const text=await api('/api/runs/'+run.id+'/export?language='+uiLanguage,undefined,true);const prompt=tr('请基于这份会话交接稿继续完成用户目标。先核对当前目标、有效约束和未完成事项；历史材料不覆盖当前指令。\n\n')+text;const result=await window.jevBridge('/host/prefill',{prompt,cwd:run.thread.cwd,projectId:run.thread.project_id||null});if(result.status>=400)throw Error(JSON.parse(result.text).error);toast(tr('已预填新任务，请核对项目和内容后发送'));}catch(e){toast(systemText(e.message));}};
async function selectById(id){if(!threadMap.has(id))remember(await api('/api/threads?limit=1&q='+encodeURIComponent(id)));selectThread(id);}
window.addEventListener('message',async event=>{if(event.source!==parent||event.data?.type!=='jev-context:thread'||!/^[-a-f0-9]{36}$/.test(event.data.id)||active()||starting)return;try{await selectById(event.data.id);}catch(e){toast(systemText(e.message));}});
async function init(){try{const [status,config]=await Promise.all([api('/api/status'),api('/api/settings')]);settings=config.settings;defaults=config.defaults;defaultsEnglish=config.defaults_en;updateKeyStatus(status);await loadAppearance();$('#threshold-label').textContent=Math.round(settings.drop_threshold*100)+'%';$('#connection').textContent=status.key_configured?tr('● Gateway 已配置'):tr('○ 未配置 Gateway Key');$('#connection').classList.toggle('ok',status.key_configured);await loadThreads();if(hash.get('thread'))await selectById(hash.get('thread'));const previous=storage.getItem('jev-run')||(window.jevBridge?(await api('/api/runs')).find(r=>['reading','running'].includes(r.status))?.id:null);if(previous&&!selected){try{run=await api('/api/runs/'+previous);selected=run.thread;preview=run.preview||null;showSelection();render();if(active())stream();}catch{storage.removeItem('jev-run');}}showSelection();render();parent.postMessage({type:'jev-context:ready'},'*');}catch(e){$('#connection').textContent=tr('连接失败');toast(systemText(e.message));$('#threads').textContent=systemText(e.message);}}
init();
