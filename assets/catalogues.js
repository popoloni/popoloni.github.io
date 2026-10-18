(() => {
  'use strict';
  const form = document.querySelector('[data-catalogue-filter]');
  if (!form) return;
  const rows = [...document.querySelectorAll('[data-record]')];
  const q = form.querySelector('[name=q]');
  const group = form.querySelector('[name=group]');
  const field = form.dataset.groupField || 'streams';
  const count = document.getElementById('resultCount');
  const empty = document.getElementById('emptyState');
  const normalize = x => x.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const index = rows.map(el => ({el,text:normalize(el.textContent),groups:JSON.parse(el.dataset[field] || '[]')}));
  function apply(){
    const words = normalize(q.value.trim()).split(/\s+/).filter(Boolean); const selected = group?.value || '';
    let visible = 0;
    index.forEach(r => {const ok=words.every(w=>r.text.includes(w)) && (!selected || r.groups.includes(selected));r.el.hidden=!ok;if(ok)visible++;});
    count.textContent = `${visible.toLocaleString('en-US')} of ${rows.length.toLocaleString('en-US')} records shown`;
    empty.hidden = visible !== 0;
  }
  q.addEventListener('input',apply); group?.addEventListener('change',apply);
  document.querySelectorAll('[data-family-filter]').forEach(link => {
    link.addEventListener('click',event => {
      if (!group || field !== 'families') return;
      event.preventDefault();
      q.value='';group.value=link.dataset.familyFilter;apply();
      form.scrollIntoView({block:'start',behavior:'smooth'});group.focus({preventScroll:true});
    });
  });
  form.addEventListener('submit',e=>e.preventDefault());
  form.querySelector('[data-clear]').onclick=()=>{q.value='';if(group)group.value='';apply();q.focus();};
  function revealAnchor(){
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
    const target = document.getElementById(id);
    if (target?.matches('.practice-family-card')) {
      const disclosure=target.closest('details');if(disclosure)disclosure.open=true;
      requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));return;
    }
    if(!target || !target.matches('[data-record]'))return;
    q.value='';if(group)group.value='';apply();
    const detail=target.querySelector('details');if(detail)detail.open=true;
    requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
  }
  window.addEventListener('hashchange',revealAnchor);apply();revealAnchor();
})();
