"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import json, sqlite3


ROOT = Path(__file__).resolve().parents[1]


def test_live_validation_v20(server, riot):
    m = server
    rf = riot
    f=json.loads((ROOT/'tests'/'riot_v10_fixture.json').read_text());ev=rf.event_from_details(f['event']);snap=rf.normalize('123',ev,f['window'],f['details'],ev['match']['games'][0])
    draft=m._draft_analysis_v10(snap);assert draft
    # Clean fixture ids first.
    with sqlite3.connect(ROOT/'data'/'lck_data_v1.sqlite') as con:
        con.execute("delete from live_training_snapshots_v20 where game_id in ('456','457')")
        con.execute("delete from riot_games_v10 where game_id in ('456','457')");con.commit()
    r=m.v20_capture_live_training(snap,draft);assert r['captured'] and r['checkpoint_second']==1200
    r2=m.v20_capture_live_training(snap,draft);assert not r2['captured']
    # Terminal snapshots must never be admitted as live training data.
    completed=dict(snap);completed['game_id']='457';completed['game_state']='completed';completed['event_state']='completed'
    assert not m.v20_capture_live_training(completed,draft)['captured']
    # Score from final winner cache.
    with sqlite3.connect(ROOT/'data'/'lck_data_v1.sqlite') as con:
        con.execute("insert or replace into riot_games_v10(game_id,event_id,game_number,state,blue_team,red_team,winner) values(?,?,?,?,?,?,?)",('456','123',2,'completed','HLE','DK','HLE'));con.commit()
    assert m.v20_score_live_training()>=1
    ready=m.v20_live_readiness();assert ready['completed_maps']>=1 and not ready['ready'];assert ready['checkpoints'][20]>=1
    # Cleanup.
    with sqlite3.connect(ROOT/'data'/'lck_data_v1.sqlite') as con:
        con.execute("delete from live_training_snapshots_v20 where game_id in ('456','457')")
        con.execute("delete from riot_games_v10 where game_id in ('456','457')");con.commit()
