"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import time


def test_draft_tree_v15(server):
    m = server
    ctx=m.series_context_v14("115548147900619029",2)
    assert not ctx.get("error")
    assert len(ctx["fearless_used"])>=10

    payload={
     "team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16","game_number":2,
     "series_score_a":1,"series_score_b":0,
     "picks_a":{"top":"","jng":"","mid":"","bot":"","sup":""},
     "picks_b":{"top":"","jng":"","mid":"","bot":"","sup":""},
     "fearless_used":ctx["fearless_used"],"bans":[],
     "root_slot":"B1","root_role":"top","depth":3,"branch_width":2,
     "candidates_per_role":1,"limit":5
    }
    t=time.perf_counter();tree=m.draft_tree_v15(payload);elapsed=time.perf_counter()-t
    assert not tree.get("error"),tree
    assert tree["results"]
    assert tree["root_team"]=="HLE"
    assert tree["model_states_evaluated"]<=30
    assert elapsed<20
    assert all(r["principal_variation"] for r in tree["results"])
    assert all(r["root_action"]["champion"] not in ctx["fearless_used"] for r in tree["results"])

    too_big=m.draft_tree_v15({**payload,"depth":4,"branch_width":4})
    assert too_big.get("error")

    flex=m.flex_resolve_v15({"team":"T1","champions":["Poppy","Aurora","Smolder"],"limit":8})
    assert not flex.get("error")
    assert flex["assignments"]
    assert flex["assignment_count"]>=2

    g1=m.evaluate_draft({
     "team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16",
     "picks_a":{"top":"Camille","jng":"Lee Sin","mid":"Ryze","bot":"Ziggs","sup":"Alistar"},
     "picks_b":{"top":"Olaf","jng":"Jarvan IV","mid":"Twisted Fate","bot":"Yunara","sup":"Lulu"},
     "fearless_used":[],
     "rating_override":{"HLE":1679.34,"DK":1734.14}
    })
    assert abs(g1["draft_game_probability_team_a"]-0.5544)<0.02

