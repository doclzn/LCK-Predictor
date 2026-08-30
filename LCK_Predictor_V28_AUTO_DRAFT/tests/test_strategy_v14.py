"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path


def test_strategy_v14(server):
    m = server
    ctx=m.series_context_v14("115548147900619029",2)
    assert not ctx.get("error")
    assert ctx["game_number"]==2
    assert len(ctx["fearless_used"])>=10

    seq=m.draft_sequence_v14({"team_a":"HLE","team_b":"DK","side_a":"Blue"})
    assert [x["slot"] for x in seq["pick_order"]]==["B1","R1","R2","B2","B3","R3","R4","B4","B5","R5"]
    assert seq["pick_order"][0]["team"]=="HLE"
    assert seq["pick_order"][1]["team"]=="DK"

    payload={
     "team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16","game_number":2,
     "series_score_a":1,"series_score_b":0,
     "picks_a":{"top":"","jng":"","mid":"","bot":"","sup":""},
     "picks_b":{"top":"","jng":"","mid":"","bot":"","sup":""},
     "fearless_used":ctx["fearless_used"],"bans":[],
     "pick_slot":"B1","target_role":"top","limit":8
    }
    pick=m.draft_strategy_pick_v14(payload)
    assert not pick.get("error")
    assert pick["target_team"]=="HLE"
    assert 0 <= pick["expected_future_maps"] <= 1
    assert pick["candidates"]
    assert all(c["champion"] not in ctx["fearless_used"] for c in pick["candidates"])
    assert all("strategy_delta_pp_equiv" in c for c in pick["candidates"])

    ban=m.draft_ban_strategy_v14({**payload,"ban_slot":"B1BAN"})
    assert not ban.get("error")
    assert ban["banning_team"]=="HLE"
    assert ban["opponent_team"]=="DK"
    assert ban["candidates"]
    assert max(c["relative_priority"] for c in ban["candidates"])==100

    g1=m.evaluate_draft({
     "team_a":"HLE","team_b":"DK","side_a":"Blue","patch":"16.16",
     "picks_a":{"top":"Camille","jng":"Lee Sin","mid":"Ryze","bot":"Ziggs","sup":"Alistar"},
     "picks_b":{"top":"Olaf","jng":"Jarvan IV","mid":"Twisted Fate","bot":"Yunara","sup":"Lulu"},
     "fearless_used":[],
     "rating_override":{"HLE":1679.34,"DK":1734.14}
    })
    assert abs(g1["draft_game_probability_team_a"]-0.5544)<0.02

