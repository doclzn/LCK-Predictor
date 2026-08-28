from pathlib import Path
import importlib.util,time
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v18",ROOT/"server.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert abs(m._v18_series_win_prob(1,0,3,.5,.5)-.75)<1e-9
assert abs(m._v18_series_win_prob(0,1,3,.5,.5)-.25)<1e-9
assert abs(m._v18_series_win_prob(1,1,3,.6,.5)-.6)<1e-9
assert abs(m._v18_series_win_prob(2,1,5,.5,.5)-.75)<1e-9
ctx=m.series_context_v14("115548147900619029",2)
p={"team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16","game_number":2,"series_score_a":1,"series_score_b":0,"best_of":3,
 "picks_a":{"top":"","jng":"","mid":"","bot":"","sup":""},"picks_b":{"top":"","jng":"","mid":"","bot":"","sup":""},
 "fearless_used":ctx["fearless_used"],"bans":[],"root_action_slot":"B1","depth":2,"branch_width":2,"assignment_limit":2,"limit":4}
t=time.perf_counter();r=m.series_plan_v18(p);elapsed=time.perf_counter()-t
assert not r.get("error"),r
assert r["results"]
assert .5<r["baseline_series_probability_root"]<1
series_order=[x["root_action"]["champion"] for x in r["results"]]
map_order=[x["root_action"]["champion"] for x in sorted(r["results"],key=lambda z:z["robust_probability_root"],reverse=True)]
assert series_order!=map_order, (series_order,map_order)
assert all(0<x["series_probability_root"]<1 for x in r["results"])
assert all(x["future_pool"]["pool_a"]["roles"] and x["future_pool"]["pool_b"]["roles"] for x in r["results"])
assert elapsed<30
print("V18 Series Planner test: OK")
print("runtime_sec",round(elapsed,2))
print("baseline_series",round(r["baseline_series_probability_root"],4))
print("series_order",series_order)
print("map_order",map_order)
print("top_series",series_order[0],round(r["results"][0]["series_probability_root"],4))
