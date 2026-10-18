// Static catalogue navigation. A bare URL preserves the original W001-W193 view.
const catalogueFiles={W:'polimi',O:'osmani',P:'pragmatic-engineer',F:'fowler',B:'books',N:'ndse2'};
const originalNodeDetails=renderNodeDetails;
renderNodeDetails=function(n,resetScroll=true){
 originalNodeDetails(n,resetScroll);
 const slug=catalogueFiles[n.r.collection] || (n.r.kind==='practice_descriptor'?'practices':n.r.kind==='practice_occurrence'?'occurrences':null);
 if(slug){
  const a=document.createElement('a');
  a.className='external-link';
  a.textContent=n.r.collection==='N'?'Read published chapter guide':'Read static catalogue entry';
  a.href='catalogues/'+slug+'.html#'+encodeURIComponent(n.id);
  $('inspectorBody').appendChild(a);
 }
 const ch=D.chapters.find(c=>c.id===n.id||c.record_id===n.id||c.id===n.r.attributes.chapter_hub);
 if(ch){
  const a=document.createElement('a');
  a.className='external-link';
  a.textContent='Chapter '+ch.n+' · outline and exact source citations';
  a.href='catalogues/chapters/c'+String(ch.n).padStart(2,'0')+'.html';
  $('inspectorBody').appendChild(a);
 }
 if(n.r.attributes.title_it){
  const p=document.createElement('p');
  p.className='micro';p.lang='it';p.textContent='Italiano: '+n.r.attributes.title_it;
  $('inspectorBody').appendChild(p);
 }
 if(n.r.attributes.updated_date){
  const p=document.createElement('p');p.className='micro';
  p.textContent='Latest revision: '+n.r.attributes.updated_date+' · original publication: '+n.r.attributes.publication_date;
  $('inspectorBody').appendChild(p);
 }
 if(n.r.attributes.latest_version_url){
  const u=safeURL(n.r.attributes.latest_version_url);
  if(u){const a=document.createElement('a');a.className='external-link';a.href=u;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Read the superseding expanded article';$('inspectorBody').appendChild(a);}
 }
};
function applyCatalogueURL(search=location.search){
 const urlParams=new URLSearchParams(search);
 if(['collection','node','group','grouping','chapterBasis','context'].some(k=>urlParams.has(k))){
  const validCollections=(urlParams.get('collection')||'').split(',').filter(c=>Object.hasOwn(catalogueFiles,c));
  if(validCollections.length)S.collections=new Set(validCollections);
  const grouping=urlParams.get('grouping');
  if(['theme','chapter','topic','volume','collection','none'].includes(grouping))S.grouping=grouping;
  const basis=urlParams.get('chapterBasis');
  if(['mapped','actual'].includes(basis))S.chapterBasis=basis;
  const group=urlParams.get('group');
  const groupLists={theme:allThemeIDs,chapter:allChapterIDs,topic:allTopicIDs,volume:allVolumeIDs};
  const groupKeys={theme:'themeFilters',chapter:'chapterFilters',topic:'topicFilters',volume:'volumeFilters'};
  if(groupLists[S.grouping]?.includes(group))S[groupKeys[S.grouping]]=new Set([group]);
  const contexts=(urlParams.get('context')||'').split(',').filter(c=>D.nodeGroups.some(g=>g.id===c));
  if(contexts.length)S.context=new Set(contexts);
  const n=byID.get(urlParams.get('node'));
  if(n){if(n.r.collection)S.collections.add(n.r.collection);else S.context.add(n.r.category);}
  rebuild({run:false});
  if(n){if(!visibleSet.has(n.i))revealNode(n);else selectNode(n,true);}
 }
}
window.atlasOpenCatalogueView=applyCatalogueURL;
applyCatalogueURL();
