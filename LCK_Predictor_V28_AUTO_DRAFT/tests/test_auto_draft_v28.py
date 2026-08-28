from pathlib import Path
import importlib.util,tempfile,shutil
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v28",ROOT/"server.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
tmp=Path(tempfile.mkdtemp())/"x.sqlite";shutil.copy2(ROOT/"data"/"lck_data_v1.sqlite",tmp);m.DB=tmp;m.v28_ensure_schema()
fake={"event_id":"E","game_id":"G","game_number":1,"game_state":"inProgress","event_state":"inProgress","patch":"16.16.1","locked_count":10,"complete":True,"source":"fixture",
"blue":{"team":"T1","picks":[{"champion":"Gnar","role":"TOP"},{"champion":"Vi","role":"JUNGLE"},{"champion":"Azir","role":"MIDDLE"},{"champion":"Jinx","role":"BOTTOM"},{"champion":"Nautilus","role":"SUPPORT"}]},
"red":{"team":"KT Rolster","picks":[{"champion":"Renekton","role":"TOP"},{"champion":"Sejuani","role":"JUNGLE"},{"champion":"Taliyah","role":"MIDDLE"},{"champion":"Aphelios","role":"BOTTOM"},{"champion":"Rakan","role":"SUPPORT"}]}}
m.riot_fetch_draft_probe=lambda eid:fake
out=m.draft_status_v28("E",True)
assert out["ok"] and out["complete"] and out["locked_count"]==10
assert out["blue"]["picks"]["mid"]=="Azir"
assert out["red"]["picks"]["sup"]=="Rakan"
assert out["auto_evaluation"] is not None
row=m.db_one("SELECT draft_json FROM riot_games_v10 WHERE game_id='G'")
assert row and "Gnar" in row["draft_json"] and "Rakan" in row["draft_json"]
print("V28 automatic draft capture regression: OK")
print("locked",out["locked_count"])
print("post_draft",round(out["auto_evaluation"]["probability_team_a"]*100,2))
