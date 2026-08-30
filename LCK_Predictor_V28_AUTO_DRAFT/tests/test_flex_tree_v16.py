"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import time


def test_flex_tree_v16(server):
    m = server
    p={"team_a":"T1","team_b":"GEN","side_a":"Blue","patch":"16.16","game_number":1,
       "picks_a":{"top":"","jng":"","mid":"","bot":"","sup":""},"picks_b":{"top":"","jng":"","mid":"","bot":"","sup":""},
       "fearless_used":[],"bans":[],"root_slot":"B1","depth":2,"branch_width":2,"assignment_limit":2,"limit":5}
    t=time.perf_counter();r=m.draft_flex_tree_v16(p);elapsed=time.perf_counter()-t
    assert not r.get("error"),r
    assert r["results"]
    assert any(x["root_action"]["role_uncertainty"]>1 for x in r["results"])
    assert all(x["leaf"].get("root_assignment") for x in r["results"])
    assert elapsed<30
    # Full-draft regression remains unchanged.
    g=m.evaluate_draft({"team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16",
     "picks_a":{"top":"Camille","jng":"Lee Sin","mid":"Ryze","bot":"Ziggs","sup":"Alistar"},
     "picks_b":{"top":"Olaf","jng":"Jarvan IV","mid":"Twisted Fate","bot":"Yunara","sup":"Lulu"},"fearless_used":[],
     "rating_override":{"HLE":1679.34,"DK":1734.14}})
    assert abs(g["draft_game_probability_team_a"]-.5544)<.02
