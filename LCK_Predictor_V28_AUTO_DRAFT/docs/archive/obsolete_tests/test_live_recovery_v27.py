from pathlib import Path
import importlib.util
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v27",ROOT/"server.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
br=timezone(timedelta(hours=-3))
now=datetime(2026,8,21,7,22,tzinfo=br)
rows=m._schedule_rows_for_day_v27("2026-08-21")
states={(r["team_a"],r["team_b"]):m._schedule_row_state_v27(r,now) for r in rows}
assert states[("KT","T1")]=="live_candidate",states
assert states[("BRO","BFX")]!="live_candidate",states
fb=m._fallback_live_candidate_v27(now)
assert fb and {fb["team1"],fb["team2"]}=={"KT","T1"},fb
assert fb["status"]=="live"
assert fb["live_confidence"]=="schedule_fallback"
assert fb["date"].startswith("2026-08-21T07:00:00"),fb["date"]
print("V27 live recovery regression: OK")
print(states)
print(fb["team1"],"vs",fb["team2"],fb["date"])
