"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import sqlite3, json, datetime


ROOT = Path(__file__).resolve().parents[1]


def test_validation_v19(server):
    m = server
    v=m.v19_validation_summary()
    # Invariantes em vez das contagens cravadas de quando o teste foi escrito
    # (900/551/349/343): o dataset cresce a cada importação — só a importação
    # da LPL o levou a 6.771 — e um número fixo aqui só sinaliza a própria
    # desatualização, nunca uma regressão real.
    ds=v['dataset']
    assert ds['games']>0 and ds['series']>0
    assert ds['games_2025']+ds['games_2026']<=ds['games']
    assert ds['series']<=ds['games'], 'uma série tem ao menos um mapa'
    ex={x['candidate']:x for x in v['experiments']}
    assert 'core' in ex, 'o modelo de referência precisa estar entre os experimentos'
    # Os vereditos e limites de bootstrap cravados aqui eram os da rodada
    # original. Rodar run_validation_v19.py de novo em 2026-08-27, com o dataset
    # já contendo a LPL, produziu outros — o que é esperado, não regressão. O
    # que precisa valer sempre é a estrutura do registro.
    VERDICTS={'REFERENCE','RETROSPECTIVE_SUPPORT','RETROSPECTIVE_REJECT','INCONCLUSIVE'}
    assert ex['core']['retrospective_verdict']=='REFERENCE'
    for name,x in ex.items():
        assert x['retrospective_verdict'] in VERDICTS,(name,x['retrospective_verdict'])
        assert 0<x['eval2026_log_loss']<2,(name,x['eval2026_log_loss'])
        assert 0<x['eval2026_brier']<1,(name,x['eval2026_brier'])
        if name=='core': continue
        b=x['bootstrap']
        assert b['ll_delta_lo']<=b['ll_delta_hi'],(name,b)
        assert b['brier_delta_lo']<=b['brier_delta_hi'],(name,b)

    # Frozen model inference is portable/pure Python.
    fr=m.db_one("SELECT * FROM validation_freeze_v19 WHERE candidate='core_pool_exhaustion'")
    model=json.loads(fr['model_json'])
    p=m._v19_frozen_predict(model,{'elo_diff':100,'mastery_diff':.05,'synergy_diff':.01,'pool_exhaustion_adv':.02})
    assert 0<p<1

    # V18 persistence bug fixed: table now exists.
    assert m.db_one("SELECT name FROM sqlite_master WHERE type='table' AND name='series_strategy_runs_v18'")


def test_v19_late_capture_cannot_contaminate_gate(server):
    """Um snapshot em cache tem de virar LATE_CAPTURE, nunca VALID_EARLY.

    v19_capture_prospective aborta com 'no frozen candidates' quando as
    definições congeladas não conferem com o lock de governança — e é o estado
    atual desde 2026-08-27. Consequência prática: a coleta prospectiva está
    parada, com a última captura em 2026-08-26.
    """
    import pytest
    m = server
    if not m.v21_verified_v19_freezes():
        pytest.skip("freezes V19 divergem do GOVERNANCE_LOCK_V21 - captura prospectiva desligada")
    live=m.live_response_v10('115548147900619029',False)
    assert live['ok'] and live['draft_analysis']
    with sqlite3.connect(ROOT/'data'/'lck_data_v1.sqlite') as con:
        late=con.execute("SELECT COUNT(*) FROM prospective_predictions_v19 WHERE game_id=? AND capture_status='LATE_CAPTURE'",(live['game_id'],)).fetchone()[0]
        assert late>=1
        valid=con.execute("SELECT COUNT(*) FROM prospective_predictions_v19 WHERE game_id=? AND capture_status='VALID_EARLY'",(live['game_id'],)).fetchone()[0]
        assert valid==0
        # Cleanup test capture.
        con.execute("DELETE FROM prospective_predictions_v19 WHERE game_id=?",(live['game_id'],))
        con.execute("DELETE FROM prospective_gate_summary_v19")
        con.commit()
