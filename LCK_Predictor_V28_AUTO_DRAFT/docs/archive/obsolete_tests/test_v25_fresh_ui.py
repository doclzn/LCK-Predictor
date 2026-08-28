from pathlib import Path
import importlib.util,re
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v25',ROOT/'server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.PORT==8825
assert m.APP_VERSION=='V25_FRESH_UI'
h=m.v12_home()
assert not any({x['team1'],x['team2']}=={'HLE','DK'} for x in h['live'])
assert not any(str(x['date'])[:10]<'2026-08-21' for x in h['upcoming'])
assert any({x['team1'],x['team2']}=={'KT','T1'} for x in h['upcoming'])
assert any({x['team1'],x['team2']}=={'HLE','DK'} for x in h['recent'])
idx=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
css=(ROOT/'static'/'v25.css').read_text(encoding='utf-8')
js=(ROOT/'static'/'v25.js').read_text(encoding='utf-8')
assert 'V25 • NOVA INTERFACE' in idx
assert '/static/v25.css?build=V25_FRESH_UI' in idx
assert 'html[data-ui-scale="xxlarge"]{font-size:26px!important}' in css
assert 'small{font-size:16px!important}' in css
assert 'EXPECTED_APP_VERSION="V25_FRESH_UI"' in js
print('V25 fresh UI regression: OK')
print('upcoming',[(x['date'],x['team1'],x['team2']) for x in h['upcoming']])
print('recent',[(x['date'],x['team1'],x.get('wins1'),x.get('wins2'),x['team2']) for x in h['recent'][:3]])
