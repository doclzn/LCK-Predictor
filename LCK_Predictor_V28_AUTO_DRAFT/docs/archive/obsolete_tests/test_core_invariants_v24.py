from pathlib import Path
import importlib.util, re, json
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v24',ROOT/'server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

# --- canonical state machine ---
TZ=m.BRAZIL_TZ
now=datetime(2026,8,20,23,15,tzinfo=TZ)
assert m.v24_match_state('2026-08-21T10:00:00-03:00','unstarted',now=now)=='upcoming'
assert m.v24_match_state('2026-08-20T07:00:00-03:00','unstarted',now=now)=='pending'
assert m.v24_match_state('2026-08-20T07:00:00-03:00','inProgress',now=now)=='pending'
assert m.v24_match_state('2026-08-20T22:30:00-03:00','inProgress',now=now)=='live'
assert m.v24_match_state('2026-08-20T07:00:00-03:00','completed',0,2,now=now)=='completed'
assert m.v24_match_state(None,None,legacy_date='2026-08-19',now=now)=='pending'
assert m.v24_match_state(None,None,legacy_date='2026-08-21',now=now)=='upcoming'

# --- current data invariants ---
home=m.v12_home()
assert home['schedule_status']['timezone']=='UTC-03:00'
assert not any(str(x.get('date') or '')[:10]<'2026-08-21' for x in home['upcoming']), home['upcoming']
assert not any({x['team1'],x['team2']}=={'HLE','DK'} for x in home['live']), home['live']
assert any({x['team1'],x['team2']}=={'KT','T1'} for x in home['upcoming'])

completed=m.v12_match_items('completed',20)
# The two Aug-20 finals verified during this QA review must be present above Aug-19.
keys=[(str(x.get('date') or '')[:10],frozenset((x['team1'],x['team2'])),x.get('winner')) for x in completed]
assert ('2026-08-20',frozenset(('DK','HLE')),'HLE') in keys
assert ('2026-08-20',frozenset(('KRX','NS')),'NS') in keys
if completed:
    dates=[str(x.get('date') or '')[:10] for x in completed]
    assert dates==sorted(dates,reverse=True), dates

# No duplicate same-day pair in upcoming.
seen=set()
for x in m.v12_match_items('upcoming',100):
    key=(str(x.get('date') or '')[:10],frozenset((x['team1'],x['team2'])))
    assert key not in seen,key
    seen.add(key)

# --- scientific lock remains valid after UI/release evolution ---
integ=m.v21_integrity_report()
assert integ['ok'], integ
verified=m.v21_verified_v19_freezes()
assert len(verified)==5, len(verified)

# --- frontend version/cache and date-only timezone fix ---
index=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
js=(ROOT/'static'/'v24.js').read_text(encoding='utf-8')
css=(ROOT/'static'/'v24.css').read_text(encoding='utf-8')
sw=(ROOT/'static'/'sw.js').read_text(encoding='utf-8')
assert '/static/v24.css' in index and '/static/v24.js' in index
assert 'lck-predictor-v24-qa-review' in sw
assert r'/^\\d{4}-\\d{2}-\\d{2}$/' in js or r'/^\d{4}-\d{2}-\d{2}$/' in js
assert 'UI_SCALES_V24' in js and 'data-ui-scale="large"' in index

# --- legibility floor: no explicit microscopic typography survives ---
px=[float(x) for x in re.findall(r'font-size\s*:\s*([0-9.]+)px',css)]
rem=[float(x) for x in re.findall(r'font-size\s*:\s*([0-9]*\.?[0-9]+)rem',css)]
assert px and min(px)>=14, min(px)
assert rem and min(rem)>=.78, min(rem)
# Ensure the primary selectors are materially large, not merely floor-compliant.
for token in ['.page-head h1{font-size:2.05rem}', '.hero-copy h1{font-size:2.2rem}', '.match-teams b{font-size:1.04rem}', '.match-time b{font-size:.98rem}']:
    assert token in css, token

print('V24 core invariants: OK')
print('upcoming',[(str(x['date'])[:10],x['team1'],x['team2']) for x in home['upcoming'][:6]])
print('latest results',[(str(x['date'])[:10],x['team1'],x.get('wins1'),x.get('wins2'),x['team2']) for x in completed[:4]])
print('min typography',min(px),'px /',min(rem),'rem')
