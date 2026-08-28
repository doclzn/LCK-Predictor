from pathlib import Path
import subprocess,sys,json,sqlite3,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
tests=[
 'test_riot_v10.py','test_strategy_v14.py','test_draft_tree_v15.py','test_flex_tree_v16.py',
 'test_joint_v17.py','test_series_v18.py','test_validation_v19.py','test_live_validation_v20.py',
 'test_governance_v21.py','test_live_protocol_v21.py','test_core_invariants_v24.py'
]
results=[]
for name in tests:
    p=subprocess.run([sys.executable,str(ROOT/'tests'/name)],cwd=str(ROOT),capture_output=True,text=True,timeout=180)
    results.append({'test':name,'ok':p.returncode==0,'stdout':p.stdout[-1200:],'stderr':p.stderr[-1200:]})
    if p.returncode:
        print(json.dumps({'ok':False,'failed':name,'results':results},ensure_ascii=False,indent=2));raise SystemExit(1)
css=(ROOT/'static'/'v24.css').read_text(encoding='utf-8')
px=[float(x) for x in re.findall(r'font-size\s*:\s*([0-9.]+)px',css)]
rem=[float(x) for x in re.findall(r'font-size\s*:\s*([0-9]*\.?[0-9]+)rem',css)]
report={'ok':True,'tests':results,'typography':{'min_px':min(px),'min_rem':min(rem)},'version':'V24 QA Review'}
(ROOT/'QA_REPORT_V24.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ok':True,'tests_passed':len(results),'min_px':min(px),'min_rem':min(rem)},ensure_ascii=False,indent=2))
