#!/usr/bin/env python3
"""Offline structural checks. Python stdlib only; external URLs are inventoried, not fetched."""
import collections, hashlib, html.parser, json, re, sys, zipfile
from pathlib import Path
from urllib.parse import urlsplit,unquote
R=Path(__file__).resolve().parent.parent
class Parser(html.parser.HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.ids=[];self.links=[];self.records=[];self.images=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if a.get('id'):self.ids.append(a['id'])
  if 'data-record' in a:self.records.append(a.get('id'))
  if tag in ['a','link'] and a.get('href'):self.links.append((tag,a['href']))
  if tag in ['img','script'] and a.get('src'):self.links.append((tag,a['src']))
  if tag=='img':self.images.append(a)
 def handle_data(self,data):self.text.append(data)
checks=[]
def check(name,ok,detail=''):
 checks.append({'check':name,'passed':bool(ok),'detail':detail})
 return ok
pages=json.loads((R/'source/page_inventory.json').read_text())+['UPDATE_20261018.html','verification/report.html']
parsed={}
for name in pages:
 if not (R/name).exists():check('HTML exists: '+name,False);continue
 p=Parser();p.feed((R/name).read_text());parsed[name]=p
 check('Unique anchors: '+name,len(p.ids)==len(set(p.ids)))
 check('Image alt text: '+name,all(a.get('alt') for a in p.images))
errors=[];external=set();internal_count=0
for name,p in parsed.items():
 for tag,link in p.links:
  u=urlsplit(link)
  if u.scheme in ('http','https') or u.netloc:external.add(link);continue
  if u.scheme in ('mailto','data','javascript'):continue
  path=unquote(u.path)
  dest=((R/name).parent/path).resolve() if path else (R/name).resolve()
  if dest.is_dir():dest/='index.html'
  if not dest.is_relative_to(R.resolve()):errors.append([name,link,'escapes root']);continue
  if not dest.is_file():errors.append([name,link,'missing file']);continue
  internal_count+=1
  if u.fragment and dest.suffix=='.html':
   rel=str(dest.relative_to(R));q=parsed.get(rel)
   if q is None:q=Parser();q.feed(dest.read_text());parsed.setdefault(rel,q)
   if unquote(u.fragment) not in q.ids:errors.append([name,link,'missing fragment'])
check('All local file links and fragment anchors resolve',not errors,{'checked_links':internal_count,'errors':errors})
original=(R/'source/atlas_v12_original.html').read_text();current=(R/'swe_knowledge_graph.html').read_text()
extract=lambda h:json.loads(re.search(r'<script id="graph-data" type="application/json">(.*?)</script>',h,re.S)[1])
d=extract(original);now=extract(current)
check('All original node IDs retain their positions',[n['id'] for n in now['nodes'][:len(d['nodes'])]]==[n['id'] for n in d['nodes']])
check('All 12,188 original keyed relationships remain identical',len(d['edges'])==12188 and now['edges'][:len(d['edges'])]==d['edges'])
check('Current payload export equals embedded graph',now==json.loads((R/'data/graph/atlas_payload_v13.json').read_text()))
check('Current template embeds the delivered payload',now==extract((R/'source/atlas_v13_current.html').read_text()))
original_files=json.loads((R/'source/baseline_provenance.json').read_text())['preserved_files']
check('Frozen original HTML and GraphML/JSON bytes retained',all(hashlib.sha256((R/p).read_bytes()).hexdigest()==m['sha256'] for p,m in original_files.items()))
original_catalogues=json.loads((R/'source/original_catalogue_provenance.json').read_text())
check('All 17 inherited catalogue files retain source bytes',len(original_catalogues)==17 and all(hashlib.sha256((R/m['file']).read_bytes()).hexdigest()==m['sha256'] for m in original_catalogues))
md_errors=[];md_count=0
for doc in ['README.md','DEPLOYMENT.md','ATTRIBUTION.md']:
 for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',(R/doc).read_text()):
  u=urlsplit(target)
  if u.scheme or u.netloc:continue
  path=(R/unquote(u.path)).resolve();md_count+=1
  if not path.is_file():md_errors.append([doc,target])
check('README and top-level Markdown local links resolve',not md_errors,{'checked':md_count,'errors':md_errors})

for c,n in [('W',193),('O',51),('P',124),('F',35),('B',111),('N',13)]:
 slug={'W':'polimi','O':'osmani','P':'pragmatic-engineer','F':'fowler','B':'books','N':'ndse2'}[c]
 ids=[x['id'] for x in now['nodes'] if x.get('collection')==c]
 check('Static '+c+' record IDs complete',parsed['catalogues/'+slug+'.html'].records==ids and len(ids)==n)
 export=json.loads((R/'data/catalogues'/f'{slug}.json').read_text())['records']
 check('JSON '+c+' complete attributes preserved',export==[x for x in now['nodes'] if x.get('collection')==c])
for slug,kind in [('practices','practice_descriptor'),('occurrences','practice_occurrence')]:
 check('Static '+slug+' IDs complete',parsed['catalogues/'+slug+'.html'].records==[x['id'] for x in now['nodes'] if x['kind']==kind])
check('No external runtime dependencies in new pages',not any(urlsplit(l).scheme in ('http','https') for name,p in parsed.items() for tag,l in p.links if tag in ['script','img','link']))
check('Original Polimi-only defaultState unchanged',re.search(r'const defaultState=.*?;',original)[0]==re.search(r'const defaultState=.*?;',current)[0])
check('All original core app functions retained',all(x in current for x in ['function assignedGroup(n)','function filterRelationList()','function restoreView(data)','function fullExport()']))
check('README includes bio and local portrait',all(x in (R/'README.md').read_text() for x in ['assets/enrico-papalini.jpg','Enrico Papalini','Alfonso Fuggetta','Damian Andrew Tamburri','Alessandro Margara']))
check('No fonts, third-party full-text PDFs or book manuscripts',not any(p.suffix.lower() in ('.ttf','.otf','.woff','.woff2','.pdf','.tex') for p in R.rglob('*') if p.is_file()))
check('.nojekyll present',(R/'.nojekyll').is_file())
# No file can exceed GitHub's ordinary browser-upload threshold; bundle upload is not a deployment.
check('Each site file under 25 MiB',all(p.stat().st_size<25*1024*1024 for p in R.rglob('*') if p.is_file()))
from check_graph_update import validate
validate(R,now,check)
baseline=json.loads((R/'source/update_baseline_20261018.json').read_text())
check('Copy-only update retains all 157 baseline file paths',len(baseline['files'])==157 and all((R/p).is_file() for p in baseline['files']))
res={'as_of':'2026-10-18','site_version':'13.0','graph_snapshot':now['meta']['date'],'graph_nodes':len(now['nodes']),'graph_edges':len(now['edges']),'graph_html_sha256':hashlib.sha256((R/'swe_knowledge_graph.html').read_bytes()).hexdigest(),'baseline_zip_sha256':baseline['baseline_sha256'],'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'checks':checks,'internal_links_checked':internal_count,'distinct_external_links':len(external),'external_urls_live_checked':False,'html_pages_checked':len(pages)}
(R/'verification/structure_checks.json').write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in res.items() if k!='checks'},indent=2))
if res['failed']:
 print(json.dumps([x for x in checks if not x['passed']],indent=2,ensure_ascii=False));sys.exit(1)
