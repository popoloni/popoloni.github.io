#!/usr/bin/env python3
"""Regenerate static catalogues from the frozen v12 atlas. Python 3.10+, standard library only.
No network or research refresh is performed. All record wording/attributes remain source-derived.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, html, io, json, os, re, shutil, unicodedata, zipfile
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent
C=json.loads((SOURCE/'site_config.json').read_text(encoding='utf-8'))
BASE=(SOURCE/'atlas_v12_original.html').read_text(encoding='utf-8')
D=json.loads(re.search(r'<script id="graph-data" type="application/json">(.*?)</script>',BASE,re.S).group(1))
BY={n['id']:n for n in D['nodes']}
COLS={c['code']:c for c in C['collections']}
SOURCES=[n for n in D['nodes'] if n.get('collection') in COLS]
PRACTICES=[n for n in D['nodes'] if n['kind']=='practice_descriptor']
OCCURRENCES=[n for n in D['nodes'] if n['kind']=='practice_occurrence']
FAMILIES=[n for n in D['nodes'] if n['kind']=='practice_family']
BOOKS=[n for n in D['nodes'] if n['kind']=='published_book']
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
 nav=''.join(link(path,t,esc(l)) if active!=l else f'<a aria-current="page" href="{esc(rel(path,t))}">{esc(l)}</a>' for l,t in [('Atlas','swe_knowledge_graph.html'),('Catalogues','catalogues/index.html'),('About','about.html'),('Downloads','downloads.html')])
 s=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="author" content="Enrico Papalini"><meta name="description" content="{esc(description)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="website"><title>{esc(title)} · Knowledge Atlas</title><link rel="stylesheet" href="{esc(rel(path,'assets/site.css'))}"><script src="{esc(rel(path,'assets/catalogues.js'))}" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="site-head"><div class="nav">{link(path,'index.html',LOGO+'<span><small>AI & Software Engineering</small><strong>Knowledge Atlas</strong></span>','brand')}<nav class="nav-links" aria-label="Main navigation">{nav}</nav></div></header><main id="main" class="wrap {'wide' if wide else ''}">{body}</main><footer class="site-foot"><div class="foot-inner"><p>Independent atlas by Enrico Papalini · Site v{C['site_version']} · Graph snapshot {C['graph_snapshot']}<br>Source collections identify provenance, not evidence quality.</p><p>{link(path,'attribution.html','Credits &amp; evidence boundaries')} · {link(path,'README.md','README')} · {link(path,'verification/report.html','Build checks')}</p></div></footer></body></html>'''
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
 evidence=a.get('reviewed_evidence_class') or a.get('evidence_class') or ''
 summary=n.get('summary') or a.get('contribution') or a.get('summary') or a.get('required_revision') or a.get('purpose') or ''
 limit=n.get('limitation') or a.get('limitation') or ''
 title=n['label'];anchor=quote(n['id'],safe='')
 pills=f'<span class="pill">{esc(col.get("short",n["kind"].replace("_"," ")))}</span>'
 if n.get('printed'):pills+='<span class="pill">Recorded in book bibliography</span>'
 if a.get('access_status'):pills+=f'<span class="pill">{esc(a["access_status"].replace("_"," "))}</span>'
 top=f'<div class="record-top"><span class="code">{esc(n["id"])}</span>{pills}</div><h2><a href="#{anchor}">{esc(title)}</a></h2>'+ (f'<p class="byline">{info}</p>' if info else '')
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
 if n['kind']=='practice_descriptor':
  more+=fmt_meta(a,[('required_revision','Recorded revision'),('disposition','Editorial disposition'),('family','Practice family'),('status','Record status')])
  for occ in parsejson(a.get('occurrences','[]')):
   oid='OCC:'+occ
   if oid in BY:more+='<p>Historical occurrence: '+link(path,record_file(BY[oid]),esc(occ)+' — '+esc(BY[oid]['label']))+'</p>'
 more+=fmt_meta(a,[('source_locator','Inspected passage'),('verification_scope','Inspection scope'),('source_review_scope','Review scope'),('review_scope','Mapping scope'),('access_note','Access note'),('source_path','Original source path'),('source_file','Original source file'),('source_line','Start line'),('source_end_line','End line'),('source_sha256','Original SHA-256'),('provenance','Provenance')])
 if c in COLS:
  actual=n.get('actual',[]);mapped=n.get('mapped',[])
  more+='<div class="mapping"><h3>Recorded chapter citations</h3>'+ ('<br>'.join(named_group_link(path,x,'chapters') for x in actual) if actual else '<span class="muted">None recorded in the current atlas layer.</span>')
  more+='<h3>Editorial chapter mappings</h3>'+ ('<br>'.join(named_group_link(path,x,'chapters') for x in mapped) if mapped else '<span class="muted">None recorded.</span>')+'<p class="micro">A proposed mapping is not a manuscript citation or evidence of effectiveness. Chapter links open static source lists, not the book text.</p></div>'
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
 obj={'meta':{'source':'Frozen v12 atlas payload','snapshot':C['graph_snapshot'],'site_version':C['site_version'],'count':len(records),'note':'Materialized catalogue view; all node fields and attributes retained. No new source verification or empirical validation.'},'records':records}
 p=ROOT/f'data/catalogues/{name}.json';p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 keys=['id','title','authors_as_recorded','date_as_recorded','collection','kind','summary','limitation','recorded_url','streams','topics','actual_chapter_citations','editorial_chapter_mappings','source_path','source_sha256']
 with (ROOT/f'data/catalogues/{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for n in records:
   a=n.get('attributes',{});row=dict(zip(keys,[n['id'],n['label'],n.get('authors',''),n.get('year',''),n.get('collection',''),n['kind'],n.get('summary',''),n.get('limitation',''),n.get('url',''),'; '.join(n.get('streams',[])),'; '.join(n.get('topics',[])),'; '.join(n.get('actual',[])),'; '.join(n.get('mapped',[])),a.get('source_path',a.get('source_file','')),a.get('source_sha256','')]))
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
 for n in records:by[n['collection']].append(n)
 text=''
 for c in COLS:
  if not by[c]:continue
  text+=f'<section class="section"><h2>{esc(COLS[c]["title"])} <span class="pill">{len(by[c])}</span></h2><ul class="compact-list">'
  for n in by[c]:text+='<li>'+link(path,record_file(n),f'<span class="mono">{esc(n["id"])}</span> — {esc(n["label"])}')+(f'<br><span class="micro">{esc(n.get("authors",""))} · {esc(n.get("year",""))}</span>' if n.get('authors') else '')+'</li>'
  text+='</ul></section>'
 return text or '<p>No source membership recorded in this view.</p>'
def build():
 # No graph data mutation; amend navigation only, and keep the v12 app usable as a standalone file.
 patch=(SOURCE/'atlas_navigation_patch.js').read_text()
 modified=BASE.replace('buildControls();boardSize();rebuild();','buildControls();boardSize();rebuild();\n'+patch)
 assert modified!=BASE
 nav='<a href="catalogues/index.html" id="siteCataloguesLink" title="Browse static catalogues" aria-label="Browse static catalogues" style="display:inline-flex;gap:6px;align-items:center;padding:7px;border:1px solid #dce3e9;border-radius:7px;color:#245e70;text-decoration:none;font-size:11px"><svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 3h6l1 2 1-2h6v14h-6l-1 1-1-1H3zM10 5v13" stroke="currentColor" stroke-width="1.4"/></svg><span class="desktop">Catalogues</span></a>'
 modified=modified.replace('<div class="top-actions">','<div class="top-actions">'+nav,1)
 (ROOT/'swe_knowledge_graph.html').write_text(modified,encoding='utf-8')
 # Standardized catalogue exports retain entire node objects. Graph export files remain original.
 for c in COLS:write_dataset(COLS[c]['slug'],[n for n in SOURCES if n['collection']==c])
 write_dataset('all-sources',SOURCES);write_dataset('practices',PRACTICES);write_dataset('occurrences',OCCURRENCES);write_dataset('practice-families',FAMILIES);write_dataset('published-books',BOOKS)
 # Collection pages: every full record is static HTML; JS enhances search only.
 for code,c in COLS.items():
  path=collection_file(code);records=[n for n in SOURCES if n['collection']==code]
  b='<div class="crumbs">'+link(path,'index.html','Home')+' / '+link(path,'catalogues/index.html','Catalogues')+' / '+esc(c['short'])+'</div>'+heading(c['title'],f'{code} collection · {len(records)} records',c['description'])+collection_nav(path,code)
  if code=='W':b+=ack(path)
  if code=='F':b+='<p class="note">The collection is named for the host website. It does not mean every essay was written by Martin Fowler. The series index credits Birgitta Böckeler’s work as contributor and editor.</p>'
  b+='<div class="actions">'+link(path,atlasurl(collection=code),'Explore this collection in the atlas','button primary')+link(path,f'data/catalogues/{c["slug"]}.json','JSON catalogue','button')+link(path,f'data/catalogues/{c["slug"]}.csv','CSV catalogue','button')+'</div>'
  if code=='B':b+='<p>'+link(path,'catalogues/volumes.html','Browse the five parent volumes →')+'</p>'
  b+=filter_bar(path,len(records),D['themes'])+'<div class="records">'+''.join(record(n,path) for n in records)+'</div>'
  page(path,c['title'],b,c['description'])
 # Practice catalogue and historical occurrences remain separate records.
 for name,title,rs,desc in [
  ('practices','Practice descriptors',PRACTICES,'84 reconciled editorial descriptors from the Non-Deterministic series. These are design practices, not 84 independently validated interventions.'),
  ('occurrences','Historical practice occurrences',OCCURRENCES,'87 source occurrences across the five earlier volumes. Occurrences, reconciled descriptors and evidence of effectiveness are different things.')]:
  path=f'catalogues/{name}.html';b=heading(title,'Series practice catalogue',desc)+'<div class="actions">'+link(path,'catalogues/practices.html','Descriptors','button')+link(path,'catalogues/occurrences.html','Occurrences','button')+link(path,f'data/catalogues/{name}.json','JSON','button')+link(path,f'data/catalogues/{name}.csv','CSV','button')+'</div>'
  b+=filter_bar(path,len(rs),D['volumes'][:5] if name=='occurrences' else None,'volumes','Volume')+'<div class="records">'+''.join(record(n,path) for n in rs)+'</div>'
  page(path,title,b,desc)
 # One page per thematic group, topic, volume and book chapter.
 for kind,payloadkey,title in [('streams','themes','Polimi thematic streams'),('topics','topics','Editorial topics'),('chapters','chapters','Book chapter mappings'),('volumes','volumes','Earlier volumes')]:
  glist=D[payloadkey][:5] if kind=='volumes' else D[payloadkey]
  index=f'catalogues/{kind}.html';cards=''
  for g in glist:
   path=groupfile(kind,g)
   if kind=='chapters':
    actual=[n for n in SOURCES if g['id'] in n.get('actual',[])]; mapped=[n for n in SOURCES if g['id'] in n.get('mapped',[])]; records=mapped
   elif kind=='volumes':records=[n for n in SOURCES if n['collection']=='B' and g['id'] in n.get('volumes',[])]
   else:records=[n for n in SOURCES if g['id'] in n.get(kind,[])]
   display=(f'Chapter {g["n"]}: ' if kind=='chapters' else '')+g['label']
   if kind=='volumes' and g['id']=='V03':display='Non-Deterministic Spec-Driven Development — Enterprise / second edition'
   cards+='<article class="group-item"><h3>'+link(index,path,esc(display))+'</h3><p>'+str(len(records))+' mapped records'+(f' · {len(actual)} recorded chapter citations' if kind=='chapters' else '')+'</p></article>'
   desc={'streams':'Membership is taken from the frozen atlas. Multi-stream records can appear on more than one page; each remains one source.', 'topics':'These are editorial topic mappings, not additional source publications or causal relationships.','chapters':'This page separates recorded manuscript citations from wider editorial mappings. The book text is not redistributed here.','volumes':'Informative chapter/file records from the selected earlier book. Internal volume IDs are stable identifiers, not necessarily commercial series order.'}[kind]
   b='<div class="crumbs">'+link(path,'catalogues/index.html','Catalogues')+' / '+link(path,index,esc(title))+'</div>'+heading(display,g['id'],desc)
   grouping={'streams':'theme','topics':'topic','chapters':'chapter','volumes':'volume'}[kind]
   b+='<div class="actions">'+link(path,atlasurl(collection='B' if kind=='volumes' else 'W,O,P,F,B',grouping=grouping,group=g['id']),'Open this group in the atlas','button primary')+'</div>'
   if kind=='volumes':
    book=next((n for n in BOOKS if n['attributes'].get('volume_id')==g['id']),None)
    if book:b+=fmt_meta(book['attributes'],[('title','Published title'),('subtitle','Subtitle'),('year','Year'),('edition_number','Edition'),('isbn','ISBN, as recorded'),('publisher','Publisher'),('metadata_verification','Metadata basis')])
   if kind=='chapters':
    b+='<section class="section"><h2>Recorded chapter citations</h2><p class="note">'+str(len(actual))+' source records in the inherited current-citation layer. Not inferred from topical similarity.</p>'+grouped_sources(path,actual)+'</section><section class="section"><h2>Editorial mapping / proposed use</h2><p class="note">Includes broader proposals and overlaps with actual use. Fowler additions have not been inserted into the book bibliography.</p>'+grouped_sources(path,mapped)+'</section>'
   else:b+=grouped_sources(path,records)
   page(path,display,b,desc)
  desc={'streams':'Nine streams from the starting SE@PoliMi bibliography, with the atlas’s additional collection mappings shown explicitly.','topics':'Thirty editorial topics in the existing graph. These are navigation categories, not new empirical claims.','chapters':'Thirteen chapters in the latest book mapping. Actual citations and editorial suggestions remain separately labelled.','volumes':'The five earlier Non-Deterministic volumes: 111 chapter/file records. Read the human-readable book and chapter names; use the stable IDs for traceability.'}[kind]
  page(index,title,heading(title,'Browse by group',desc)+'<div class="group-columns">'+cards+'</div>',desc)
 # Landing page.
 path='index.html';hero='<section class="hero"><div>'+heading(C['title'],'A navigable evidence collection','Explore the research, practitioner writing and engineering ideas behind AI-assisted software development. Follow each connection back to its source—and keep its limitations in view.')+'<div class="actions">'+link(path,'swe_knowledge_graph.html','Open the interactive atlas →','button primary')+link(path,'catalogues/index.html','Browse the catalogues','button')+'</div><p class="micro">Opens with the original 193 Polimi sources · 0 context nodes · 64 visible relationships</p></div><figure class="hero-visual">'+link(path,'swe_knowledge_graph.html',f'<img src="{rel(path,"assets/atlas-preview.webp")}" width="1280" height="800" alt="The v12 knowledge atlas showing the Polimi-only starting view">')+'<figcaption>Same graph. Two ways to read it: explore connections or browse static records.</figcaption></figure></section>'
 counts='<div class="count-strip"><div><b>399</b><span>External source records</span></div><div><b>111</b><span>Earlier-book records</span></div><div><b>5</b><span>Source collections</span></div><div><b>13</b><span>Mapped book chapters</span></div></div>'
 paths=[('streams','9 thematic streams','The original research organization, with multi-stream membership.'),('topics','30 editorial topics','Follow an engineering question across source collections.'),('volumes','5 earlier volumes','Trace the genealogy of the Non-Deterministic series.'),('chapters','13 book chapters','Separate actual citations from proposed reading mappings.')]
 grids='<div class="path-grid">'+''.join('<article class="path-card"><h3>'+link(path,f'catalogues/{s}.html',esc(t))+'</h3><p>'+esc(d)+'</p></article>' for s,t,d in paths)+'</div>'
 body=hero+counts+ack(path)+'<section class="section"><div class="section-head"><h2>Read the source collections</h2>'+link(path,'catalogues/index.html','All catalogues →')+'</div><div class="card-grid">'+''.join(collection_card(c,path) for c in C['collections'])+'<article class="collection-card"><div class="card-top"><span class="code">PRACTICE LAYER</span><span class="pill">84 descriptors</span></div><h3>'+link(path,'catalogues/practices.html','Patterns and their provenance')+'</h3><p>Explore 84 reconciled practice descriptors and their 87 historical occurrences. Engineering proposals stay distinct from evidence of effectiveness.</p>'+link(path,'catalogues/practices.html','Read practices →','card-link')+'</article></div></section><section class="section"><h2>Follow another route</h2>'+grids+'</section>'+profile(path)
 page(path,C['title'],body,'Explore five source collections, an interactive graph, and static catalogues about AI and software engineering.',active='')
 # Safe additional entrypoint if a site already has an unrelated index.html.
 page('knowledge-atlas.html',C['title'],body,'Project landing page. Use this entrypoint when preserving an existing site homepage.',active='')
 path='catalogues/index.html';page(path,'Source catalogues',heading('Source catalogues','Five collections · one evidence map','Every catalogue below is a static HTML page with all entries already present. Browser search, optional filters, JSON/CSV downloads and permanent record anchors complement the interactive atlas.')+ack(path)+'<div class="card-grid">'+''.join(collection_card(c,path) for c in C['collections'])+'</div><section class="section"><h2>Additional catalogue views</h2><div class="path-grid">'+''.join('<article class="path-card"><h3>'+link(path,f'catalogues/{s}.html',esc(t))+'</h3><p>'+esc(d)+'</p></article>' for s,t,d in paths+[('practices','Practice descriptors','84 editorial practices, with limits and source occurrences.'),('occurrences','Historical occurrences','87 occurrences in the earlier books; not 87 independent studies.')])+'</div></section>','Static source catalogues for Polimi, Osmani, The Pragmatic Engineer, Fowler and the Non-Deterministic books.')
 # About page, with only the user’s sourced professional biography, not private contact details.
 path='about.html';page(path,'About Enrico Papalini and the project',heading('About this project','Independent work by Enrico Papalini','A companion for asking better questions about AI and software engineering, built around source provenance rather than a single score.')+profile(path,True)+'<div class="prose"><h2>Why an atlas?</h2><p>The project connects research records, practitioner publications and the engineering questions explored in the <em>Non-Deterministic</em> book series. It provides two complementary ways to read: the interactive atlas exposes relationships; the catalogues make each record accessible as an ordinary web page.</p><h2>What the labels mean</h2><p>W, O, P, F and B identify collections. They are not evidence grades. A paper, interview, conceptual essay, book chapter and small experiment remain different types of source. The graph retains access restrictions, caveats and unfinished verification work.</p><h2>Biography and photograph</h2><p>The short biography and existing author photograph were taken from the author’s own <em>Non-Deterministic Loop Engineering</em> materials (About the Author, PDF page 277; printed page 265). The photograph was extracted, resized and saved locally for the website; no generative replacement was made. Current professional titles are not independently re-verified by this website build.</p><p>'+link(path,'source/author_provenance.json','Photo and biography provenance')+'</p><p>Connect through '+link(path,'https://github.com/popoloni','GitHub',external=True)+' or explore the '+link(path,'https://www.amazon.com/dp/B0GHCXPBRM','Non-Deterministic series',external=True)+'.</p></div>'+ack(path),'Author biography, photograph and the purpose of the independent Knowledge Atlas.',active='About')
 # Full attribution, bounded by inherited source claims (not new legal advice).
 path='attribution.html';att='''<div class="prose"><h2>The starting collection: Software Engineering @ PoliMi</h2><p><em>The SE &amp; AI Annotated Bibliography</em> was curated by <strong>Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara</strong>, Software Engineering @ PoliMi. The atlas retains the 193-work snapshot dated 8 October 2026, published on 9 October. Credit for the collection, its original classification and annotations belongs to the curators.</p><p><a href="https://www.sepolimi.com/p/se-ai-annotated-bibliography" target="_blank" rel="noopener noreferrer">Original annotated bibliography ↗</a></p><h2>Independent editorial additions</h2><p>Enrico Papalini developed the graph, interface, original atlas summaries, cross-source comparisons, practice genealogy and book mappings, with AI assistance. These are separate from the curators’ original work. No endorsement by Polimi, the original authors or their institutions is implied.</p><h2>Practitioner collections</h2><p>The Osmani collection credits Addy Osmani. The Pragmatic Engineer collection retains the named authors, interview and guest-contributor roles recorded in its catalogue, rather than assuming that every piece is solely authored by Gergely Orosz.</p><p>The Fowler website collection comprises the 33 essays and memos linked from <a href="https://martinfowler.com/articles/exploring-gen-ai.html" target="_blank" rel="noopener noreferrer">Exploring Generative AI</a> in the 13 October 2026 snapshot. Individual bylines remain attached to the articles. Birgitta Böckeler is credited as contributor and editor. Hosting on martinfowler.com is not proof of Martin Fowler authorship or endorsement by Thoughtworks.</p><h2>The earlier books</h2><p>The 111 B records describe informative files and chapters in five books by Enrico Papalini. The 84 practice descriptors and 87 source occurrences record conceptual genealogy. Repeated appearances of an idea in the series do not create independent empirical support.</p><h2>Evidence and access boundaries</h2><p>The website materializes the supplied v12 data. It does not independently re-audit all publications, inspect restricted text, execute source studies or perform a production pilot. Source summaries, titles, dates, mapping terminology and uncertainty are retained. Some earlier-book annotations remain in Italian. W records can contain lead-author-only metadata; use the original publication for complete bibliographic details.</p><p>The original 193-source preset, stream memberships, clustering logic and 297 selectable relationship types are unchanged. Catalogue links can open an explicit collection, group or record; opening the atlas without parameters restores the original starting view. Actual manuscript citations and wider editorial placements are distinct views.</p><h2>Rights and redistribution</h2><p>The inherited attribution record notes that the SE@PoliMi publication states CC BY-NC-ND 4.0 unless otherwise noted. Third-party works retain their own terms. This package grants no new rights to their full text, subscriber material, figures or datasets. It contains catalogue metadata, existing concise atlas paraphrases and editorial records—not full third-party articles or complete source-book manuscripts.</p><p>No blanket open-source licence has been assigned to all contents by this packaging operation. The author’s photograph is supplied for this project, not as a general stock image. Consult the applicable author or publisher for reuse beyond this package’s purpose.</p></div>'''
 page(path,'Credits, provenance and evidence boundaries',heading('Credits & provenance','Attribution is part of the model','Who created the starting bibliography, who wrote each source, and what this atlas does—and does not—establish.')+att,'Full credits to the original curators and source authors, with evidence and access boundaries.')
 (ROOT/'ATTRIBUTION.md').write_text('''# Attribution and provenance\n\nThe starting collection is **The SE & AI Annotated Bibliography**, curated by **Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara**, **Software Engineering @ PoliMi**: https://www.sepolimi.com/p/se-ai-annotated-bibliography. The retained snapshot contains 193 works across nine streams (8 October 2026; published 9 October).\n\nThe original collection, classification and annotations belong to the curators. The atlas, interface, concise independent summaries, added collections, editorial mappings and book genealogy are Enrico Papalini’s independent work with AI assistance. No institutional endorsement is implied.\n\nAddy Osmani and all credited contributors to The Pragmatic Engineer retain their individual authorship. The Fowler website collection credits each essay’s actual byline and Birgitta Böckeler’s editorial contribution to Exploring Generative AI: https://martinfowler.com/articles/exploring-gen-ai.html.\n\nThis site build reuses the frozen v12 records without a new research audit. Membership, conceptual similarity and proposed chapter mapping do not establish causality, efficacy or independent replication.\n\nThe inherited rights notice records SE@PoliMi’s stated CC BY-NC-ND 4.0 terms unless otherwise noted. No blanket licence for third-party content is granted. Full external manuscripts, subscriber article bodies and complete source-book texts are not bundled. See [the full notice](attribution.html).\n''',encoding='utf-8')
 # Downloads page, including all earlier catalogue assets, explicitly dated and separated.
 path='downloads.html';rows=''
 datasets=[(COLS[c]['slug'],COLS[c]['title']) for c in COLS]+[('all-sources','All 510 source records'),('practices','84 practice descriptors'),('occurrences','87 practice occurrences'),('practice-families','12 practice families'),('published-books','5 published book records')]
 for ds,title in datasets:rows+=f'<tr><td>{esc(title)}</td><td>'+link(path,f'data/catalogues/{ds}.json','JSON')+'</td><td>'+link(path,f'data/catalogues/{ds}.csv','CSV')+'</td></tr>'
 b=heading('Download the data','Static files · no API required','Current catalogues are generated from the same frozen v12 atlas data. JSON preserves complete node fields and graph attributes. CSV provides a compact tabular view; formula-like cells are escaped for safety.')+'<div class="table-wrap"><table><thead><tr><th>Catalogue</th><th>Complete records</th><th>Tabular export</th></tr></thead><tbody>'+rows+'</tbody></table></div><section class="section"><h2>The complete graph</h2><div class="actions">'+link(path,'data/graph/knowledge_graph_v12.graphml','GraphML','button')+link(path,'data/graph/knowledge_graph_v12.json','JSON','button')+link(path,'data/catalogue-data.zip','All current catalogue data (ZIP)','button primary')+'</div><p class="note">The graph exports are byte-identical to the supplied v12 release: 1,757 nodes, 12,188 keyed relationships and 297 relation types.</p></section><section class="section"><h2>Earlier catalogue files, preserved</h2><p class="note">These source assets retain their original version names and wording. They are historical/source catalogues, not a newer replacement for the current v12 view above. Relative links inside the original Markdown may describe the parent book archive; they are not website navigation.</p><ul class="compact-list">'
 for p in sorted((ROOT/'data/originals').iterdir()):
  if p.is_file():b+='<li>'+link(path,str(p.relative_to(ROOT)),esc(p.name))+f' <span class="micro">({p.stat().st_size/1024:.0f} KB)</span></li>'
 b+='</ul></section><section class="section"><h2>Project files</h2><ul class="compact-list">'+''.join('<li>'+link(path,t,l)+'</li>' for t,l in [('README.md','Project README'),('DEPLOYMENT.md','Deployment instructions'),('ATTRIBUTION.md','Attribution'),('source/build_site.py','Catalogue builder'),('source/site_config.json','Project and biography configuration'),('source/author_provenance.json','Photo and biography provenance'),('verification/report.html','Website validation report'),('SHA256SUMS.txt','Package integrity manifest')])+'</ul></section>'
 page(path,'Downloads',b,'All current static catalogue data, full graph exports, inherited catalogue files and reproducible build sources.',active='Downloads')
 # Short README, linked photo and relative internal links are GitHub + Pages safe.
 rows='\n'.join(f'| {c["code"]} | [{c["title"]}]({collection_file(c["code"])}) | {sum(n.get("collection")==c["code"] for n in SOURCES)} |' for c in C['collections'])
 readme=f'''# {C['title']}\n\nAn independent, source-traceable map of research and practitioner writing about AI-assisted software development, by **Enrico Papalini**. The interactive graph and static catalogues connect publications, topics, engineering practices and book chapters while keeping evidence limits visible.\n\n**[Open the published atlas]({C['canonical_atlas']})** · **[Local atlas](swe_knowledge_graph.html)** · **[Browse all catalogues](catalogues/index.html)** · **[Project homepage](index.html)** · **[Data downloads](downloads.html)**\n\nExisting public atlas address: **[{C['canonical_atlas']}]({C['canonical_atlas']})**. The relative links above work at the site root or within a GitHub project path.\n\n## Start with the original collection\n\nThe foundation is **[The SE & AI Annotated Bibliography](https://www.sepolimi.com/p/se-ai-annotated-bibliography)**, curated by **Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara**, **Software Engineering @ PoliMi**. Its 8 October 2026 snapshot contains **193 works across nine thematic streams**. The source collection, original classification and annotations are the curators’ work. The graph, interface, independent summaries and editorial extensions are separate authorial work, not an official Polimi publication or endorsed interpretation.\n\nThe atlas opens with **W001–W193 only: 193 sources, 0 context nodes, 64 visible relationships**. The other collections are available but initially disabled. Existing clustering and all 297 relationship switches are preserved.\n\n## Static catalogues\n\n| ID | Collection | Records |\n|---|---|---:|\n{rows}\n\nAlso browse **[nine streams](catalogues/streams.html)**, **[30 topics](catalogues/topics.html)**, **[five earlier volumes](catalogues/volumes.html)**, **[13 book chapters](catalogues/chapters.html)**, **[84 practice descriptors](catalogues/practices.html)** and **[87 historical occurrences](catalogues/occurrences.html)**. Each group has its own static page. All catalogue entries remain readable with JavaScript disabled; search is an optional enhancement. JSON and CSV exports are included.\n\nThe Fowler collection preserves individual bylines and acknowledges **Birgitta Böckeler** as contributor and editor of **[Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html)**. It is not a collection of 33 essays all authored by Martin Fowler. The Pragmatic Engineer catalogue likewise retains credited contributors.\n\n## About Enrico Papalini\n\n<img src="assets/enrico-papalini.jpg" alt="Enrico Papalini — author photograph" width="140">\n\n{C['bio']}\n\nPhoto and bio are adapted from his own *Non-Deterministic Loop Engineering* author page. [Photo provenance](source/author_provenance.json) · [About the project](about.html) · [GitHub](https://github.com/popoloni). This project expresses the author’s views, not those of his employers or cited institutions.\n\n## Publish on GitHub Pages\n\nCopy **the contents of this package** into your configured Pages publishing folder, keeping the directory structure and `.nojekyll`. The entry page is `index.html`; the atlas keeps `swe_knowledge_graph.html`. No Jekyll, framework, API key, CDN or server application is required. See [DEPLOYMENT.md](DEPLOYMENT.md) before replacing an existing homepage. A ready-made `knowledge-atlas.html` entrypoint is also included.\n\nGraph snapshot: **v12, 13 October 2026**. Website package: **v12.1, {C['build_date']}**. All 1,757 graph nodes and 12,188 keyed relationships are retained. Source IDs describe provenance, not evidence quality. The package does not claim exhaustive primary-source validation, restricted-text access, empirical replication or a production pilot. [Full credits and boundaries](attribution.html) · [Validation report](verification/report.html).\n'''
 (ROOT/'README.md').write_text(readme,encoding='utf-8')
 (ROOT/'DEPLOYMENT.md').write_text('''# Publish this static site\n\n## Existing GitHub Pages site\n\nBack up your current publishing folder first. Copy the extracted package contents into that folder, preserving all subfolders and the empty `.nojekyll` file. Do not upload only `index.html` or rename HTML files to `.txt`. No build command is required on GitHub.\n\nThe new `index.html` is a project landing page, not the atlas itself. `swe_knowledge_graph.html` remains the interactive atlas. If your current homepage is unrelated, keep it: publish this package in a subdirectory, or link to the supplied `knowledge-atlas.html` and do not replace your existing `index.html`. The latter file uses the same relative resource paths as the new landing page.\n\nFor the user-site root, `swe_knowledge_graph.html` serves at `https://popoloni.github.io/swe_knowledge_graph.html`. For a project site such as `articles`, the same file normally serves at `https://popoloni.github.io/articles/swe_knowledge_graph.html`. Local catalogue and image paths are relative, so no repository-name edit is required.\n\n## Branch publishing\n\nIn repository **Settings → Pages → Build and deployment**, keep or select **Deploy from a branch**, choose the publishing branch, and select its **/(root)** or **/docs** folder. Save and wait for the Pages deployment to succeed. The package’s `index.html` must be directly inside that selected folder, not hidden one level deeper under the ZIP’s name.\n\nGitHub documentation: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site\n\nStatic sites and `.nojekyll`: https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site\n\n## Local check\n\nOpen `index.html` locally. The static catalogues work without JavaScript; optional filters and atlas interactions use only bundled JavaScript. For a web-like preview, from this folder run:\n\n```sh\npython -m http.server 8000\n```\n\nThen visit `http://localhost:8000/`. An external article still requires internet access and may require a subscription. This package does not bypass that access.\n\n## Updating the site\n\nEdit `source/site_config.json` for the brief introduction/bio and replace `assets/enrico-papalini.jpg` only with an approved portrait. Run `python source/build_site.py`, then `python source/check_site.py`. The builder reads the frozen v12 atlas snapshot, not a live source feed. Do not substitute the old v6 attachment. Research refreshes require a separate, explicitly audited graph update.\n\nDeployments are not executed by this deliverable. Browser tests in the verification report are local tests, not evidence of a successful deployment to your account.\n''',encoding='utf-8')
 # Rebuild the catalogue download deterministically from local exported records and inherited catalogues.
 with zipfile.ZipFile(ROOT/'data/catalogue-data.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for item in sorted(list((ROOT/'data/catalogues').glob('*'))+list((ROOT/'data/originals').glob('*'))):
   if not item.is_file():continue
   info=zipfile.ZipInfo(item.relative_to(ROOT/'data').as_posix(),date_time=(2026,10,14,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
   z.writestr(info,item.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 (ROOT/'source/page_inventory.json').write_text(json.dumps(sorted(PAGES+['swe_knowledge_graph.html']),indent=2)+'\n')
 (ROOT/'source/build_summary.json').write_text(json.dumps({'site_version':C['site_version'],'graph_snapshot':C['graph_snapshot'],'graph_nodes':len(D['nodes']),'graph_edges':len(D['edges']),'graph_relation_types':len(D['relations']),'source_counts':{c:sum(n.get('collection')==c for n in SOURCES) for c in COLS},'static_source_records':len(SOURCES),'practice_descriptors':len(PRACTICES),'practice_occurrences':len(OCCURRENCES),'group_pages':{'streams':len(D['themes']),'topics':len(D['topics']),'chapters':len(D['chapters']),'volumes':5},'html_pages_built':len(PAGES)+1,'graph_payload_unchanged':True,'new_empirical_verification':False},indent=2)+'\n')
 print(f'Built {len(PAGES)+1} HTML pages, {len(SOURCES)} source records; frozen v12 graph unchanged.')
if __name__=='__main__':build()
