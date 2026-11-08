// api/search.js - Vercel serverless function (events only)
// Usage: /api/search?q=jazz this weekend in plett
import fs from 'fs';
import path from 'path';

// ===== BRAIN (shared search logic) =====
const BRAIN_TOWNS=[['plettenberg','Plett'],['plett','Plett'],['knysna','Knysna'],['george','George'],['sedgefield','Sedgefield'],['wilderness','Wilderness'],['mossel','Mossel Bay']];
function brainTown(text){ const t=String(text||'').toLowerCase(); for(const [k,v] of BRAIN_TOWNS) if(t.includes(k)) return v; return null; }
const BRAIN_TAGS={
  foodie:/\b(market|markets|food|wine|braai|farm|farmers|oyster|oysters|tasting|brunch)\b/,
  music:/jazz|music|concert|\b(dj|band|gig|choir)\b/,
  family:/\b(kids|children|family|easter|school)\b/,
  adventure:/\b(hike|hiking|trail|surf|surfing|adventure|run|running|bike|biking|cycle|cycling|marathon|kayak)\b/,
  culture:/\b(art|arts|gallery|theatre|theater|book|books|poetry|museum|heritage)\b/,
  romantic:/\b(romantic|sunset|couple|couples)\b/,
  free:/\bfree\b/
};
const BRAIN_QUERY=[
  [/\b(jazz|music|concert|concerts|band|gig)\b/,'music'],
  [/\b(market|markets|food|foodie|wine|braai|oysters?)\b/,'foodie'],
  [/\b(kids|children|family)\b/,'family'],
  [/\b(hike|hiking|trail|surf|surfing|adventure|run|running|bike|cycling|marathon|kayak)\b/,'adventure'],
  [/\b(art|arts|gallery|theatre|theater|poetry|museum|culture)\b/,'culture'],
  [/\b(romantic|sunset|couples?|date night)\b/,'romantic']
];
const BRAIN_STOP=new Set(['what','whats','the','and','for','are','any','some','there','this','that','with','show','find','tell','list','all','near','events','event','things','thing','happening','going','upcoming','weekend','today','tonight','week','next','free','can','you','have','got','does','about','where','when','how','anything','something','nice','good','best','plan']);
const BRAIN_TOWN_WORDS=['knysna','plett','plettenberg','bay','george','sedgefield','wilderness','mossel'];
const MON=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];

function brainTags(e){
  const text=((e.title||e.name||'')+' '+(e.description||e.desc||'')+' '+(e.category||'')+' '+(e.date||'')).toLowerCase();
  return Object.keys(BRAIN_TAGS).filter(k=>BRAIN_TAGS[k].test(text));
}
function brainParse(text){
  const lower=String(text||'').toLowerCase().replace(/’/g,"'");
  let when=null;
  if(/\bweekend\b/.test(lower)) when='weekend';
  else if(/\b(today|tonight)\b/.test(lower)) when='today';
  else if(/\b(this|next) week\b|\bnext 7 days\b/.test(lower)) when='week';
  const vibes=[]; for(const [re,v] of BRAIN_QUERY) if(re.test(lower)&&!vibes.includes(v)) vibes.push(v);
  const words=(lower.replace(/'/g,'').match(/[a-z0-9]+/g)||[]).filter(w=>w.length>=3&&!BRAIN_STOP.has(w)&&!BRAIN_TOWN_WORDS.includes(w));
  return {town:brainTown(lower),when,free:/\bfree\b/.test(lower),vibes,keywords:[...new Set(words)]};
}
function brainWindow(when,now){
  const d0=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const end=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate(),23,59,59,999);
  const add=(d,n)=>{ const x=new Date(d); x.setDate(x.getDate()+n); return x; };
  if(when==='today') return [[d0,end(d0)]];
  if(when==='week') return [[d0,end(add(d0,7))]];
  if(when==='weekend'){
    const dow=d0.getDay();
    if(dow===6) return [[d0,end(add(d0,1))]];
    const sat=add(d0,(6-dow+7)%7);
    const next=[sat,end(add(sat,1))];
    return dow===0?[[d0,end(d0)],next]:[next];
  }
  return null;
}
function brainDates(e,now){
  if(e.start_date){
    const a=new Date(e.start_date+'T00:00:00'), b=new Date((e.end_date||e.start_date)+'T23:59:59');
    if(!isNaN(a)&&!isNaN(b)) return {a,b};
  }
  const s=String(e.date||'').toLowerCase().replace(/(\d)(st|nd|rd|th)\b/g,'$1');
  if(!s||/see link/.test(s)) return null;
  if(/\bdaily\b|\bevery day\b/.test(s)) return {always:true};
  const eod=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate(),23,59,59);
  let m=s.match(/(\d{4})-(\d{2})-(\d{2})/);
  if(m){ const d=new Date(+m[1],+m[2]-1,+m[3]); return {a:d,b:eod(d)}; }
  const mon=w=>MON.indexOf(w.slice(0,3));
  const cut=new Date(now.getFullYear(),now.getMonth(),now.getDate()-60);
  const mk=(d,mi,y)=>{ let dt=new Date(y||now.getFullYear(),mi,d); if(!y&&dt<cut) dt=new Date(now.getFullYear()+1,mi,d); return dt; };
  m=s.match(/(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s+([a-z]{3,9})\.?,?\s*(\d{4})?/);
  if(m&&mon(m[3])>=0){ const y=m[4]?+m[4]:null; return {a:mk(+m[1],mon(m[3]),y),b:eod(mk(+m[2],mon(m[3]),y))}; }
  const found=[]; const re=/(\d{1,2})\s+([a-z]{3,9})\.?,?\s*(\d{4})?/g; let x;
  while((x=re.exec(s))){ const mi=mon(x[2]); if(mi>=0) found.push(mk(+x[1],mi,x[3]?+x[3]:null)); }
  if(found.length){ found.sort((p,q)=>p-q); return {a:found[0],b:eod(found[found.length-1])}; }
  if(/\b(sat|saturday|sun|sunday)\b/.test(s)) return {wk:true};
  return null;
}
function brainSearch(events,q,now){
  now=now||new Date();
  const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const win=brainWindow(q.when,now);
  const main=[],undated=[];
  for(const e of events){
    if(!e||!(e.title||e.name)) continue;
    if(q.town&&brainTown(e.town)!==q.town) continue;
    const dr=brainDates(e,now);
    if(dr&&dr.b&&dr.b<today) continue;
    const vibes=brainTags(e);
    const title=String(e.title||e.name).toLowerCase();
    const rest=((e.description||e.desc||'')+' '+(e.category||'')+' '+(e.town||'')).toLowerCase();
    let rel=0;
    const hitK=(txt,k)=>k.length>=4?txt.includes(k):new RegExp('\\b'+k+'\\b').test(txt);
    for(const k of q.keywords){ if(hitK(title,k)) rel+=15; else if(hitK(rest,k)) rel+=5; }
    for(const v of q.vibes) if(vibes.includes(v)) rel+=30;
    if((q.keywords.length||q.vibes.length)&&rel===0) continue;
    if(q.free&&vibes.includes('free')) rel+=10;
    const item={e,rel,vibes,dr};
    if(win){
      if(!dr){ undated.push(item); continue; }
      let inWin;
      if(dr.always) inWin=true; else if(dr.wk) inWin=q.when==='weekend'; else inWin=win.some(w=>dr.a<=w[1]&&dr.b>=w[0]);
      if(!inWin) continue;
    }
    main.push(item);
  }
  const t=x=>(x.dr&&x.dr.a)?x.dr.a.getTime():9e15;
  const by=(x,y)=>(y.rel-x.rel)||(t(x)-t(y));
  main.sort(by); undated.sort(by);
  if(q.free){ const f=main.filter(i=>i.vibes.includes('free')); if(f.length){ main.length=0; main.push(...f); } }
  return {main:main.slice(0,8),undated:undated.slice(0,4),totalMain:main.length,totalUndated:undated.length};
}
function brainWhy(item,q){
  const parts=[];
  const hit=q.vibes.filter(v=>item.vibes.includes(v));
  if(hit.length) parts.push(hit.join(' / '));
  if(item.e.town) parts.push(item.e.town);
  if(item.dr&&item.dr.a) parts.push(item.dr.a.toLocaleDateString('en-ZA',{weekday:'short',day:'numeric',month:'short'}));
  else if(item.dr&&item.dr.always) parts.push('daily');
  else if(item.dr&&item.dr.wk) parts.push('weekends');
  return parts.join(' · ');
}
// ===== END BRAIN =====

async function loadEvents(req) {
  try {
    const file = path.join(process.cwd(), 'data', 'events.json');
    const j = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (Array.isArray(j.events) && j.events.length) return j.events;
  } catch (e) { /* fall through to HTTP */ }
  try {
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const r = await fetch('https://' + host + '/data/events.json');
    if (r.ok) { const j = await r.json(); return Array.isArray(j.events) ? j.events : []; }
  } catch (e) { /* ignore */ }
  return [];
}

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, 'http://localhost');
    const text = (url.searchParams.get('q') || '').slice(0, 200);
    const events = await loadEvents(req);
    const q = brainParse(text);
    const town = brainTown(url.searchParams.get('town') || '');
    if (town) q.town = town;
    const r = brainSearch(events, q, new Date());
    const shape = it => ({ ...it.e, why: brainWhy(it, q) });
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');
    res.status(200).json({
      query: { text, town: q.town, when: q.when, vibes: q.vibes, keywords: q.keywords },
      total: r.totalMain,
      events: r.main.map(shape),
      undated: r.undated.map(shape)
    });
  } catch (err) {
    res.status(200).json({ error: 'search failed', events: [], undated: [] });
  }
}
