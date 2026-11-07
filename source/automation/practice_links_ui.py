"""Static presentation of reviewed source–practice graph edges.

This module materializes the reviewed graph. It neither infers classifications
from shared topics nor changes source nodes, book citations or practice prose.
"""
from __future__ import annotations
import collections
import html
import json
from pathlib import Path
from urllib.parse import quote

SOURCE_COLLECTIONS=('W','O','P','F','B','N')
RELATIONS={
    'INFORMS_PRACTICE':('Informs practice','Relevant reasoning, methods or reading context for selecting or adapting the practice.'),
    'ILLUSTRATES_PRACTICE':('Illustrates practice','A reported application or case illustrates a mechanism; it does not validate the complete practice.'),
    'EVALUATES_PRACTICE':('Evaluates a practice component','The source evaluates the specifically named component. The result does not validate the complete editorial guide.'),
    'CAUTIONS_PRACTICE':('Cautions about practice','A limitation, failure, cost or contrary finding constrains the use or interpretation of the practice.'),
    'DOCUMENTS_PRACTICE':('Documents practice origin','An exact retained book-occurrence trail documents historical origin, not independent effectiveness or the full current guide.')
}
CATEGORIES={
    'navigation_only':'Navigation or index',
    'promotion_or_announcement':'Promotion or announcement',
    'source_recruitment_only':'Recruitment without findings',
    'non_operational_context':'Outside the operational-practice scope'
}

def esc(value):
    return html.escape(str(value if value is not None else ''),quote=True)

def data_attr(name,value):
    return ' data-'+name+'=\''+esc(json.dumps(value,ensure_ascii=False))+'\''


class PracticeLinksUI:
    def __init__(self,payload,config):
        self.payload=payload
        self.config=config
        self.by={n['id']:n for n in payload['nodes']}
        self.sources=[n for n in payload['nodes'] if n.get('collection') in SOURCE_COLLECTIONS]
        self.practices=[n for n in payload['nodes'] if n.get('collection')=='PAT']
        self.collections={c['code']:c for c in config['collections']}
        self.by_source=collections.defaultdict(list)
        self.by_practice=collections.defaultdict(list)
        self.links=[]
        for edge in payload['edges']:
            if edge.get('family')!='practice':
                continue
            source=payload['nodes'][edge['source']]
            practice=payload['nodes'][edge['target']]
            if source.get('collection') not in SOURCE_COLLECTIONS or practice.get('collection')!='PAT':
                raise ValueError('Practice presentation received an invalid source/practice endpoint')
            if edge['relation'] not in RELATIONS:
                raise ValueError('Unknown practice relationship: '+edge['relation'])
            a=edge.get('attributes',{})
            row={'source':source['id'],'practice':practice['id'],'collection':source['collection'],
                 'relation':edge['relation'],'relation_label':RELATIONS[edge['relation']][0],
                 'primary':bool(a.get('primary')),'rationale':a.get('rationale',''),
                 'scope':a.get('scope',''),'basis':a.get('basis',{}),'edge_id':edge['id']}
            for key in ('evaluated_component','reviewed_on','provenance'):
                if key in a:row[key]=a[key]
            self.links.append(row)
            self.by_source[source['id']].append(row)
            self.by_practice[practice['id']].append(row)
        for rows in self.by_source.values():
            rows.sort(key=lambda r:(not r['primary'],r['practice']))
        for rows in self.by_practice.values():
            rows.sort(key=lambda r:(SOURCE_COLLECTIONS.index(r['collection']),r['source']))
        self.meta=payload.get('meta',{}).get('practice_links',{})
        self.exclusions={r['source']:r for r in self.meta.get('exclusions',[])}
        self.enabled=bool(self.links or self.meta)

    def coverage(self):
        mapped={source for source,rows in self.by_source.items() if rows}
        excluded=set(self.exclusions)
        source_ids={n['id'] for n in self.sources}
        practice_ids={n['id'] for n in self.practices}
        external={r['practice'] for r in self.links if r['collection'] in ('W','O','P','F')}
        rows=[]
        for code in SOURCE_COLLECTIONS:
            ids={n['id'] for n in self.sources if n['collection']==code}
            rows.append({'collection':code,'label':self.collections[code]['short'],'total':len(ids),
                         'mapped':len(ids&mapped),'excluded':len(ids&excluded),
                         'unreviewed':len(ids-mapped-excluded)})
        return {'release':self.config['site_version'],'reviewed_on':self.meta.get('reviewed_on',self.config['build_date']),
                'source_count':len(source_ids),'reviewed_source_count':len(source_ids&(mapped|excluded)),
                'mapped_source_count':len(mapped),'excluded_source_count':len(excluded),
                'unreviewed_source_ids':sorted(source_ids-mapped-excluded),
                'eligible_source_count':len(source_ids-excluded),
                'practice_count':len(practice_ids),'linked_practice_count':sum(bool(rows) for rows in self.by_practice.values()),
                'practices_with_external_sources':len(external),
                'practices_without_external_sources':sorted(practice_ids-external),
                'link_count':len(self.links),'primary_link_count':sum(r['primary'] for r in self.links),
                'relation_counts':dict(collections.Counter(r['relation'] for r in self.links)),
                'collections':rows,'exclusions':list(self.exclusions.values()),
                'semantics':'Reviewed editorial classifications of retained Atlas source annotations. Historical origins, background reasoning, reported cases, component evaluations and cautions have distinct meanings. No link alone establishes effectiveness, author endorsement, or a new manuscript citation.'}

    def connections(self,n):
        rows=self.by_practice.get(n['id'],[]) if n.get('collection')=='PAT' else self.by_source.get(n['id'],[])
        return [{k:r[k] for k in ('source','practice','collection','relation')} for r in rows]

    def attributes(self,n):
        if not self.enabled:return ''
        rows=self.connections(n)
        practices=[n['id']] if n.get('collection')=='PAT' else [r['practice'] for r in rows]
        codes=sorted({r['collection'] for r in rows}) or ([n['collection']] if n.get('collection') in SOURCE_COLLECTIONS else [])
        status='mapped' if rows else 'excluded' if n['id'] in self.exclusions else 'unreviewed'
        return data_attr('practices',practices)+data_attr('source-collections',codes)+data_attr('practice-connections',rows)+data_attr('review-status',status)

    def filter_options(self,mode):
        if not self.enabled:return ''
        out=''
        if mode in ('source','coverage'):
            out+='<label>Related practice<select name="practice"><option value="">All practices</option>'
            out+=''.join('<option value="'+esc(n['id'])+'">'+esc(n['id']+' · '+n['label'])+'</option>' for n in self.practices)
            out+='</select></label>'
        if mode in ('practice','coverage'):
            out+='<label>Source collection<select name="sourceCollection"><option value="">All collections</option>'
            out+=''.join('<option value="'+code+'">'+esc(code+' · '+self.collections[code]['short'])+'</option>' for code in SOURCE_COLLECTIONS)
            out+='</select></label><label>Relationship<select name="linkRelation"><option value="">All relationship meanings</option>'
            out+=''.join('<option value="'+key+'">'+esc(value[0])+'</option>' for key,value in RELATIONS.items())
            out+='</select></label>'
        if mode=='coverage':
            out+='<label>Review status<select name="reviewStatus"><option value="">All reviewed records</option><option value="mapped">Mapped to practices</option><option value="excluded">Outside practice scope</option></select></label>'
        return out

    def source_section(self,n,path,link,record_file):
        if not self.enabled or n.get('collection') not in SOURCE_COLLECTIONS:return ''
        rows=self.by_source.get(n['id'],[])
        if not rows:
            excluded=self.exclusions.get(n['id'])
            if not excluded:
                return '<section class="practice-associations"><h3>Practice classification</h3><p>Not yet reviewed for a practice association.</p></section>'
            return ('<section class="practice-associations practice-unmapped"><h3>Practice classification</h3><p><strong>'+esc(CATEGORIES.get(excluded['category'],excluded['category']))+'</strong>. '+esc(excluded['reason'])+'</p><p class="micro">The record remains in the Atlas. This disposition concerns its fit to the operational practices, not its overall quality or relevance.</p>'+link(path,'catalogues/practice-map.html#map-'+quote(n['id'],safe=''),'Review scope and coverage →')+'</section>')
        out='<section class="practice-associations" aria-label="Related practices"><h3>Related practices</h3><div class="practice-chips">'
        for r in rows:
            p=self.by[r['practice']]
            label='<span class="code">'+esc(p['id'])+'</span> '+esc(p['label'])+'<span class="practice-chip-role">'+esc(r['relation_label'])+(' · primary reading' if r['primary'] else '')+'</span>'
            out+=link(path,record_file(p),label,'practice-chip')
        out+='</div><details class="practice-link-details"><summary>Why these practices ('+str(len(rows))+')</summary><ul class="practice-link-list">'
        for r in rows:
            p=self.by[r['practice']]
            out+='<li data-practice-link'+data_attr('practice-link-data',{k:r[k] for k in ('source','practice','collection','relation')})+'><strong>'+esc(p['id']+' · '+r['relation_label'])+'</strong><p>'+esc(r['rationale'])+'</p>'
            if r.get('evaluated_component'):out+='<p class="micro"><strong>Evaluated component:</strong> '+esc(r['evaluated_component'])+'</p>'
            occs=r.get('basis',{}).get('occurrence_ids',[])
            if occs:
                out+='<p class="micro">Historical locators: '+' · '.join(link(path,record_file(self.by[x]),esc(x)) for x in occs)+'</p>'
            out+=link(path,'swe_knowledge_graph.html?practice='+quote(p['id'],safe=''),'Explore this practice with its sources →','card-link')+'</li>'
        out+='</ul><p class="micro">Primary reading is the main classification for this record, not a strength-of-evidence score. Associations use retained Atlas annotations; they add no manuscript citation or claim that the complete practice was validated.</p></details></section>'
        return out

    def practice_section(self,n,path,link,record_file):
        if not self.enabled:return ''
        rows=self.by_practice.get(n['id'],[])
        if not rows:return '<section class="practice-associations"><h3>Linked sources</h3><p>No reviewed source association is available yet.</p></section>'
        external=sum(r['collection'] in ('W','O','P','F') for r in rows)
        ident='practice-sources-'+n['id']
        out='<section class="practice-associations"><p class="practice-source-count"><strong>'+str(len(rows))+' linked sources</strong> · '+str(external)+' external sources · '+str(len(rows)-external)+' book records. '+link(path,'catalogues/practices.html#'+quote(ident,safe=''),'Read the associations ↓')+'</p>'
        out+='<details class="practice-sources" id="'+esc(ident)+'"><summary>Read linked sources and relationship rationales ('+str(len(rows))+')</summary><p class="micro">Each link below has a reviewed meaning. External reading, author synthesis and historical origin remain distinct; none alone proves this whole practice effective.</p><p class="micro" data-connection-count>'+str(len(rows))+' linked sources shown</p>'
        for code in SOURCE_COLLECTIONS:
            selected=[r for r in rows if r['collection']==code]
            if not selected:continue
            target='catalogues/'+self.collections[code]['slug']+'.html?practice='+quote(n['id'],safe='')
            out+='<section class="practice-source-group" data-practice-source-group><h4>'+link(path,target,esc(self.collections[code]['short']))+' <span class="muted">('+str(len(selected))+')</span></h4><ul class="practice-link-list">'
            for r in selected:
                s=self.by[r['source']]
                out+='<li data-practice-link'+data_attr('practice-link-data',{k:r[k] for k in ('source','practice','collection','relation')})+'><div class="practice-source-title"><span class="code">'+esc(s['id'])+'</span> '+link(path,record_file(s),esc(s['label']))+'</div><span class="practice-relation-label">'+esc(r['relation_label'])+(' · primary reading for this source' if r['primary'] else '')+'</span><p>'+esc(r['rationale'])+'</p>'
                if r.get('evaluated_component'):out+='<p class="micro"><strong>Evaluated component:</strong> '+esc(r['evaluated_component'])+'</p>'
                occs=r.get('basis',{}).get('occurrence_ids',[])
                if occs:out+='<p class="micro">Historical locators: '+' · '.join(link(path,record_file(self.by[x]),esc(x)) for x in occs)+'</p>'
                out+='</li>'
            out+='</ul></section>'
        out+='</details></section>'
        return out

    def coverage_section(self,path,link):
        if not self.enabled:return ''
        c=self.coverage()
        out='<section class="practice-coverage" aria-labelledby="practice-coverage-heading"><h2 id="practice-coverage-heading">Practices connected to the corpus</h2><div class="practice-coverage-stats">'
        for number,label in [(str(c['reviewed_source_count'])+'/'+str(c['source_count']),'source records reviewed'),(str(c['mapped_source_count']),'source records mapped'),(str(c['linked_practice_count'])+'/'+str(c['practice_count']),'practices with sources'),(str(c['link_count']),'reviewed associations')]:
            out+='<div><strong>'+number+'</strong><span>'+esc(label)+'</span></div>'
        out+='</div><p>Read from a practice to its sources, or from any source card to its related practices. The classification distinguishes rationale, cases, component evaluations, cautions and historical book origins.</p>'
        if c['excluded_source_count']:
            out+='<p>'+str(c['excluded_source_count'])+' retained records are explicitly outside the operational-practice scope. They remain accessible, with individual review reasons; no forced practice match is created.</p>'
        out+='<div class="practice-table-scroll"><table class="practice-coverage-table"><thead><tr><th>Collection</th><th>Records</th><th>Mapped</th><th>Outside practice scope</th></tr></thead><tbody>'
        for row in c['collections']:
            out+='<tr><th>'+link(path,'catalogues/'+self.collections[row['collection']]['slug']+'.html',esc(row['collection']+' · '+row['label']))+'</th><td>'+str(row['total'])+'</td><td>'+str(row['mapped'])+'</td><td>'+str(row['excluded'])+'</td></tr>'
        out+='</tbody></table></div><p class="micro">'+str(c['practices_with_external_sources'])+' of '+str(c['practice_count'])+' practices have external W/O/P/F reading. Book-only coverage, where present, is visible in the full review. Primary reading means the source’s main editorial classification; it is not a quality ranking.</p>'
        if c['practices_without_external_sources']:
            out+='<details class="practice-legend"><summary>Practices currently linked only to book sources ('+str(len(c['practices_without_external_sources']))+')</summary><p>The retained annotations did not justify an external-source association for these specific mechanisms. Their historical origins and chapter context remain linked; no external corroboration is implied.</p><ul>'
            for pid in c['practices_without_external_sources']:
                out+='<li>'+link(path,'catalogues/practices.html#'+quote(pid,safe=''),esc(pid+' · '+self.by[pid]['label']))+'</li>'
            out+='</ul></details>'
        out+='<div class="actions">'+link(path,'catalogues/practice-map.html','Inspect every source and review decision','button')+link(path,'data/practice_links.json','Download classified relationships','button')+link(path,'data/practice_coverage.json','Download coverage audit','button')+'</div><details class="practice-legend"><summary>What the relationship labels mean</summary><dl>'
        for title,meaning in RELATIONS.values():out+='<dt>'+esc(title)+'</dt><dd>'+esc(meaning)+'</dd>'
        out+='</dl><p>Classifications are an editorial reading layer based on the retained Atlas records. They do not attribute our practice names to source authors, create manuscript citations, or claim a new full-text review or replication.</p></details></section>'
        return out

    def coverage_records(self,path,link,record_file):
        out='<div class="records practice-map-records">'
        for n in self.sources:
            rows=self.by_source.get(n['id'],[])
            out+='<article class="record practice-map-record" data-record id="map-'+esc(n['id'])+'"'+self.attributes(n)+'><div class="record-top"><span class="code">'+esc(n['id'])+'</span><span class="pill">'+esc(self.collections[n['collection']]['short'])+'</span><span class="pill">'+('Mapped' if rows else 'Outside practice scope')+'</span></div><h2>'+link(path,record_file(n),esc(n['label']))+'</h2>'
            if n.get('authors'):out+='<p class="byline">'+esc(n['authors'])+'</p>'
            if n.get('summary'):out+='<p class="summary">'+esc(n['summary'])+'</p>'
            if rows:
                out+='<ul class="practice-map-list">'
                for r in rows:
                    p=self.by[r['practice']]
                    out+='<li><strong>'+link(path,record_file(p),esc(p['id']+' · '+p['label']))+'</strong><span class="practice-relation-label">'+esc(r['relation_label'])+(' · primary reading' if r['primary'] else '')+'</span><p>'+esc(r['rationale'])+'</p></li>'
                out+='</ul>'
            else:
                e=self.exclusions.get(n['id'],{})
                out+='<p><strong>'+esc(CATEGORIES.get(e.get('category'),e.get('category','Unreviewed')))+'</strong>. '+esc(e.get('reason','No review decision is recorded.'))+'</p>'
            out+='</article>'
        return out+'</div>'

    def export_relationships(self,records):
        ids={n['id'] for n in records}
        return [r for r in self.links if r['source'] in ids or r['practice'] in ids]

    def csv_fields(self,n):
        if n.get('collection')=='PAT':
            rows=self.by_practice.get(n['id'],[])
            return {'practice_ids':'','practice_source_ids':'|'.join(r['source'] for r in rows),
                    'practice_relation_types':'|'.join(sorted({r['relation'] for r in rows})),
                    'practice_review_status':'mapped' if rows else 'unreviewed'}
        rows=self.by_source.get(n['id'],[])
        return {'practice_ids':'|'.join(r['practice'] for r in rows),'practice_source_ids':'',
                'practice_relation_types':'|'.join(sorted({r['relation'] for r in rows})),
                'practice_review_status':'mapped' if rows else 'excluded' if n['id'] in self.exclusions else ''}

    def write_outputs(self,root):
        if not self.enabled:return
        root=Path(root)
        for name,obj in [('practice_links',{'schema_version':1,'meta':self.coverage(),'relationships':self.links}),('practice_coverage',self.coverage())]:
            (root/'data'/f'{name}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (root/'assets/practice-links.css').write_text(CSS,encoding='utf-8')
        (root/'assets/catalogues.js').write_text(CATALOGUE_JS,encoding='utf-8')


CSS='''/* Reviewed practice classifications. Generated by source/build_site.py. */
.practice-associations{border-top:1px solid var(--line);margin:20px 0 16px;padding-top:16px;font-size:13px;line-height:1.65}.practice-associations h3{margin:0 0 12px;font-size:15px}.practice-chips{display:flex;flex-wrap:wrap;gap:9px}.practice-chip{display:block;max-width:100%;padding:9px 12px;background:#f1f7fa;border:1px solid #d5e4eb;border-radius:7px;color:var(--ink);font-size:12px;text-decoration:none;overflow-wrap:anywhere}.practice-chip:hover{background:#e6f1f5;text-decoration:underline}.practice-chip .code{margin-right:5px}.practice-chip-role{display:block;color:var(--accent);font-size:11px;margin-top:3px}.practice-link-details,.practice-sources,.practice-legend{margin-top:12px}.practice-link-details>summary,.practice-sources>summary,.practice-legend>summary{cursor:pointer;color:var(--accent);font-size:13px;font-weight:650;padding:8px 0}.practice-link-list,.practice-map-list{list-style:none;padding:0;margin:10px 0}.practice-link-list>li,.practice-map-list>li{padding:13px 0;border-top:1px solid var(--line);overflow-wrap:anywhere}.practice-link-list p,.practice-map-list p{margin:6px 0;font-size:12px;line-height:1.7}.practice-source-title{font-weight:600;line-height:1.6}.practice-source-title .code{margin-right:7px}.practice-relation-label{display:block;font-size:11px;color:var(--accent);margin:4px 0}.practice-source-group h4{font-size:14px;margin:20px 0 5px}.practice-source-count{font-size:12px;line-height:1.8;margin:0}.practice-unmapped{background:#f8f7f2;border-radius:6px;padding:14px 16px}.practice-unmapped p{margin:8px 0}.practice-coverage{background:#fff;border:1px solid var(--line);border-radius:10px;padding:25px;margin:26px 0}.practice-coverage h2{font-size:25px;margin:0 0 18px}.practice-coverage p{font-size:13px;line-height:1.8}.practice-coverage-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0 18px}.practice-coverage-stats>div{padding:14px;background:#f1f7fa;border-radius:6px;min-width:0}.practice-coverage-stats strong{display:block;font-size:27px;line-height:1.2;color:var(--accent)}.practice-coverage-stats span{display:block;font-size:11px;margin-top:7px;color:var(--muted)}.practice-table-scroll{overflow-x:auto}.practice-coverage-table{width:100%;border-collapse:collapse;font-size:12px}.practice-coverage-table th,.practice-coverage-table td{padding:9px;border-bottom:1px solid var(--line);text-align:left}.practice-coverage-table thead{background:#f2f6f8}.practice-coverage-table th:first-child{width:50%}.practice-legend dl{font-size:12px;line-height:1.75}.practice-legend dt{font-weight:700;margin-top:12px}.practice-legend dd{margin:4px 0 0}.catalogue-toolbar{flex-wrap:wrap}.catalogue-toolbar label{min-width:0;max-width:100%}.catalogue-toolbar select{max-width:100%;width:100%;text-overflow:ellipsis}.catalogue-toolbar label:has(select){flex:1 1 180px}.practice-map-record h2{font-size:18px}.practice-map-record{padding:20px 24px}.practice-link-list>li[hidden],.practice-source-group[hidden]{display:none!important}
@media(max-width:650px){.practice-coverage{padding:18px}.practice-coverage-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.practice-coverage-stats strong{font-size:24px}.practice-chips{display:block}.practice-chip{margin-bottom:8px}.practice-coverage-table th,.practice-coverage-table td{padding:8px 5px;font-size:11px}.catalogue-toolbar label:has(select){flex:1 1 100%}.practice-map-record{padding:18px}.practice-source-title{font-size:12px}}
@media print{.practice-coverage{break-inside:avoid}.practice-associations{font-size:11px}.practice-chip{background:none}}
'''

CATALOGUE_JS=r'''(() => {
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
'''
