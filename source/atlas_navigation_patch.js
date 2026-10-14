// Site-only enhancement: no changes to graph records or defaultState().
// URL parameters select a deliberate catalogue entry; a bare URL retains W001-W193.
const catalogueFiles={W:'polimi',O:'osmani',P:'pragmatic-engineer',F:'fowler',B:'books'};
const originalNodeDetails=renderNodeDetails;
renderNodeDetails=function(n,resetScroll=true){
 originalNodeDetails(n,resetScroll);
 const slug=catalogueFiles[n.r.collection] || (n.r.kind==='practice_descriptor'?'practices':n.r.kind==='practice_occurrence'?'occurrences':null);
 if(slug){const a=document.createElement('a');a.className='external-link';a.textContent='Read static catalogue entry';a.href='catalogues/'+slug+'.html#'+encodeURIComponent(n.id);$('inspectorBody').appendChild(a);}
};
function applyCatalogueURL(search=location.search){
const urlParams=new URLSearchParams(search);
if(['collection','node','group','grouping'].some(k=>urlParams.has(k))){
 const validCollections=(urlParams.get('collection')||'').split(',').filter(c=>Object.hasOwn(catalogueFiles,c));
 if(validCollections.length)S.collections=new Set(validCollections);
 const grouping=urlParams.get('grouping');if(['theme','chapter','topic','volume','collection','none'].includes(grouping))S.grouping=grouping;
 const group=urlParams.get('group');const groupLists={theme:allThemeIDs,chapter:allChapterIDs,topic:allTopicIDs,volume:allVolumeIDs};const groupKeys={theme:'themeFilters',chapter:'chapterFilters',topic:'topicFilters',volume:'volumeFilters'};
 if(groupLists[S.grouping]?.includes(group))S[groupKeys[S.grouping]]=new Set([group]);
 const n=byID.get(urlParams.get('node'));
 if(n){if(n.r.collection)S.collections.add(n.r.collection);else S.context.add(n.r.category);}
 rebuild({run:false});
 if(n){if(!visibleSet.has(n.i))revealNode(n);else selectNode(n,true);}
}

}
window.atlasOpenCatalogueView=applyCatalogueURL;
applyCatalogueURL();
