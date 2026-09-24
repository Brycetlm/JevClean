// Presentation only: every flight is backed by a terminal segment decision.
class ClassificationFlow {
  constructor(root) {
    this.root=root;this.queue=[];this.seen=new Map();this.flights=new Set();this.timer=null;this.runId=null;this.segments=[];this.replaying=false;this.stackKey='';
    this.motion=!matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelector('#flow-motion').checked=this.motion;
    document.querySelector('#flow-motion').onchange=event=>{this.motion=event.target.checked;if(!this.motion)this.flush();};
    this.visibility=()=>{if(document.hidden)this.flush();};document.addEventListener('visibilitychange',this.visibility);
  }
  reset() {
    clearTimeout(this.timer);this.timer=null;this.queue=[];this.seen.clear();this.segments=[];this.runId=null;this.replaying=false;this.stackKey='';
    for(const flight of this.flights){flight.animation.cancel();flight.node.remove();}this.flights.clear();
    for(const bucket of this.root.querySelectorAll('.bucket')){bucket.querySelector('b').textContent='0';bucket.querySelector('.bucket-bar i').style.width='0%';bucket.querySelector('.bucket-last').textContent=tr('等待归类');}
    this.stack();
  }
  sync(run) {
    if(this.runId!==run.id){this.reset();this.runId=run.id;}
    this.segments=run.segments||[];
    const counts={keep:0,drop:0,review:0};
    for(const s of this.segments){
      if(!(s.status in counts))continue;counts[s.status]++;
      if(this.seen.get(s.id)!==s.status){this.seen.set(s.id,s.status);if(this.motion&&!document.hidden)this.queue.push({...s});}
    }
    for(const status of Object.keys(counts)){
      const bucket=this.root.querySelector('[data-bucket="'+status+'"]');bucket.querySelector('b').textContent=counts[status];
      bucket.querySelector('.bucket-bar i').style.width=(this.segments.length?counts[status]/this.segments.length*100:0)+'%';
      const latest=this.segments.findLast(s=>s.status===status);bucket.querySelector('.bucket-last').textContent=latest?latest.id+' · '+latest.text.slice(0,30):tr('等待归类');
    }
    this.stack();this.pump();
  }
  stack(){
    const root=this.root.querySelector('.waterfall');
    const ids=new Set();const cards=[];
    for(const s of [...this.queue,...this.segments.filter(s=>s.status==='evaluating'),...this.segments.filter(s=>s.status==='queued')]){
      if(ids.has(s.id))continue;ids.add(s.id);cards.push(s);if(cards.length===4)break;
    }
    const key=cards.map(s=>s.id+':'+s.status+':'+!!s.retry_waiting+':'+uiLanguage).join('|')+'#'+!!this.segments.length;
    if(key!==this.stackKey){
      this.stackKey=key;root.replaceChildren();
      for(const s of cards)root.append(this.card(s));
      if(!cards.length){const empty=document.createElement('div');empty.className='flow-empty';empty.textContent=this.segments.length?tr('✓ 已全部归类'):tr('等待开始整理');root.append(empty);}
    }
    const waiting=this.segments.filter(s=>['queued','evaluating'].includes(s.status)).length;
    document.querySelector('#flow-state').textContent=(this.replaying?tr('本次结果回放 · 不调用模型 · '):'')+(waiting?tr('{0} 段等待判断',waiting):(this.queue.length||this.flights.size)?tr('结果已返回 · 正在展示归类'):tr('真实结果 · 每张卡片对应一段'));
  }
  replay(run){this.reset();this.replaying=true;this.runId=run.id;this.sync(run);}
  card(s){
    const card=document.createElement('div');card.className='flow-card';card.dataset.segment=s.id;
    const meta=document.createElement('div');meta.className='flow-card-meta';meta.textContent=s.id+' · '+({user:tr('用户'),assistant:tr('助手'),tool:tr('工具')}[s.role]||s.role)+(s.protected?tr(' · 自动保留'):s.status==='evaluating'?tr(' · 判断中'):s.retry_waiting?tr(' · 等待重试'):'');
    const body=document.createElement('p');body.textContent=s.text.slice(0,140);card.append(meta,body);return card;
  }
  pump(){
    if(this.timer||!this.queue.length)return;
    const tick=()=>{
      this.timer=null;
      if(!this.motion||document.hidden){this.flush();return;}
      if(this.flights.size<16&&this.queue.length)this.fly(this.queue.shift());
      this.stack();if(this.queue.length)this.timer=setTimeout(tick,this.queue.length>12?18:48);
    };this.timer=setTimeout(tick,16);
  }
  fly(s){
    const source=this.root.querySelector('.flow-card')||this.root.querySelector('.waterfall');
    const target=this.root.querySelector('[data-bucket="'+s.status+'"]');
    const r=this.root.getBoundingClientRect(),a=source.getBoundingClientRect(),b=target.getBoundingClientRect();
    const node=this.card(s);node.classList.add('flying','to-'+s.status);
    Object.assign(node.style,{left:(a.left-r.left)+'px',top:(a.top-r.top)+'px',width:a.width+'px'});this.root.querySelector('.flight-layer').append(node);
    const dx=b.left+b.width/2-a.left-a.width/2,dy=b.top+b.height/2-a.top-a.height/2;
    const animation=node.animate([{transform:'translate(0,0) scale(1)',opacity:.95},{transform:`translate(${dx*.48}px,${dy*.25-12}px) scale(.82)`,opacity:1,offset:.45},{transform:`translate(${dx}px,${dy}px) scale(.18)`,opacity:0}],{duration:380,easing:'cubic-bezier(.35,0,.3,1)',fill:'forwards'});
    const flight={node,animation};this.flights.add(flight);
    animation.finished.then(()=>{node.remove();this.flights.delete(flight);target.animate([{filter:'brightness(1.8)',transform:'scale(1.025)'},{filter:'brightness(1)',transform:'scale(1)'}],{duration:260});this.stack();}).catch(()=>{});
  }
  flush(){clearTimeout(this.timer);this.timer=null;this.queue=[];for(const f of this.flights){f.animation.cancel();f.node.remove();}this.flights.clear();this.stack();}
}
window.ClassificationFlow=ClassificationFlow;
