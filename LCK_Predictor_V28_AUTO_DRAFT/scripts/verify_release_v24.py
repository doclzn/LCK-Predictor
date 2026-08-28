from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'RELEASE_MANIFEST_V24.json').read_text(encoding='utf-8'))
bad=[]
for rel,expected in m['files'].items():
 p=ROOT/rel
 actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
 if actual!=expected:bad.append({'path':rel,'expected':expected,'actual':actual})
print('V24 release integrity:', 'OK' if not bad else 'FAILED')
if bad:
 print(json.dumps(bad,ensure_ascii=False,indent=2));sys.exit(1)
