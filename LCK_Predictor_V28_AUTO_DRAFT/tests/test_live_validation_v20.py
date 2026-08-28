from pathlib import Path
import importlib.util,json,sqlite3
ROOT=Path(__file__).resolve().parents[1]
# Feed fixture -> normalized in-progress snapshot.
spec=importlib.util.spec_from_file_location('rf',ROOT/'riot_feed.py');rf=importlib.util.module_from_spec(spec);spec.loader.exec_module(rf)
f=json.loads((ROOT/'tests'/'riot_v10_fixture.json').read_text());ev=rf.event_from_details(f['event']);snap=rf.normalize('123',ev,f['window'],f['details'],ev['match']['games'][0])
ss=importlib.util.spec_from_file_location('v20',ROOT/'server.py');m=importlib.util.module_from_spec(ss);ss.loader.exec_module(m)
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
print('V20 Live Validation test: OK')
print('status',ready['status'],'maps',ready['completed_maps'],'20min',ready['checkpoints'][20])
