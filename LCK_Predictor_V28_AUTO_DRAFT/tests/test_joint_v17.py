from pathlib import Path
import importlib.util,time
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v17",ROOT/"server.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ctx=m.series_context_v14("115548147900619029",2)
p={"team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16","game_number":2,"series_score_a":1,"series_score_b":0,
 "picks_a":{"top":"","jng":"","mid":"","bot":"","sup":""},"picks_b":{"top":"","jng":"","mid":"","bot":"","sup":""},
 "fearless_used":ctx["fearless_used"],"bans":[],"root_action_slot":"R3BAN","depth":3,"branch_width":2,"assignment_limit":2,"limit":4}
t=time.perf_counter();r=m.joint_draft_plan_v17(p);elapsed=time.perf_counter()-t
assert not r.get("error"),r
assert r["root_action_type"]=="BAN" and r["root_team"]=="DK"
assert r["results"]
assert any(any(a["action_type"]=="PICK" for a in x["principal_variation"]) for x in r["results"])
assert elapsed<30
q={**p,"root_action_slot":"B1","depth":2}
r2=m.joint_draft_plan_v17(q)
assert not r2.get("error") and r2["root_action_type"]=="PICK"
print("V17 Joint Planner test: OK")
print("runtime_sec",round(elapsed,2),"states",r["model_states_evaluated"])
print("top_root",r["results"][0]["root_action"]["champion"],"robust",round(r["results"][0]["robust_probability_root"],4))
