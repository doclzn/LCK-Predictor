from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
js=(ROOT/"static"/"v25.js").read_text(encoding="utf-8")
css=(ROOT/"static"/"v25.css").read_text(encoding="utf-8")
assert 'b.hidden=true' in js
assert 'b.style.display="none"' in js
assert 'ev.key==="Escape"' in js
assert '.coach-modal-backdrop[hidden]' in css
assert 'display:none !important' in css
assert '#coachBackdropV23:not([hidden])' in css
print("V25.1 modal close regression: OK")
