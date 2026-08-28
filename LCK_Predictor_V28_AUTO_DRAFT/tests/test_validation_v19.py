from pathlib import Path
import importlib.util,sqlite3,json,datetime
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v19',ROOT/'server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

v=m.v19_validation_summary()
assert v['dataset']['games']==900
assert v['dataset']['games_2025']==551
assert v['dataset']['games_2026']==349
assert v['dataset']['series']==343
ex={x['candidate']:x for x in v['experiments']}
assert ex['core_pool_exhaustion']['retrospective_verdict']=='INCONCLUSIVE'
assert ex['core_flex']['retrospective_verdict']=='RETROSPECTIVE_REJECT'
assert ex['core_pool_exhaustion']['eval2026_log_loss'] < ex['core']['eval2026_log_loss']
assert ex['core_pool_exhaustion']['eval2026_brier'] < ex['core']['eval2026_brier']
assert ex['core_flex']['bootstrap']['ll_delta_lo'] > 0
assert ex['core_flex']['bootstrap']['brier_delta_lo'] > 0

# Frozen model inference is portable/pure Python.
fr=m.db_one("SELECT * FROM validation_freeze_v19 WHERE candidate='core_pool_exhaustion'")
model=json.loads(fr['model_json'])
p=m._v19_frozen_predict(model,{'elo_diff':100,'mastery_diff':.05,'synergy_diff':.01,'pool_exhaustion_adv':.02})
assert 0<p<1

# Cached case produces a late capture and therefore cannot contaminate the prospective gate.
live=m.live_response_v10('115548147900619029',False)
assert live['ok'] and live['draft_analysis']
with sqlite3.connect(ROOT/'data'/'lck_data_v1.sqlite') as con:
    late=con.execute("SELECT COUNT(*) FROM prospective_predictions_v19 WHERE game_id=? AND capture_status='LATE_CAPTURE'",(live['game_id'],)).fetchone()[0]
    assert late>=1
    valid=con.execute("SELECT COUNT(*) FROM prospective_predictions_v19 WHERE game_id=? AND capture_status='VALID_EARLY'",(live['game_id'],)).fetchone()[0]
    assert valid==0
    # V18 persistence bug fixed: table now exists.
    assert con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='series_strategy_runs_v18'").fetchone()
    # Cleanup test capture.
    con.execute("DELETE FROM prospective_predictions_v19 WHERE game_id=?",(live['game_id'],))
    con.execute("DELETE FROM prospective_gate_summary_v19")
    con.commit()
print('V19 Validation Lab test: OK')
print('pool_exhaustion_LL',round(ex['core_pool_exhaustion']['eval2026_log_loss'],6))
print('core_LL',round(ex['core']['eval2026_log_loss'],6))
print('flex_verdict',ex['core_flex']['retrospective_verdict'])
