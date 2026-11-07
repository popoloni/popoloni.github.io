(() => {
  'use strict';
  const form = document.querySelector('[data-catalogue-filter]');
  if (!form) return;
  const rows = [...document.querySelectorAll('[data-record]')];
  const q = form.querySelector('[name=q]');
  const group = form.querySelector('[name=group]');
  const practice = form.querySelector('[name=practice]');
  const collection = form.querySelector('[name=sourceCollection]');
  const relation = form.querySelector('[name=linkRelation]');
  const status = form.querySelector('[name=reviewStatus]');
  const field = form.dataset.groupField || 'streams';
  const count = document.getElementById('resultCount');
  const empty = document.getElementById('emptyState');
  const normalize = x => String(x).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const parse = value => {try{return JSON.parse(value || '[]');}catch{return [];}};
  const index = rows.map(el => ({el,text:normalize(el.textContent),groups:parse(el.dataset[field]),
    practices:parse(el.dataset.practices),collections:parse(el.dataset.sourceCollections),
    connections:parse(el.dataset.practiceConnections),status:parse(el.dataset.reviewStatus),
    isPractice:el.classList.contains('practice-record')}));
  function selections(){return {practice:practice?.value||'',collection:collection?.value||'',relation:relation?.value||''};}
  function matchesConnection(c,s){return (!s.practice||c.practice===s.practice)&&(!s.collection||c.collection===s.collection)&&(!s.relation||c.relation===s.relation);}
  function apply(){
    const words=normalize(q.value.trim()).split(/\s+/).filter(Boolean), selected=group?.value||'', s=selections();
    let visible=0;
    index.forEach(r=>{
      const needsConnection=!!(s.practice||s.relation||(r.isPractice&&s.collection));
      const associationOK=needsConnection?r.connections.some(c=>matchesConnection(c,s)):(!s.collection||r.collections.includes(s.collection));
      const ok=words.every(w=>r.text.includes(w))&&(!selected||r.groups.includes(selected))&&associationOK&&(!status?.value||r.status===status.value);
      r.el.hidden=!ok;if(ok)visible++;
      const links=[...r.el.querySelectorAll('[data-practice-link]')];let matches=0;
      links.forEach(el=>{const keep=matchesConnection(parse(el.dataset.practiceLinkData),s);el.hidden=!keep;if(keep)matches++;});
      r.el.querySelectorAll('[data-practice-source-group]').forEach(el=>{el.hidden=![...el.querySelectorAll('[data-practice-link]')].some(item=>!item.hidden);});
      r.el.querySelectorAll('[data-connection-count]').forEach(el=>{el.textContent=`${matches} of ${links.length} linked sources shown`;});
    });
    count.textContent=`${visible.toLocaleString('en-US')} of ${rows.length.toLocaleString('en-US')} records shown`;
    empty.hidden=visible!==0;
  }
  function clear(){q.value='';[group,practice,collection,relation,status].forEach(el=>{if(el)el.value='';});}
  q.addEventListener('input',apply);[group,practice,collection,relation,status].forEach(el=>el?.addEventListener('change',apply));
  document.querySelectorAll('[data-family-filter]').forEach(link=>link.addEventListener('click',event=>{
    if(!group||field!=='families')return;event.preventDefault();clear();group.value=link.dataset.familyFilter;apply();
    form.scrollIntoView({block:'start',behavior:'smooth'});group.focus({preventScroll:true});
  }));
  form.addEventListener('submit',e=>e.preventDefault());form.querySelector('[data-clear]').onclick=()=>{clear();apply();q.focus();};
  function revealAnchor(){
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
    const target=document.getElementById(id);if(!target)return;
    if(target.matches('.practice-family-card')){const disclosure=target.closest('details');if(disclosure)disclosure.open=true;requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));return;}
    const record=target.matches('[data-record]')?target:target.closest('[data-record]');
    if(!record)return;clear();apply();
    if(target===record){
      const detail=record.querySelector(':scope > details');if(detail)detail.open=true;
      const sources=record.querySelector('.practice-sources');if(sources)sources.open=true;
    }
    if(target.matches('details'))target.open=true;
    for(let parent=target.parentElement;parent;parent=parent.parentElement){if(parent.matches('details'))parent.open=true;}
    requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
  }
  const params=new URLSearchParams(location.search);
  for(const [key,el] of [['practice',practice],['collection',collection],['relation',relation],['status',status]]){
    const value=params.get(key);if(el&&value&&[...el.options].some(o=>o.value===value))el.value=value;
  }
  window.addEventListener('hashchange',revealAnchor);apply();revealAnchor();
})();
