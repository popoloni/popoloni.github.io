#!/usr/bin/env python3
"""Rebuild generated site outputs and compare their exact bytes. Python standard library."""
import hashlib, json, subprocess, sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent
paths=json.loads((R/'source/page_inventory.json').read_text())
paths += [p.relative_to(R).as_posix() for p in sorted((R/'data/catalogues').glob('*')) if p.is_file()]
paths += ['README.md','DEPLOYMENT.md','ATTRIBUTION.md','source/page_inventory.json','source/build_summary.json','data/catalogue-data.zip']
sha=lambda p:hashlib.sha256((R/p).read_bytes()).hexdigest()
before={p:sha(p) for p in paths}
subprocess.run([sys.executable,str(R/'source/build_site.py')],check=True,cwd=R)
checks=[{'path':p,'before':before[p],'after':sha(p),'passed':before[p]==sha(p)} for p in paths]
result={'outputs_tested':len(checks),'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'method':'Frozen input; two sequential builds compared by SHA-256; no network or source refresh','checks':checks}
(R/'verification/reproducibility.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2));assert result['failed']==0
