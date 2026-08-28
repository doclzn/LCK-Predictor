from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
js=(ROOT/"static"/"v26.js").read_text(encoding="utf-8")
html=(ROOT/"static"/"index.html").read_text(encoding="utf-8")
server=(ROOT/"server.py").read_text(encoding="utf-8")
for token in ["coachModalHtmlV23","openGuideV23","closeGuideV23","coachBackdropV23","coach-fab","Ver passo a passo","ensureCoachV23"]:
    assert token not in js, token
assert "PORT = 8826" in server
assert 'APP_VERSION = "V26_CLEAN_UI"' in server
assert "/static/v26.js?build=V26_CLEAN_UI" in html
assert "/static/v26.css?build=V26_CLEAN_UI" in html
assert "V26 • PORTA 8826 • SEM GUIA" in html
assert not (ROOT/"static"/"v25.js").exists()
assert not (ROOT/"static"/"v25.css").exists()
print("V26 clean UI package test: OK")
