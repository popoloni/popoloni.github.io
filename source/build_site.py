#!/usr/bin/env python3
"""Regenerate static catalogues and the NDSE2 companion from the current audited atlas.
Python 3.10+, standard library only. No network or new research is performed by this builder.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, html, io, json, os, re, shutil, unicodedata, zipfile
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from build_ndse2_pages import BookCompanion

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent
C=json.loads((SOURCE/'site_config.json').read_text(encoding='utf-8'))
ATLAS_SOURCE=SOURCE/C.get('atlas_source','atlas_v13_current.html')
GRAPH_JSON=C.get('graph_json','data/graph/knowledge_graph_v13.json')
GRAPH_GRAPHML=C.get('graph_graphml','data/graph/knowledge_graph_v13.graphml')
BASE=ATLAS_SOURCE.read_text(encoding='utf-8')
D=json.loads(re.search(r'<script id="graph-data" type="application/json">(.*?)</script>',BASE,re.S).group(1))
BY={n['id']:n for n in D['nodes']}
COLS={c['code']:c for c in C['collections']}
SOURCES=[n for n in D['nodes'] if n.get('collection') in COLS]
PRACTICES=[n for n in D['nodes'] if n['kind']=='practice_descriptor']
OCCURRENCES=[n for n in D['nodes'] if n['kind']=='practice_occurrence']
FAMILIES=[n for n in D['nodes'] if n['kind']=='practice_family']
BOOKS=[n for n in D['nodes'] if n['kind']=='published_book']
COUNTS=collections.Counter(n.get('collection') for n in SOURCES)
EXTERNAL_COUNT=sum(v for k,v in COUNTS.items() if k not in {'B','N'})
BOOK_VOLUME_IDS={n.get('attributes',{}).get('volume_id') for n in BOOKS}
VOLUMES=[g for g in D['volumes'] if g['id'] in BOOK_VOLUME_IDS]
EARLIER_VOLUME_IDS={v for n in SOURCES if n.get('collection')=='B' for v in n.get('volumes',[])}
EARLIER_VOLUMES=[g for g in VOLUMES if g['id'] in EARLIER_VOLUME_IDS]
NDSE2=BookCompanion(SOURCE/'ndse2_book.json',required='N' in COLS)
RELEASE_NOTES='UPDATE_20261018.html'
RESEARCH_AUDIT='data/updates/source_review_20261018.json'
NAMES={n['id']:n['label'] for n in D['nodes']}
NAMES.update({g['id']:g['label'] for k in ['themes','chapters','topics','volumes'] for g in D[k]})
ADJ=collections.defaultdict(list)
for e in D['edges']:
 s=D['nodes'][e['source']]['id'];t=D['nodes'][e['target']]['id'];ADJ[s].append((t,e,'out'))
 if s!=t:ADJ[t].append((s,e,'in'))
PAGES=[]
def esc(x):return html.escape(str(x if x is not None else ''),quote=True)
def slug(x):
 s=unicodedata.normalize('NFKD',x).encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+','-',s).strip('-')
def rel(current,target):
 # target is a site-root-relative filename, possibly with query/fragment
 p,sep,f=target.partition('#');p,sepq,q=p.partition('?')
 out=os.path.relpath(p,os.path.dirname(current) or '.').replace(os.sep,'/')
 return out+('?' + q if sepq else '')+('#'+f if sep else '')
def link(current,target,label,cls='',external=False):
 href=target if external else rel(current,target)
 return f'<a href="{esc(href)}"'+(f' class="{esc(cls)}"' if cls else '')+(' target="_blank" rel="noopener noreferrer"' if external else '')+f'>{label}</a>'
def safeurl(u):
 try:return u if urlsplit(u).scheme in ('http','https') and urlsplit(u).netloc else ''
 except:return ''
def atlasurl(**params):return 'swe_knowledge_graph.html'+('?' + urlencode(params) if params else '')
def collection_file(code):return f'catalogues/{COLS[code]["slug"]}.html'
def record_file(n):
 if n.get('collection') in COLS:return collection_file(n['collection'])+'#'+quote(n['id'],safe='')
 if n['kind']=='published_book':
  g=next((g for g in VOLUMES if g['id']==n.get('attributes',{}).get('volume_id')),None)
  if g:return groupfile('volumes',g)
 if n['kind']=='practice_descriptor':return 'catalogues/practices.html#'+quote(n['id'],safe='')
 if n['kind']=='practice_occurrence':return 'catalogues/occurrences.html#'+quote(n['id'],safe='')
 return atlasurl(node=n['id'])
def groupfile(kind,g):
 return 'catalogues/'+kind+'/'+(g['id'].split(':')[-1].lower() if kind=='chapters' else g['id'].lower() if kind=='volumes' else slug(g['label']))+'.html'
def named_group_link(page,gid,kind):
 groups=D[{'streams':'themes','chapters':'chapters','topics':'topics','volumes':'volumes'}[kind]]
 g=next((g for g in groups if g['id']==gid),None)
 return link(page,groupfile(kind,g),esc((f'Chapter {g["n"]}: ' if kind=='chapters' else '')+g['label'])) if g else esc(gid)
def jsjson(obj):return json.dumps(obj,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
LOGO='<svg viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M5 5L23 7L18 23L5 5L4 20L23 7" stroke="currentColor" opacity=".75"/><g fill="currentColor"><circle cx="5" cy="5" r="3"/><circle cx="23" cy="7" r="3"/><circle cx="18" cy="23" r="3"/><circle cx="4" cy="20" r="2.5"/></g></svg>'
def page(path,title,body,description='',active='Catalogues',wide=False):
 nav_items=[('Atlas','swe_knowledge_graph.html'),('Catalogues','catalogues/index.html')]
 if 'N' in COLS:nav_items.append(('NDSE2',collection_file('N')))
 nav_items.extend([('About','about.html'),('Downloads','downloads.html')])
 nav=''.join(link(path,t,esc(l)) if active!=l else f'<a aria-current="page" href="{esc(rel(path,t))}">{esc(l)}</a>' for l,t in nav_items)
 s=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="author" content="Enrico Papalini"><meta name="description" content="{esc(description)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="website"><title>{esc(title)} · Knowledge Atlas</title><link rel="stylesheet" href="{esc(rel(path,'assets/site.css'))}"><script src="{esc(rel(path,'assets/catalogues.js'))}" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="site-head"><div class="nav">{link(path,'index.html',LOGO+'<span><small>AI & Software Engineering</small><strong>Knowledge Atlas</strong></span>','brand')}<nav class="nav-links" aria-label="Main navigation">{nav}</nav></div></header><main id="main" class="wrap {'wide' if wide else ''}">{body}</main><footer class="site-foot"><div class="foot-inner"><p>Independent atlas by Enrico Papalini · Site v{C['site_version']} · Graph snapshot {C['graph_snapshot']}<br>Source collections identify provenance, not evidence quality.</p><p>{link(path,'attribution.html','Credits &amp; evidence boundaries')} · {link(path,RELEASE_NOTES,'What changed')} · {link(path,'verification/report.html','Build checks')}</p></div></footer></body></html>'''
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8');PAGES.append(path)
def heading(title,kicker='Static catalogues',description=''):
 return f'<p class="eyebrow">{esc(kicker)}</p><h1>{esc(title)}</h1>'+ (f'<p class="intro">{esc(description)}</p>' if description else '')
def collection_nav(path,code=None):
 return '<nav class="collection-nav" aria-label="Source collections">'+''.join(f'<a href="{esc(rel(path,collection_file(c)))}"'+(' aria-current="page"' if c==code else '')+f'>{esc(c)} · {esc(v["short"])}</a>' for c,v in COLS.items())+'</nav>'
def filter_bar(path,count,groups=None,field='streams',group_title='Stream'):
 opts=''
 if groups:opts=f'<label>{esc(group_title)}<select name="group"><option value="">All</option>'+''.join(f'<option value="{esc(g["id"])}">{esc(g["label"])}</option>' for g in groups)+'</select></label>'
 return f'<form class="catalogue-toolbar" data-catalogue-filter data-group-field="{esc(field)}"><label class="search-field">Find a record<input type="search" name="q" placeholder="Search ID, title, author, summary or caveat" autocomplete="off"></label>{opts}<button type="button" data-clear>Clear filters</button></form><noscript><p class="caution">All entries are available below without JavaScript. Use your browser’s Find command to search.</p></noscript><p id="resultCount" class="result-count" role="status" aria-live="polite">{count:,} records shown</p><div id="emptyState" class="empty-state" hidden>No matching records. Clear the search or choose another group.</div>'
def fmt_meta(a,keys):
 vals=[]
 for key,title in keys:
  v=a.get(key)
  if v not in (None,'',[],{}):vals.append(f'<dt>{esc(title)}</dt><dd>{esc(v if not isinstance(v,(dict,list)) else json.dumps(v,ensure_ascii=False))}</dd>')
 return '<dl class="metadata">'+''.join(vals)+'</dl>' if vals else ''
def record(n,path):
 c=n.get('collection');a=n.get('attributes',{});col=COLS.get(c,{})
 tone=f'var(--{c.lower()})' if c in COLS else 'var(--accent)'
 dat=' '.join(f'data-{key}=\'{esc(json.dumps(n.get(key,[]),ensure_ascii=False))}\'' for key in ['streams','topics','volumes','mapped','actual'])
 # Collection data are displayed as recorded. Never promote an inferred outcome or fill in a missing author.
 byline=n.get('authors') or a.get('authors') or a.get('author') or ''
 date=n.get('year') or a.get('publication_date') or a.get('year') or ''
 info=' · '.join(esc(x) for x in [byline,str(date)] if x)
 updated=a.get('updated_date') or a.get('revision_date')
 if updated and str(updated)!=str(date):info+=f' · Updated {esc(updated)}'
 evidence=a.get('reviewed_evidence_class') or a.get('evidence_class') or ''
 summary=n.get('summary') or a.get('contribution') or a.get('summary') or a.get('required_revision') or a.get('purpose') or ''
 limit=n.get('limitation') or a.get('limitation') or ''
 title=n['label'];anchor=quote(n['id'],safe='')
 pills=f'<span class="pill">{esc(col.get("short",n["kind"].replace("_"," ")))}</span>'
 if n.get('printed'):pills+='<span class="pill">In the published NDSE2 bibliography</span>'
 if a.get('access_status'):pills+=f'<span class="pill">{esc(a["access_status"].replace("_"," "))}</span>'
 top=f'<div class="record-top"><span class="code">{esc(n["id"])}</span>{pills}</div><h2><a href="#{anchor}">{esc(title)}</a></h2>'+ (f'<p class="byline">{info}</p>' if info else '')
 if c=='N' and a.get('title_it'):top+=f'<p class="byline" lang="it">{esc(a["title_it"])}</p>'
 if summary:top+=f'<p class="summary">{esc(summary)}</p>'
 if n.get('streams'):top+='<div class="tags">'+''.join(named_group_link(path,g,'streams') for g in n['streams'])+'</div>'
 more=''
 if limit:more+=f'<div class="caution"><strong>Evidence boundary</strong>{esc(limit)}</div>'
 if a.get('summary') and a['summary']!=summary:more+=f'<p><strong>Recorded summary.</strong> {esc(a["summary"])}</p>'
 if a.get('main_findings'):more+=f'<p><strong>Reported findings / argument.</strong> {esc(a["main_findings"])}</p>'
 if evidence:more+=f'<p><strong>Source type, as recorded:</strong> {esc(evidence)}</p>'
 if a.get('manual_use'):more+=f'<p><strong>Editorial use.</strong> {esc(a["manual_use"])}</p>'
 if c=='W':more+='<p class="micro">Author names can be lead-author fields, not complete bylines. Follow the recorded source for the full citation. An index URL is labelled as an index, not silently replaced by an unverified primary-paper link.</p>'
 if c=='B':
  v=a.get('volume_id');more+='<p><strong>Parent volume:</strong> '+(named_group_link(path,v,'volumes') if v else 'Not recorded')+'</p>'
 if c=='N':
  chapter=NDSE2.chapter(n['id'])
  if chapter:
   more+=NDSE2.chapter_content(chapter,path,link,BY,record_file,include_summary=False,include_evidence=False)
   top+='<p>'+link(path,NDSE2.chapter_path(chapter),'Chapter guide and cited sources →','card-link')+'</p>'
 if n['kind']=='practice_descriptor':
  more+=fmt_meta(a,[('required_revision','Recorded revision'),('disposition','Editorial disposition'),('family','Practice family'),('status','Record status')])
  for occ in parsejson(a.get('occurrences','[]')):
   oid='OCC:'+occ
   if oid in BY:more+='<p>Historical occurrence: '+link(path,record_file(BY[oid]),esc(occ)+' — '+esc(BY[oid]['label']))+'</p>'
 more+=fmt_meta(a,[('source_scope','Collection scope'),('publication_status','Publication status'),('source_version_note','Source version'),('source_locator','Inspected passage'),('verification_scope','Inspection scope'),('source_review_scope','Review scope'),('review_scope','Mapping scope'),('access_note','Access note'),('source_path','Original source path'),('source_file','Original source file'),('source_line','Start line'),('source_end_line','End line'),('source_sha256','Original SHA-256'),('provenance','Provenance')])
 if safeurl(a.get('latest_version_url','')):more+='<p>'+link(path,a['latest_version_url'],'Read the expanded source version ↗',external=True)+'</p>'
 if c in COLS and c!='N':
  actual=n.get('actual',[]);mapped=n.get('mapped',[])
  more+='<div class="mapping"><h3>Cited in published NDSE2 chapters</h3>'+ ('<br>'.join(named_group_link(path,x,'chapters') for x in actual) if actual else '<span class="muted">No literal chapter citation recorded in the published edition.</span>')
  more+='<h3>Editorial chapter mappings</h3>'+ ('<br>'.join(named_group_link(path,x,'chapters') for x in mapped) if mapped else '<span class="muted">None recorded.</span>')+'<p class="micro">Editorial reading suggestions can extend beyond the published citations. Chapter guides show the outline and traceable source references.</p></div>'
 if n.get('topics'):more+='<p><strong>Topics.</strong> '+' · '.join(named_group_link(path,g,'topics') for g in n['topics'])+'</p>'
 source_conn=[(BY[other],e,direction) for other,e,direction in ADJ[n['id']] if BY[other].get('collection') in COLS or (n['kind']=='practice_occurrence' and BY[other]['kind']=='practice_descriptor')]
 if source_conn:
  more+=f'<details><summary>{len(source_conn)} recorded source relationships</summary><ul class="compact-list">'
  for other,e,direction in source_conn:
   more+='<li>'+('→ ' if direction=='out' else '← ')+link(path,record_file(other),esc(other['id'])+' · '+esc(other['label']))+f'<br><span class="micro">{esc(e["relation"])} · edge {esc(e["id"])} · key {esc(e["key"])}</span></li>'
  more+='</ul><p class="micro">These retain the graph’s exact relation labels. A connection is not automatically a causal claim or an independent replication.</p></details>'
 more+='<details><summary>All preserved graph attributes</summary><pre>'+esc(json.dumps(a,ensure_ascii=False,indent=2))+'</pre></details>'
 href=safeurl(n.get('url',''));actions=[]
 if href:
  lab='Open recorded index ↗' if href.startswith('https://www.sepolimi.com/p/se-ai-bibliography') else ('Open author’s companion ↗' if c=='B' else 'Open recorded source ↗')
  actions.append(link(path,href,lab,external=True))
 args={'node':n['id']}
 if c in COLS:args={'collection':c,**args}
 actions.append(link(path,atlasurl(**args),'View in atlas →'))
 actions.append(link(path,record_file(n),'Permanent entry link'))
 return f'<article class="record" id="{esc(n["id"])}" data-record {dat} style="--tone:{tone}">{top}<details><summary>Evidence, context &amp; provenance</summary>{more}</details><div class="record-links">'+''.join(actions)+'</div></article>'
def parsejson(x):
 try:return json.loads(x) if isinstance(x,str) else x
 except:return []
def write_dataset(name,records):
 obj={'meta':{'source':ATLAS_SOURCE.name,'snapshot':C['graph_snapshot'],'site_version':C['site_version'],'count':len(records),'note':'Materialized view of the current audited graph; complete node fields retained. Source inspection and publication status are recorded per item. The builder performs no new empirical validation.'},'records':records}
 p=ROOT/f'data/catalogues/{name}.json';p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 keys=['id','title','authors_as_recorded','date_as_recorded','collection','kind','summary','limitation','recorded_url','streams','topics','actual_chapter_citations','editorial_chapter_mappings','source_path','source_sha256','title_it','publication_date','updated_date','publication_status','parent_volume']
 with (ROOT/f'data/catalogues/{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for n in records:
   a=n.get('attributes',{});row=dict(zip(keys,[n['id'],n['label'],n.get('authors',''),n.get('year',''),n.get('collection',''),n['kind'],n.get('summary',''),n.get('limitation',''),n.get('url',''),'; '.join(n.get('streams',[])),'; '.join(n.get('topics',[])),'; '.join(n.get('actual',[])),'; '.join(n.get('mapped',[])),a.get('source_path',a.get('source_file','')),a.get('source_sha256',''),a.get('title_it',''),a.get('publication_date',''),a.get('updated_date',a.get('revision_date','')),a.get('publication_status',''),a.get('volume_id','')]))
   # Protect spreadsheet users against formula interpretation; JSON is byte-faithful semantically.
   for k,v in row.items():
    if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')):row[k]="'"+v
   w.writerow(row)
def collection_card(c,path):
 count=sum(n.get('collection')==c['code'] for n in SOURCES);tone=f'var(--{c["code"].lower()})'
 return f'<article class="collection-card" style="--tone:{tone}"><div class="card-top"><span class="code">{c["code"]} COLLECTION</span><span class="pill">{count} records</span></div><h3>'+link(path,collection_file(c['code']),esc(c['title']))+f'</h3><p>{esc(c["description"])}</p>'+link(path,collection_file(c['code']),'Read catalogue →','card-link')+'</article>'
def profile(path,big=False):
 return f'<section class="profile {"bio-big" if big else ""}"><img src="{esc(rel(path,"assets/enrico-papalini.jpg"))}" width="155" height="157" alt="Author photograph of Enrico Papalini from his published author biography" loading="lazy"><div><p class="eyebrow">About the author</p><h2>Enrico Papalini</h2><p>{esc(C["bio"])}</p><p class="micro">{esc(C["bio_note"])}</p>'+link(path,'about.html','About this project →','card-link')+'</div></section>'
def ack(path):
 return '<aside class="ack"><p><strong>Built on the work of Software Engineering @ PoliMi.</strong> The starting bibliography was curated by <strong>Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara</strong>: 193 works across nine streams in the 8 October 2026 snapshot. The collection, original classification and annotations are their contribution; the independent atlas and editorial extensions are Enrico Papalini’s.</p><p>'+link(path,'https://www.sepolimi.com/p/se-ai-annotated-bibliography','Read the original bibliography ↗',external=True)+' · '+link(path,'attribution.html','Full credits and evidence boundaries')+'</p></aside>'
def grouped_sources(path,records,kind=None):
 by=collections.defaultdict(list)
 for n in records:by[n.get('collection')].append(n)
 text=''
 for c in COLS:
  if not by[c]:continue
  text+=f'<section class="section"><h2>{esc(COLS[c]["title"])} <span class="pill">{len(by[c])}</span></h2><ul class="compact-list">'
  for n in by[c]:text+='<li>'+link(path,record_file(n),f'<span class="mono">{esc(n["id"])}</span> — {esc(n["label"])}')+(f'<br><span class="micro">{esc(n.get("authors",""))} · {esc(n.get("year",""))}</span>' if n.get('authors') else '')+'</li>'
  text+='</ul></section>'
 contextual=[n for n in records if n.get('collection') not in COLS]
 if contextual:
  text+='<section class="section"><h2>Book and contextual references</h2><ul class="compact-list">'
  for n in contextual:text+='<li>'+link(path,record_file(n),esc(n['id'])+' · '+esc(n['label']))+'</li>'
  text+='</ul></section>'
 return text or '<p>No source membership recorded in this view.</p>'
def actual_sources_for_chapter(group):
 chapter=NDSE2.chapter(group['id'])
 if chapter:
  return [BY[sid] for sid in NDSE2.cited_ids(chapter) if sid in BY and BY[sid].get('collection')!='N']
 return [n for n in SOURCES if n.get('collection')!='N' and group['id'] in n.get('actual',[])]

def build_group_pages():
 for kind,payloadkey,title in [
  ('streams','themes','Thematic streams'),('topics','topics','Editorial topics'),
  ('chapters','chapters','NDSE2 chapter guides and sources'),('volumes','volumes','Published Non-Deterministic books')]:
  groups=VOLUMES if kind=='volumes' else D[payloadkey]
  index=f'catalogues/{kind}.html';cards=''
  for g in groups:
   path=groupfile(kind,g)
   chapter=NDSE2.chapter(g['id']) if kind=='chapters' else None
   if kind=='chapters':
    actual=actual_sources_for_chapter(g)
    mapped=[n for n in SOURCES if n.get('collection')!='N' and g['id'] in n.get('mapped',[])]
    records=mapped
   elif kind=='volumes':
    records=[n for n in SOURCES if n.get('collection') in {'B','N'} and g['id'] in n.get('volumes',[])]
   else:
    records=[n for n in SOURCES if g['id'] in n.get(kind,[])]
   display=(f'Chapter {g["n"]}: ' if kind=='chapters' else '')+(chapter['title'] if chapter else g['label'])
   if kind=='volumes' and g['id']=='V03':
    display='Non-Deterministic Spec-Driven Development — Enterprise / second edition'
   if kind=='chapters':
    count_text=f'{len(actual)} cited atlas references · {len(mapped)} editorial reading mappings'
   elif kind=='volumes':
    count_text=f'{len(records)} chapter or file records'
    count_text+=' · Published second edition' if g['id']=='V06' else ' · Earlier volume'
   else:
    count_text=f'{len(records)} mapped records'
   cards+='<article class="group-item"><h3>'+link(index,path,esc(display))+'</h3>'
   if chapter and chapter.get('title_it'):
    cards+=f'<p lang="it">{esc(chapter["title_it"])}</p>'
   cards+=f'<p>{esc(count_text)}</p></article>'
   descriptions={
    'streams':'Current source memberships across the atlas. A source can address more than one stream.',
    'topics':'Editorial topic mappings connect related questions across sources and book chapters.',
    'chapters':'A guide to the published second edition, with literal citations separated from wider editorial reading suggestions.',
    'volumes':'Published book metadata and the corresponding chapter or file records. Volume IDs preserve the atlas history.'}
   desc=descriptions[kind]
   b='<div class="crumbs">'+link(path,'catalogues/index.html','Catalogues')+' / '+link(path,index,esc(title))+'</div>'+heading(display,g['id'],desc)
   grouping={'streams':'theme','topics':'topic','chapters':'chapter','volumes':'volume'}[kind]
   codes='B,N' if kind=='volumes' and 'N' in COLS else ('B' if kind=='volumes' else ','.join(COLS))
   b+='<div class="actions">'+link(path,atlasurl(collection=codes,grouping=grouping,group=g['id']),'Open this group in the atlas','button primary')
   if chapter:
    b+=link(path,record_file(BY[chapter['id']]),'Chapter catalogue entry','button')
   b+='</div>'
   if kind=='volumes':
    if g['id']=='V06' and NDSE2.chapters:
     b+=NDSE2.edition_metadata(path,link)
     b+='<p>'+link(path,collection_file('N'),'NDSE2 · published second edition →','card-link')+'</p>'
    else:
     book=next((n for n in BOOKS if n.get('attributes',{}).get('volume_id')==g['id']),None)
     if book:
      b+=fmt_meta(book['attributes'],[('title','Published title'),('subtitle','Subtitle'),('year','Year'),('edition_number','Edition'),('isbn','ISBN, as recorded'),('publisher','Publisher'),('metadata_verification','Metadata basis')])
   if kind=='chapters':
    if chapter:
     b+='<section class="section"><h2>Chapter guide</h2>'+NDSE2.chapter_content(chapter,path,link,BY,record_file,include_evidence=False)+'</section>'
    b+='<section class="section"><h2>Cited in the published chapter</h2>'
    b+=f'<p class="note">{len(actual)} linked atlas references from literal citations in the English and Italian editions. General bibliography membership and identifier-index entries are counted separately.</p>'
    b+=grouped_sources(path,actual)+'</section>'
    if chapter:
     b+=NDSE2.citation_evidence(chapter,path,link,BY,record_file)
    b+='<section class="section"><h2>Editorial reading mappings</h2><p class="note">Broader topical suggestions can overlap the cited sources. A mapping does not add a citation to the published edition or establish that a practice is effective.</p>'+grouped_sources(path,mapped)+'</section>'
   else:
    b+=grouped_sources(path,records)
   page(path,display,b,desc)
  descriptions={
   'streams':f'{len(D["themes"])} streams connect the original SE@PoliMi organization with the atlas’s additional collection mappings.',
   'topics':f'{len(D["topics"])} editorial topics help follow engineering questions through the current graph.',
   'chapters':f'{len(D["chapters"])} chapter guides for the published NDSE2 edition, with English and Italian titles, learning goals, outlines and traceable references.',
   'volumes':f'{len(VOLUMES)} published books: {len(EARLIER_VOLUMES)} earlier volumes and the current second edition of Non-Deterministic Software Engineering.'}
  desc=descriptions[kind]
  page(index,title,heading(title,'Browse by group',desc)+'<div class="group-columns">'+cards+'</div>',desc)

def build_landing_pages():
 path='index.html'
 hero='<section class="hero"><div>'+heading(C['title'],'A navigable evidence collection','Explore the research, practitioner writing and engineering ideas behind AI-assisted software development. Follow connections to their sources and read the limits of each claim.')
 hero+='<div class="actions">'+link(path,'swe_knowledge_graph.html','Open the interactive atlas →','button primary')+link(path,'catalogues/index.html','Browse the catalogues','button')
 if 'N' in COLS:
  hero+=link(path,collection_file('N'),'NDSE2 · published second edition','button')
 hero+='</div><p class="micro">Starts with the original PoliMi source collection. Select the other collections to expand the view.</p></div>'
 hero+='<figure class="hero-visual">'+link(path,'swe_knowledge_graph.html',f'<img src="{esc(rel(path,"assets/atlas-preview.webp"))}" width="1280" height="800" alt="Knowledge Atlas with its original PoliMi starting collection">')+'<figcaption>Explore the connections or read each source in a static catalogue.</figcaption></figure></section>'
 counts='<div class="count-strip">'+''.join(f'<div><b>{n:,}</b><span>{esc(label)}</span></div>' for n,label in [
  (EXTERNAL_COUNT,'External source records'),(COUNTS['B'],'Earlier-book records'),(COUNTS['N'],'Published NDSE2 chapters'),(len(COLS),'Source collections')])+'</div>'
 paths=[
  ('streams',f'{len(D["themes"])} thematic streams','The original research organization, with additional source mappings.'),
  ('topics',f'{len(D["topics"])} editorial topics','Follow an engineering question across source collections.'),
  ('volumes',f'{len(VOLUMES)} published books','Distinguish the earlier volumes from the published NDSE2 edition.'),
  ('chapters',f'{len(D["chapters"])} chapter guides','Read chapter outlines and separate printed citations from suggested reading.')]
 grids='<div class="path-grid">'+''.join('<article class="path-card"><h3>'+link(path,f'catalogues/{name}.html',esc(title))+'</h3><p>'+esc(desc)+'</p></article>' for name,title,desc in paths)+'</div>'
 practice_card=f'<article class="collection-card"><div class="card-top"><span class="code">PRACTICE LAYER</span><span class="pill">{len(PRACTICES)} descriptors</span></div><h3>'+link(path,'catalogues/practices.html','Patterns and their provenance')+f'</h3><p>Explore {len(PRACTICES)} reconciled practice descriptors and {len(OCCURRENCES)} historical occurrences. Engineering proposals retain their evidence limits.</p>'+link(path,'catalogues/practices.html','Read practices →','card-link')+'</article>'
 body=hero+counts+NDSE2.introduction(path,link,heading=True)+ack(path)
 body+='<section class="section"><div class="section-head"><h2>Read the source collections</h2>'+link(path,'catalogues/index.html','All catalogues →')+'</div><div class="card-grid">'+''.join(collection_card(c,path) for c in C['collections'])+practice_card+'</div></section>'
 body+='<section class="section"><h2>Follow another route</h2>'+grids+'</section>'+profile(path)
 page(path,C['title'],body,f'Explore {len(COLS)} source collections, an interactive graph and the published NDSE2 chapter guides.',active='')
 page('knowledge-atlas.html',C['title'],body,'Project landing page, also suitable when preserving a separate existing homepage.',active='')
 path='catalogues/index.html'
 extra=paths+[
  ('practices','Practice descriptors',f'{len(PRACTICES)} editorial practices, with limits and source occurrences.'),
  ('occurrences','Historical occurrences',f'{len(OCCURRENCES)} occurrences in earlier books, preserving conceptual genealogy.')]
 body=heading('Source catalogues',f'{len(COLS)} collections · one evidence map','All entries are present in static HTML. Search, filters, data downloads and permanent record links complement the interactive atlas.')+ack(path)
 body+='<div class="card-grid">'+''.join(collection_card(c,path) for c in C['collections'])+'</div>'
 body+='<section class="section"><h2>Additional catalogue views</h2><div class="path-grid">'+''.join('<article class="path-card"><h3>'+link(path,f'catalogues/{name}.html',esc(title))+'</h3><p>'+esc(desc)+'</p></article>' for name,title,desc in extra)+'</div></section>'
 page(path,'Source catalogues',body,'Static source catalogues, published book chapters and evidence provenance.')

def build_about_page():
 path='about.html'
 labels=', '.join(COLS)
 body=heading('About this project','Independent work by Enrico Papalini','A companion for asking better questions about AI and software engineering, built around source provenance.')+profile(path,True)
 body+=f"""<div class="prose"><h2>Why an atlas?</h2><p>The project connects research records, practitioner publications and the engineering questions explored in the <em>Non-Deterministic</em> book series. The interactive atlas exposes relationships; the catalogues make each record accessible as an ordinary web page.</p><h2>What the labels mean</h2><p>{esc(labels)} identify collections and their provenance. Papers, interviews, conceptual essays, book chapters and small experiments retain their distinct source types. Records show access restrictions, caveats and the scope of source inspection.</p><h2>The published second edition</h2><p>NDSE2 is represented by {COUNTS['N']} chapter records. Guides include English and Italian titles, learning goals, outlines and source references. On 18 October 2026, the author confirmed that the book was already published. Its metadata separates that confirmation from a first-publication date.</p><p>"""
 body+=link(path,'catalogues/ndse2.html','NDSE2 · published second edition →')+'</p>'
 body+='<h2>Biography and photograph</h2><p>The biography and author photograph come from the author’s own <em>Non-Deterministic Loop Engineering</em> materials (About the Author, PDF page 277; printed page 265). The photograph was extracted, resized and saved locally for this project.</p><p>'+link(path,'source/author_provenance.json','Photo and biography provenance')+'</p><p>Connect through '+link(path,'https://github.com/popoloni','GitHub',external=True)+' or explore the '+link(path,'https://www.amazon.com/dp/B0GHCXPBRM','Non-Deterministic series',external=True)+'.</p></div>'+ack(path)
 page(path,'About Enrico Papalini and the project',body,'Author biography and the purpose of the independent Knowledge Atlas.',active='About')

def build_attribution():
 path='attribution.html'
 f_printed=sum(bool(n.get('printed')) for n in SOURCES if n.get('collection')=='F')
 body=heading('Credits & provenance','Attribution is part of the model','The starting bibliography, source authors, editorial additions and evidence boundaries.')
 body+=f"""<div class="prose"><h2>The starting collection: Software Engineering @ PoliMi</h2><p><em>The SE &amp; AI Annotated Bibliography</em> was curated by <strong>Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara</strong>, Software Engineering @ PoliMi. The retained original snapshot contains 193 works, dated 8 October 2026 and published on 9 October. Credit for the original collection, classification and annotations belongs to the curators.</p><p><a href="https://www.sepolimi.com/p/se-ai-annotated-bibliography" target="_blank" rel="noopener noreferrer">Original annotated bibliography ↗</a></p><h2>Independent editorial additions</h2><p>Enrico Papalini developed the graph, interface, independent summaries, cross-source comparisons, practice genealogy and book mappings with AI assistance. These are separate from the curators’ original work. No endorsement by Polimi, the source authors or their institutions is implied.</p><h2>Practitioner collections</h2><p>The Osmani collection credits Addy Osmani. The Pragmatic Engineer collection preserves named authors, interview participants and guest contributors. Publisher affiliation is not a substitute for an article byline.</p><p>The Fowler website collection contains {COUNTS['F']} records. It preserves the original <a href="https://martinfowler.com/articles/exploring-gen-ai.html" target="_blank" rel="noopener noreferrer">Exploring Generative AI</a> series and explicitly labels the adjacent website articles added in this refresh. Individual bylines remain attached to each article; Birgitta Böckeler’s contribution as writer and editor is acknowledged. Hosting on martinfowler.com does not establish Martin Fowler authorship or Thoughtworks endorsement.</p><h2>Books and published citations</h2><p>The {COUNTS['B']} B records describe chapters and informative files in {len(EARLIER_VOLUMES)} earlier books. The {COUNTS['N']} N records describe the published second edition of <em>Non-Deterministic Software Engineering</em>. Its guides trace literal citations in the English and Italian chapter sources separately from general bibliography membership and the identifier index. {f_printed} Fowler records occur in the published bibliography; newly suggested reading is labelled according to its actual status.</p><p>The {len(PRACTICES)} practice descriptors and {len(OCCURRENCES)} historical occurrences record conceptual genealogy. Repeated discussion of an idea is not independent empirical support.</p><h2>Evidence and access boundaries</h2><p>This release combines the retained historical graph with the documented {esc(C['graph_snapshot'])} source refresh and the published-book citation extraction. Inspection scope and access limitations are recorded per source. The builder reproduces those audited records; it does not execute studies, replicate statistical analyses or perform a production pilot. W records can contain lead-author-only metadata; consult the original publication for full bibliographic details.</p><p>The current graph contains {len(D['nodes']):,} nodes, {len(D['edges']):,} keyed relationships and {len(D['relations']):,} relation types. Historical IDs and the original PoliMi starting collection remain available. Literal source citations, source-published links and editorial mappings have distinct meanings.</p><p>"""
 body+=link(path,RESEARCH_AUDIT,'Read the source-review audit')+' · '+link(path,RELEASE_NOTES,'Read the update notes')+'</p>'
 body+='<h2>Rights and redistribution</h2><p>The inherited attribution record notes the SE@PoliMi publication’s stated CC BY-NC-ND 4.0 terms unless otherwise noted. Third-party works retain their own terms. This package contains metadata, concise paraphrases, chapter guides and provenance records. It grants no new rights to full articles, subscriber material, figures or datasets.</p><p>No blanket licence is assigned to every source in the atlas. The author photograph is supplied for this project. Complete third-party articles and complete book manuscripts are not distributed in the website package.</p></div>'
 page(path,'Credits, provenance and evidence boundaries',body,'Credits to the original curators and source authors, with evidence and access boundaries.')
 text=f"""# Attribution and provenance

The starting collection is **The SE & AI Annotated Bibliography**, curated by **Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara**, **Software Engineering @ PoliMi**: https://www.sepolimi.com/p/se-ai-annotated-bibliography. Its original snapshot contains 193 works (8 October 2026; published 9 October).

The original collection, classification and annotations belong to the curators. The atlas, interface, independent summaries, additional collections, editorial mappings and book genealogy are Enrico Papalini’s independent work with AI assistance. No institutional endorsement is implied.

Addy Osmani and all credited contributors to The Pragmatic Engineer retain their individual authorship. The Fowler website collection preserves article bylines and Birgitta Böckeler’s editorial contribution to [Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html). Adjacent website articles added in this refresh are explicitly labelled.

The current release combines the historical graph with the documented {C['graph_snapshot']} source refresh and published NDSE2 citation extraction. Source inspection does not amount to causal validation or independent replication. The {COUNTS['N']} N records are published-book chapter guides, not independent research studies. The {COUNTS['B']} B records preserve earlier-book genealogy.

The inherited rights notice records SE@PoliMi’s stated CC BY-NC-ND 4.0 terms unless otherwise noted. No blanket licence for third-party content is granted. Full external manuscripts, subscriber article bodies and complete book texts are not bundled. See [the full notice](attribution.html), [source-review audit]({RESEARCH_AUDIT}) and [update notes]({RELEASE_NOTES}).
"""
 (ROOT/'ATTRIBUTION.md').write_text(text,encoding='utf-8')

def build_downloads():
 path='downloads.html';rows=''
 datasets=[(COLS[c]['slug'],COLS[c]['title']) for c in COLS]+[
  ('all-sources',f'All {len(SOURCES)} source and chapter records'),
  ('practices',f'{len(PRACTICES)} practice descriptors'),
  ('occurrences',f'{len(OCCURRENCES)} practice occurrences'),
  ('practice-families',f'{len(FAMILIES)} practice families'),
  ('published-books',f'{len(BOOKS)} published book records')]
 for name,title in datasets:
  rows+='<tr><th scope="row">'+esc(title)+'</th><td>'+link(path,f'data/catalogues/{name}.json','JSON')+'</td><td>'+link(path,f'data/catalogues/{name}.csv','CSV')+'</td></tr>'
 body=heading('Download the data','Static files · no API required','Current catalogues and graph exports represent the same audited release. JSON retains complete records; CSV provides a compact tabular view.')
 body+='<div class="table-wrap"><table><caption>Current catalogue exports</caption><thead><tr><th scope="col">Catalogue</th><th scope="col">Complete records</th><th scope="col">Tabular export</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
 body+='<section class="section"><h2>The current complete graph</h2><div class="actions">'+link(path,GRAPH_GRAPHML,'Current GraphML','button')+link(path,GRAPH_JSON,'Current graph JSON','button')+link(path,'data/catalogue-data.zip','All current catalogue data (ZIP)','button primary')+'</div>'
 body+=f'<p class="note">Graph v{esc(C["graph_version"])} · {esc(C["graph_snapshot"])} · {len(D["nodes"]):,} nodes · {len(D["edges"]):,} keyed relationships · {len(D["relations"]):,} relation types.</p></section>'
 body+='<section class="section"><h2>Published NDSE2 evidence and this update</h2><ul class="compact-list">'
 for target,label in [('source/ndse2_book.json','Published edition metadata, chapter structure and citation provenance'),(RESEARCH_AUDIT,'Source-review audit'),(RELEASE_NOTES,'What changed in this release')]:
  body+='<li>'+link(path,target,label)+'</li>'
 for suffix,label in [('json','NDSE2 sections and references (JSON)'),('csv','NDSE2 sections and references (CSV)')]:
  target=f'data/catalogues/ndse2-sections.{suffix}'
  if (ROOT/target).exists():body+='<li>'+link(path,target,label)+'</li>'
 body+='</ul></section>'
 body+='<section class="section"><h2>Historical graph and catalogue files</h2><p class="note">These files retain their original version names and wording. Use the current graph above for the refreshed atlas. Relative links inside historical Markdown can refer to the original book archive.</p><ul class="compact-list">'
 for target,label in [('data/graph/knowledge_graph_v12.json','Historical v12 graph JSON'),('data/graph/knowledge_graph_v12.graphml','Historical v12 GraphML')]:
  if (ROOT/target).exists():body+='<li>'+link(path,target,label)+'</li>'
 for item in sorted((ROOT/'data/originals').glob('*')):
  if item.is_file():body+='<li>'+link(path,item.relative_to(ROOT).as_posix(),esc(item.name))+f' <span class="micro">({item.stat().st_size/1024:.0f} KB)</span></li>'
 body+='</ul></section><section class="section"><h2>Project files</h2><ul class="compact-list">'
 for target,label in [
  ('README.md','Project README'),('DEPLOYMENT.md','Deployment instructions'),('ATTRIBUTION.md','Attribution'),
  ('source/build_site.py','Catalogue builder'),('source/build_ndse2_pages.py','NDSE2 companion renderer'),
  ('source/site_config.json','Project configuration'),('source/author_provenance.json','Photo and biography provenance'),
  ('verification/report.html','Website validation report'),('SHA256SUMS.txt','Package integrity manifest')]:
  body+='<li>'+link(path,target,label)+'</li>'
 body+='</ul></section>'
 page(path,'Downloads',body,'Current graph exports, static catalogues, published-book evidence, historical files and build sources.',active='Downloads')

def write_readme_and_deployment():
 rows='\n'.join(f'| {c["code"]} | [{c["title"]}]({collection_file(c["code"])}) | {COUNTS[c["code"]]} |' for c in C['collections'])
 readme=f"""# {C['title']}

An independent, source-traceable map of research and practitioner writing about AI-assisted software development, by **Enrico Papalini**. The graph and static catalogues connect publications, topics, engineering practices and book chapters while retaining their evidence limits.

**[Open the published atlas]({C['canonical_atlas']})** · **[Local atlas](swe_knowledge_graph.html)** · **[Catalogues](catalogues/index.html)** · **[NDSE2 · published second edition](catalogues/ndse2.html)** · **[Downloads](downloads.html)** · **[Update notes]({RELEASE_NOTES})**

## The starting collection

The foundation is **[The SE & AI Annotated Bibliography](https://www.sepolimi.com/p/se-ai-annotated-bibliography)**, curated by **Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara**, **Software Engineering @ PoliMi**. Its original 8 October 2026 snapshot contains 193 works. The original classification and annotations are the curators’ contribution. This independent atlas and its editorial extensions do not imply institutional endorsement.

The atlas opens with the original PoliMi collection. Additional collections, context and relationship controls are available through the interface. Source IDs and established links remain stable.

## Current catalogues

| ID | Collection | Records |
|---|---|---:|
{rows}

Also browse **[{len(D['themes'])} streams](catalogues/streams.html)**, **[{len(D['topics'])} topics](catalogues/topics.html)**, **[{len(VOLUMES)} published books](catalogues/volumes.html)**, **[{len(D['chapters'])} NDSE2 chapter guides](catalogues/chapters.html)**, **[{len(PRACTICES)} practice descriptors](catalogues/practices.html)** and **[{len(OCCURRENCES)} historical occurrences](catalogues/occurrences.html)**. Static entries work without JavaScript; optional filters improve navigation.

## Published NDSE2 second edition

On **18 October 2026**, the author confirmed that the book was already published. That confirmation records availability, not an inferred first-publication date. ISBN and first-publication date are displayed only if supplied in the edition metadata.

The **{COUNTS['N']} chapter records** contain concise English summaries, Italian titles, learning goals, outlines and source links. Literal citations from the English and Italian chapter files are distinguished from bibliography membership, the identifier index and broader editorial reading mappings. The full manuscripts are not included in the website.

[Read the chapter guides](catalogues/ndse2.html) · [Edition and extraction provenance](source/ndse2_book.json) · [Source-review audit]({RESEARCH_AUDIT})

## Authorship and evidence

The Fowler collection credits each article’s actual author and acknowledges **Birgitta Böckeler** as contributor and editor of [Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html). Its adjacent website additions are labelled separately. The Pragmatic Engineer catalogue preserves guest and interview roles. Collection membership does not establish peer review, causal support or independent replication.

## About Enrico Papalini

<img src="assets/enrico-papalini.jpg" alt="Enrico Papalini — author photograph" width="140">

{C['bio']}

Photo and biography are adapted from the author’s own *Non-Deterministic Loop Engineering* author page. [Photo provenance](source/author_provenance.json) · [About the project](about.html) · [GitHub](https://github.com/popoloni). This project expresses the author’s views, not those of his employers or cited institutions.

## Publish or update the static site

Copy the package contents to the configured Pages publishing folder, preserving relative paths and `.nojekyll`. The homepage is `index.html`; the interactive atlas remains `swe_knowledge_graph.html`. A `knowledge-atlas.html` entrypoint is also supplied. A delta package contains only files to add or overwrite and is applied to the existing site using the same relative paths.

No server application, API key, framework or CDN is required. See [DEPLOYMENT.md](DEPLOYMENT.md) for local preview and rebuild instructions.

**Graph v{C['graph_version']} · {C['graph_snapshot']}**. **Website v{C['site_version']} · {C['build_date']}**. The current graph contains **{len(D['nodes']):,} nodes**, **{len(D['edges']):,} keyed relationships** and **{len(D['relations']):,} relation types**. Historical v12 exports remain labelled as historical.

[Credits and boundaries](attribution.html) · [Validation report](verification/report.html)
"""
 (ROOT/'README.md').write_text(readme,encoding='utf-8')
 deployment=f"""# Publish or update this static site

## Apply the package

Copy the extracted files to the folder already configured as the GitHub Pages publishing source. Preserve all relative paths and `.nojekyll`. The extracted `index.html` must be directly inside that folder.

For a **full package**, use the complete site tree. For a **delta package**, add or overwrite only the included files at their existing relative paths. Follow the accompanying delta instructions for the baseline and file list.

The homepage is `index.html`; the interactive atlas is `swe_knowledge_graph.html`. If an unrelated homepage must be retained, use `knowledge-atlas.html` as the project entrypoint. Local links work at a user-site root or within a project subdirectory.

## Preview locally

Static catalogue contents remain readable with JavaScript disabled. To preview normal browser navigation, run from the site folder:

```sh
python -m http.server 8000
```

Open `http://localhost:8000/`. External source links still follow the publisher’s access conditions.

## Rebuild from the supplied sources

Rebuild the graph first, then the static website. The graph builder reads the preserved v12 baseline, audited article update, final bilingual metadata in `source/ndse2_book.json` and the supplied graph template. The static builder reads the resulting `source/{ATLAS_SOURCE.name}` and `source/site_config.json`. These steps use frozen local inputs and require no network or original book manuscript.

```sh
python source/build_graph_v13.py
python source/build_site.py
python source/write_release_report.py
python source/check_site.py
python source/check_reproducibility.py
python source/write_release_report.py
```

The reproducibility check rebuilds the graph and site twice in an isolated temporary copy and compares the generated bytes with this folder. The report generator reads verification records; it does not run browser tests. Current browser records must match the current interactive HTML hash. To rerun browser checks, use the supplied `source/test_update_browser.js` with Node.js, Playwright and a Chromium-family browser; its usage header documents the options. Reports and screenshots from that script are written outside the site tree. Copy the current browser and relationship-check JSON records into `verification/` before regenerating the release report.

Current graph downloads are `{GRAPH_JSON}` and `{GRAPH_GRAPHML}`. The original v12 exports remain historical artefacts and should not replace those current files. A subsequent research refresh needs its own source audit and updated graph, followed by this static build.

The release notes and source-review audit are supplied alongside the generated pages. Local validation verifies the package; publication to a GitHub account is a separate deployment action.
"""
 (ROOT/'DEPLOYMENT.md').write_text(deployment,encoding='utf-8')

def build():
 # The graph engine is supplied by the audited current source; add only static-site navigation.
 patch=(SOURCE/'atlas_navigation_patch.js').read_text(encoding='utf-8')
 marker='buildControls();boardSize();rebuild();'
 if marker not in BASE:raise ValueError('Current atlas is missing the expected navigation insertion point')
 modified=BASE.replace(marker,marker+'\n'+patch)
 nav='<a href="catalogues/index.html" id="siteCataloguesLink" title="Browse static catalogues" aria-label="Browse static catalogues" style="display:inline-flex;gap:6px;align-items:center;padding:7px;border:1px solid #dce3e9;border-radius:7px;color:#245e70;text-decoration:none;font-size:11px"><svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 3h6l1 2 1-2h6v14h-6l-1 1-1-1H3zM10 5v13" stroke="currentColor" stroke-width="1.4"/></svg><span class="desktop">Catalogues</span></a>'
 modified=modified.replace('<div class="top-actions">','<div class="top-actions">'+nav,1)
 (ROOT/'swe_knowledge_graph.html').write_text(modified,encoding='utf-8')
 (ROOT/'data/catalogues').mkdir(parents=True,exist_ok=True)
 for code,c in COLS.items():write_dataset(c['slug'],[n for n in SOURCES if n['collection']==code])
 for name,records in [('all-sources',SOURCES),('practices',PRACTICES),('occurrences',OCCURRENCES),('practice-families',FAMILIES),('published-books',BOOKS)]:
  write_dataset(name,records)
 for code,c in COLS.items():
  path=collection_file(code);records=[n for n in SOURCES if n['collection']==code]
  if code=='N':records.sort(key=lambda n:int(n.get('attributes',{}).get('chapter_number') or n['id'].split('C')[-1]))
  body='<div class="crumbs">'+link(path,'index.html','Home')+' / '+link(path,'catalogues/index.html','Catalogues')+' / '+esc(c['short'])+'</div>'
  body+=heading(c['title'],f'{code} collection · {len(records)} records',c['description'])+collection_nav(path,code)
  if code=='W':body+=ack(path)
  if code=='F':
   printed=sum(bool(n.get('printed')) for n in records)
   body+='<p class="note">The collection follows the host website, with each article’s actual byline. The original Exploring Generative AI series credits Birgitta Böckeler as contributor and editor; adjacent website articles are labelled individually. '
   body+=f'{printed} records are included in the published NDSE2 bibliography. Literal chapter citations and later editorial suggestions remain distinct.</p>'
  if code=='N':body+=NDSE2.introduction(path,link)
  body+='<div class="actions">'+link(path,atlasurl(collection=code),'Explore this collection in the atlas','button primary')+link(path,f'data/catalogues/{c["slug"]}.json','JSON catalogue','button')+link(path,f'data/catalogues/{c["slug"]}.csv','CSV catalogue','button')+'</div>'
  if code=='B':body+='<p>'+link(path,'catalogues/volumes.html',f'Browse {len(EARLIER_VOLUMES)} earlier volumes and the published NDSE2 edition →')+'</p>'
  body+=filter_bar(path,len(records),D['themes'])+'<div class="records">'+''.join(record(n,path) for n in records)+'</div>'
  page(path,c['title'],body,c['description'],active='NDSE2' if code=='N' else 'Catalogues')
 for name,title,records,desc in [
  ('practices','Practice descriptors',PRACTICES,f'{len(PRACTICES)} reconciled editorial descriptors from the Non-Deterministic series, with their recorded limits and historical origins.'),
  ('occurrences','Historical practice occurrences',OCCURRENCES,f'{len(OCCURRENCES)} source occurrences across {len(EARLIER_VOLUMES)} earlier volumes. These trace where practices were discussed.')]:
  path=f'catalogues/{name}.html'
  body=heading(title,'Series practice catalogue',desc)+'<div class="actions">'+link(path,'catalogues/practices.html','Descriptors','button')+link(path,'catalogues/occurrences.html','Occurrences','button')+link(path,f'data/catalogues/{name}.json','JSON','button')+link(path,f'data/catalogues/{name}.csv','CSV','button')+'</div>'
  body+=filter_bar(path,len(records),EARLIER_VOLUMES if name=='occurrences' else None,'volumes','Volume')+'<div class="records">'+''.join(record(n,path) for n in records)+'</div>'
  page(path,title,body,desc)
 build_group_pages()
 build_landing_pages()
 build_about_page()
 build_attribution()
 build_downloads()
 write_readme_and_deployment()
 date=tuple(int(part) for part in C['build_date'][:10].split('-'))+(0,0,0)
 with zipfile.ZipFile(ROOT/'data/catalogue-data.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
  for item in sorted(list((ROOT/'data/catalogues').glob('*'))+list((ROOT/'data/originals').glob('*'))):
   if not item.is_file():continue
   info=zipfile.ZipInfo(item.relative_to(ROOT/'data').as_posix(),date_time=date)
   info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
   archive.writestr(info,item.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 (SOURCE/'page_inventory.json').write_text(json.dumps(sorted(set(PAGES+['swe_knowledge_graph.html'])),indent=2)+'\n',encoding='utf-8')
 summary={
  'site_version':C['site_version'],'graph_snapshot':C['graph_snapshot'],'graph_source':ATLAS_SOURCE.name,
  'graph_nodes':len(D['nodes']),'graph_edges':len(D['edges']),'graph_relation_types':len(D['relations']),
  'source_counts':dict(COUNTS),'static_source_records':len(SOURCES),'external_source_records':EXTERNAL_COUNT,
  'practice_descriptors':len(PRACTICES),'practice_occurrences':len(OCCURRENCES),
  'published_books':len(BOOKS),'ndse2_chapters':len(NDSE2.chapters),
  'group_pages':{'streams':len(D['themes']),'topics':len(D['topics']),'chapters':len(D['chapters']),'volumes':len(VOLUMES)},
  'html_pages_built':len(PAGES)+1,'graph_payload_unchanged':True,
  'graph_payload_matches_current_source':True,'new_empirical_verification':False}
 (SOURCE/'build_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
 print(f'Built {len(PAGES)+1} HTML pages, {len(SOURCES)} source/chapter records and {len(NDSE2.chapters)} NDSE2 guides from {ATLAS_SOURCE.name}.')

if __name__=='__main__':build()
