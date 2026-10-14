#!/usr/bin/env python3
"""Supplemental responsive/portrait checks using the packaged assets, with no network."""
import base64, json, mimetypes, re, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent.parent
checks=[]
def embedded(path):
 f=R/path;s=f.read_text()
 s=re.sub(r'<link rel="stylesheet" href="([^"]+)">',lambda m:'<style>'+(f.parent/m[1]).read_text()+'</style>',s)
 s=re.sub(r'<script src="([^"]+)" defer></script>',lambda m:'<script>document.addEventListener("DOMContentLoaded",()=>{'+(f.parent/m[1]).read_text()+'});</script>',s)
 s=re.sub(r'src="([^"]+\.(?:jpg|png|webp))"',lambda m:'src="data:'+mimetypes.guess_type(m[1])[0]+';base64,'+base64.b64encode((f.parent/m[1]).read_bytes()).decode()+'"',s)
 return s
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
 for name,width,height in [('desktop',1440,1000),('tablet',1024,768),('mobile',390,844)]:
  page=b.new_page(viewport={'width':width,'height':height});page.set_content(embedded('index.html'),wait_until='load')
  photo=page.locator('.profile img');photo.scroll_into_view_if_needed();page.wait_for_function('document.querySelector(".profile img").complete && document.querySelector(".profile img").naturalWidth>0')
  photo.screenshot(path=str(R/f'verification/portrait_{name}.png'))
  checks.append({'check':f'{name} portrait loads on scroll','passed':photo.evaluate('(im)=>im.complete&&im.naturalWidth===631&&im.naturalHeight===640'),'viewport':width})
  page.evaluate('scrollTo(0,0)');page.screenshot(path=str(R/f'verification/home_{name}.png'),full_page=True)
  checks.append({'check':f'{name} homepage no horizontal overflow','passed':page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')})
  page.close()
 page=b.new_page(viewport={'width':390,'height':844});page.set_content(embedded('catalogues/fowler.html'),wait_until='load');page.locator('input[name=q]').fill('F023');page.locator('[data-record]:visible').first.scroll_into_view_if_needed();page.screenshot(path=str(R/'verification/catalogue_mobile.png'),full_page=False)
 checks.append({'check':'Mobile catalogue search displays F023','passed':page.locator('#F023').is_visible()});page.close();b.close()
res={'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'checks':checks,'method':'Chromium set_content, local assets inlined, responsive viewport simulation; no native Safari or hosted-navigation test'}
(R/'verification/visual_checks.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2));assert not res['failed']
