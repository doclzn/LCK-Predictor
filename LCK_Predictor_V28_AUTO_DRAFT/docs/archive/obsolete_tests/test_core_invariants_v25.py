from pathlib import Path
import importlib.util, re, json
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v25',ROOT/'server.py')
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
js=(ROOT/'static'/'v25.js').read_text(encoding='utf-8')
css=(ROOT/'static'/'v25.css').read_text(encoding='utf-8')
sw=(ROOT/'static'/'sw.js').read_text(encoding='utf-8')
assert '/static/v25.css?build=V25_FRESH_UI' in index and '/static/v25.js?build=V25_FRESH_UI' in index
assert 'fetch(e.request)' in sw
assert r'/^\\d{4}-\\d{2}-\\d{2}$/' in js or r'/^\d{4}-\d{2}-\d{2}$/' in js
assert 'UI_SCALES_V24' in js and 'data-ui-scale="xxlarge"' in index and 'EXPECTED_APP_VERSION="V25_FRESH_UI"' in js

# --- V25 readability is intentionally obvious, not a subtle floor ---
for token in [
    'html[data-ui-scale=\"xxlarge\"]{font-size:26px!important}',
    '.page-head h1{font-size:38px!important',
    '.hero-copy h1{font-size:39px!important',
    '.match-teams b{font-size:21px!important',
    '.match-time b{font-size:19px!important',
    'small{font-size:16px!important}'
]:
    assert token in css, token
assert m.PORT==8825
assert m.APP_VERSION=='V25_FRESH_UI'

print('V25 core invariants: OK')
print('upcoming',[(str(x['date'])[:10],x['team1'],x['team2']) for x in home['upcoming'][:6]])
print('latest results',[(str(x['date'])[:10],x['team1'],x.get('wins1'),x.get('wins2'),x['team2']) for x in completed[:4]])
