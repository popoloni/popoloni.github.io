#!/usr/bin/env python3
"""Local browser checks; requires playwright + Chromium. No deployment or source re-audit."""
from pathlib import Path
import base64, collections, functools, hashlib, http.server, json, mimetypes, re, threading, time
from urllib.parse import urlsplit, unquote
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent.parent
checks=[];errors=[];requests=[];external=[]
def check(name,ok,detail=None):
 checks.append({'check':name,'passed':bool(ok),'detail':detail})
 (R/'verification/browser_checks_in_progress.json').write_text(json.dumps(checks,indent=2))
 print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 if not ok:raise AssertionError(name+': '+str(detail))
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=R))
threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}/'
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=__import__('shutil').which('chromium') or None,headless=True,args=['--no-sandbox'])
 viewport={'width':1440,'height':1000}
 ctx=browser.new_context(viewport=viewport,accept_downloads=True)
 pg=ctx.new_page();pg.on('pageerror',lambda e:errors.append(str(e)))
 pg.on('request',lambda r:requests.append(r.url))
 def embedded(path):
  u=urlsplit(path);file=R/unquote(u.path);text=file.read_text(encoding='utf-8')
  def css(m):return '<style>'+ (file.parent/m.group(1)).read_text()+'</style>'
  def js(m):return '<script>document.addEventListener("DOMContentLoaded",()=>{'+ (file.parent/m.group(1)).read_text()+'});</script>'
  def img(m):
   f=(file.parent/m.group(1)).resolve();mime=mimetypes.guess_type(str(f))[0] or 'application/octet-stream';return 'src="data:'+mime+';base64,'+base64.b64encode(f.read_bytes()).decode()+'"'
  text=re.sub(r'<link rel="stylesheet" href="([^"]+)">',css,text)
  text=re.sub(r'<script src="([^"]+)" defer></script>',js,text)
  text=re.sub(r'src="([^"]+\.(?:jpg|png|webp))"',img,text)
  return text,u
 def load(path):
  global pg
  pg.close();pg=ctx.new_page();pg.set_viewport_size(viewport);pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('request',lambda r:requests.append(r.url))
  text,u=embedded(path);pg.set_content(text,wait_until='load');check('Embedded page '+path,pg.locator('html').count()==1)
  if u.query and u.path=='swe_knowledge_graph.html':pg.wait_for_function('!!window.atlasOpenCatalogueView');pg.evaluate('(s)=>atlasOpenCatalogueView(s)','?'+u.query)
  if u.fragment:pg.evaluate('(s)=>{location.hash=s;}','#'+u.fragment);pg.wait_for_timeout(60)
 def overflow():return pg.evaluate('document.documentElement.scrollWidth > innerWidth+2')
 load('index.html');check('Landing page title','Knowledge Atlas for AI and Software Engineering' in pg.title());check('Landing has 5 source catalogue links',pg.locator('.collection-card .card-link').count()==6);check('Landing image loaded',pg.locator('.hero-visual img').evaluate('(im)=>im.complete&&im.naturalWidth>0'));check('Desktop no horizontal overflow',not overflow());pg.screenshot(path=str(R/'verification/home_desktop.png'),full_page=True)
 for slug,num in [('polimi',193),('osmani',50),('pragmatic-engineer',123),('fowler',33),('books',111),('practices',84),('occurrences',87)]:
  load('catalogues/'+slug+'.html');check(slug+' static record count',pg.locator('[data-record]').count()==num)
  ident=pg.locator('[data-record]').first.get_attribute('id');pg.locator('input[name=q]').fill(ident);check(slug+' search filters entries',1<=pg.locator('[data-record]:visible').count()<num)
  pg.locator('input[name=q]').fill('no-source-can-match-this-token-7e962');check(slug+' empty state',pg.locator('#emptyState').is_visible() and pg.locator('[data-record]:visible').count()==0)
  pg.locator('[data-clear]').click();check(slug+' reset restores all',pg.locator('[data-record]:visible').count()==num)
 load('catalogues/polimi.html#W023');check('Anchor reveals details',pg.locator('#W023 > details').get_attribute('open') is not None);pg.screenshot(path=str(R/'verification/polimi_record.png'),full_page=False)
 load('about.html');check('Author photo loaded',pg.locator('.profile img').evaluate('(im)=>im.complete&&im.naturalWidth>0'));pg.screenshot(path=str(R/'verification/about_desktop.png'),full_page=True)
 # JavaScript-free source catalogues remain complete.
 nojs=browser.new_context(java_script_enabled=False,viewport={'width':1200,'height':850});nj=nojs.new_page()
 for slug,num in [('polimi',193),('osmani',50),('pragmatic-engineer',123),('fowler',33),('books',111)]:
  nj.set_content(embedded('catalogues/'+slug+'.html')[0],wait_until='load');check(slug+' readable without JavaScript',nj.locator('[data-record]').count()==num and nj.locator('[data-record] h2').first.inner_text()!='')
 nojs.close()
 # Atlas default, deep links and bidirectional navigation.
 load('swe_knowledge_graph.html');pg.wait_for_function('!!window.atlasDiagnostics');pg.wait_for_function('!atlasDiagnostics().layoutRunning',timeout=30000)
 diag=pg.evaluate('atlasDiagnostics()');check('Original 193 / 0 / 64 default',diag['visibleSources']==193 and diag['visibleContext']==0 and len(diag['visibleEdgeIDs'])==64,diag['sourceCounts']);check('All 297 relationship switches present',pg.locator('[data-relation]').count()==297)
 data=pg.evaluate('JSON.parse(document.getElementById("graph-data").textContent)')
 wids={f'W{i:03}' for i in range(1,194)};expected=[e['id'] for e in data['edges'] if data['nodes'][e['source']]['id'] in wids and data['nodes'][e['target']]['id'] in wids and e['relation']!='inferred_topic_similarity']
 check('Default uses exact expected edge IDs',set(diag['visibleEdgeIDs'])==set(expected))
 pg.screenshot(path=str(R/'verification/atlas_desktop.png'),full_page=True)
 load('swe_knowledge_graph.html?collection=F&node=F023');pg.wait_for_function('!!window.atlasDiagnostics');diag=pg.evaluate('atlasDiagnostics()');check('Fowler deep link selects F023',diag['selected']=='F023' and diag['sourceCounts']['F']==33 and diag['sourceCounts']['W']==0);check('Source inspector links back to static catalogue',pg.locator('#inspectorBody a[href="catalogues/fowler.html#F023"]').count()==1)
 load('swe_knowledge_graph.html?collection=B&grouping=volume&group=V03');pg.wait_for_function('!!window.atlasDiagnostics');diag=pg.evaluate('atlasDiagnostics()');check('Volume deep link selects 36 B records',diag['visibleSources']==36 and diag['grouping']=='volume')
 load('swe_knowledge_graph.html?node=PAT%3A001');pg.wait_for_function('!!window.atlasDiagnostics');check('Context record deep link',pg.evaluate('atlasDiagnostics().selected')=='PAT:001')
 load('swe_knowledge_graph.html?collection=invalid&node=NOT_A_NODE');pg.wait_for_function('!!window.atlasDiagnostics');check('Invalid deep link leaves default intact',pg.evaluate('atlasDiagnostics().visibleSources')==193)
 # Every existing relationship switch: explicit F/W/O/P/B + context, using real UI events.
 load('swe_knowledge_graph.html');pg.wait_for_function('!!window.atlasDiagnostics')
 pg.locator('#fullGraph').evaluate('(el)=>el.click()');pg.wait_for_function('!atlasDiagnostics().layoutRunning',timeout=30000)
 test_results=pg.evaluate('''() => {const D=JSON.parse(document.getElementById('graph-data').textContent);document.getElementById('noEdges').click();const results=[];for(const input of document.querySelectorAll('[data-relation]')){input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));const actual=atlasDiagnostics().visibleEdgeIDs.slice().sort();const expected=D.edges.filter(e=>e.relation===input.dataset.relation).map(e=>e.id).sort();results.push({relation:input.dataset.relation,passed:JSON.stringify(actual)===JSON.stringify(expected),edges:actual.length});input.checked=false;input.dispatchEvent(new Event('change',{bubbles:true}));}document.getElementById('resetBtn').click();return results;}''')
 (R/'verification/relationship_switch_checks.json').write_text(json.dumps(test_results,indent=2));check('All 297 relation switches have exact keyed edges',len(test_results)==297 and all(x['passed'] for x in test_results))
 pg.wait_for_function('!atlasDiagnostics().layoutRunning',timeout=30000);check('Reset after edge tests restores 193 / 64',pg.evaluate('atlasDiagnostics().visibleSources')==193 and pg.evaluate('atlasDiagnostics().visibleEdgeIDs.length')==64)
 # Mobile static pages and atlas.
 viewport={'width':390,'height':844}
 pg.set_viewport_size(viewport)
 check('Actual mobile viewport width is 390px',pg.evaluate('innerWidth')==390)
 for path in ['index.html','catalogues/index.html','catalogues/polimi.html','catalogues/books.html','about.html','downloads.html']:
  load(path);check('Mobile viewport '+path,pg.evaluate('innerWidth')==390);check('Mobile no overflow '+path,not overflow())
  if path=='index.html':pg.screenshot(path=str(R/'verification/home_mobile.png'),full_page=True)
 load('swe_knowledge_graph.html');pg.wait_for_function('!atlasDiagnostics().layoutRunning',timeout=30000);check('Mobile atlas still Polimi-only',pg.evaluate('atlasDiagnostics().sourceCounts.W')==193 and pg.evaluate('atlasDiagnostics().sourceCounts.F')==0);pg.screenshot(path=str(R/'verification/atlas_mobile.png'),full_page=True)
 check('No unhandled JavaScript errors',not errors,errors)
 external=[u for u in requests if u.startswith(('http://','https://')) and not u.startswith(base)]
 check('No external network requests during site navigation',not external,external)
 browser.close()
server.shutdown()
res={'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'browser':'Playwright Chromium; packaged CSS, JavaScript and images inlined for local set_content rendering because administrator policy blocks HTTP navigation','navigation_test_boundary':'Static path/fragment validation plus the same catalogue URL handler called with explicit parameters; real hosted navigation not exercised','native_safari_tested':False,'github_deployed':False,'checks':checks,'page_errors':errors,'external_network_requests':external}
(R/'verification/browser_checks.json').write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n');print('BROWSER TOTAL',res['passed'],res['failed'])
