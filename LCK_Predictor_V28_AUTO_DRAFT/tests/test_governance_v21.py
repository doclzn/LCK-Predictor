from pathlib import Path
import importlib.util, sqlite3, shutil, tempfile, json
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v21',ROOT/'server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

base=m.v21_governance_summary()
assert base['integrity']['ok'],base['integrity']
assert len(base['experiments'])==5
assert base['live_protocol']['hash_ok']
assert base['live_protocol']['status']=='PRE_REGISTERED_NOT_TRAINED'
assert all(r['decision']=='COLLECTING' for r in base['promotion_reviews'])

with tempfile.TemporaryDirectory() as td:
    tdb=Path(td)/'test.sqlite';shutil.copy2(ROOT/'data'/'lck_data_v1.sqlite',tdb)
    old=m.DB;m.DB=tdb
    try:
        con=sqlite3.connect(tdb)
        con.execute('DELETE FROM prospective_predictions_v19')
        con.execute('DELETE FROM prospective_gate_summary_v19')
        # Strong synthetic future signal: candidate decisively better than frozen reference predictions.
        rows=[]
        for i in range(100):
            y=i%2;event=f'E{i//2:03d}';gid=f'FUT{i:03d}';blue='GEN' if i%3 else 'DK';red='T1'
            core=.58 if y else .42;cand=.78 if y else .22
            common=(gid,'2026-09-01T00:00:00Z',blue,red,'{}','2026-08-20T21:56:58+00:00',y,'2026-09-01T01:00:00Z',event,(i%3)+1,event,120.0,'VALID_EARLY','V21_TEST')
            for name,p in [('core',core),('core_pool_exhaustion',cand)]:
                con.execute('''INSERT INTO prospective_predictions_v19
                  (game_id,candidate,captured_at,blue_team,red_team,probability_blue,features_json,model_frozen_at,outcome_blue,scored_at,event_id,game_number,series_key,game_time_seconds,capture_status,validation_epoch)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(common[0],name,common[1],common[2],common[3],p,*common[4:]))
        con.commit();con.close()
        reviews=m.v21_refresh_promotion_reviews()
        pool=next(x for x in reviews if x['candidate']=='core_pool_exhaustion')
        assert pool['decision']=='ELIGIBLE_FOR_REVIEW',pool
        assert pool['sample_pass'] and pool['practical_pass'] and pool['uncertainty_pass'] and pool['calibration_pass']
        # Tamper one frozen coefficient: it must be excluded/blocked rather than silently accepted.
        con=sqlite3.connect(tdb);r=con.execute("SELECT model_json FROM validation_freeze_v19 WHERE candidate='core_pool_exhaustion'").fetchone();obj=json.loads(r[0]);obj['coef'][0]+=0.001
        con.execute("UPDATE validation_freeze_v19 SET model_json=? WHERE candidate='core_pool_exhaustion'",(json.dumps(obj),));con.commit();con.close()
        verified=m.v21_verified_v19_freezes()
        assert 'core_pool_exhaustion' not in {x['candidate'] for x in verified}
        reviews=m.v21_refresh_promotion_reviews();pool=next(x for x in reviews if x['candidate']=='core_pool_exhaustion')
        assert pool['decision']=='BLOCKED_INTEGRITY',pool
        events=m.db_rows("SELECT * FROM governance_events_v21 WHERE event_type='FROZEN_MODEL_DRIFT'")
        assert events
    finally:m.DB=old
print('V21 governance test: OK')
