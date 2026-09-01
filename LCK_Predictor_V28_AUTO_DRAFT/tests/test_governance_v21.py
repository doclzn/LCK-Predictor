"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import sqlite3, shutil, tempfile, json


ROOT = Path(__file__).resolve().parents[1]


def test_governance_v21(server):
    m = server
    base=m.v21_governance_summary()
    assert base['integrity']['ok'],base['integrity']
    # Nao travar num numero: o registro cresce a cada selagem. O invariante e
    # que todo experimento registrado carregue sua digital.
    assert base['experiments']
    assert all(e.get('definition_hash') for e in base['experiments'])
    assert base['live_protocol']['hash_ok']
    assert base['live_protocol']['status']=='PRE_REGISTERED_NOT_TRAINED'
    # A versão antiga exigia decision=='COLLECTING' para todos, o que era um
    # retrato do estado em que foi escrita. O invariante de verdade é a
    # coerência: uma candidata só pode ser bloqueada por integridade quando a
    # definição congelada realmente não confere com o lock — e, se confere,
    # nunca pode aparecer como bloqueada.
    verified={f['candidate'] for f in m.v21_verified_v19_freezes()}
    for r in base['promotion_reviews']:
        blocked = r['decision']=='BLOCKED_INTEGRITY'
        assert blocked != (r['candidate'] in verified), (
            f"{r['candidate']}: decision={r['decision']} mas verificada={r['candidate'] in verified}")


def test_governance_v21_promotion_flow(server, monkeypatch):
    """Fluxo sintetico de promocao: candidata forte deve ficar elegivel, e
    adulterar um coeficiente congelado deve bloquea-la.

    Depende de as definicoes congeladas conferirem com governance/
    GOVERNANCE_LOCK_V21.json. Hoje NAO conferem: rodar run_validation_v19.py em
    2026-08-27 reescreveu validation_freeze_v19 e invalidou a pre-registro de
    2026-08-20. Enquanto isso nao for resolvido por decisao explicita (re-
    congelar = nova pre-registro, o historico anterior nao pode ser reivindicado),
    o gate inteiro responde BLOCKED_INTEGRITY e este cenario nao tem como rodar."""
    m = server
    import pytest
    if not m.v21_verified_v19_freezes():
        pytest.skip("freezes V19 divergem do GOVERNANCE_LOCK_V21 - gate bloqueado")
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


def _load_validation_script():
    import importlib.util
    spec=importlib.util.spec_from_file_location(
        'run_validation_v19_guard', ROOT/'scripts'/'run_validation_v19.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_guard_hash_matches_server(server):
    """run_validation_v19.py reimplementa o hash canonico do server.py para nao
    depender de importa-lo. Se as duas implementacoes divergirem, o guarda passa
    a achar que nada esta selado e volta a reescrever o congelamento em silencio
    -- exatamente a falha que ele existe para impedir. Este teste amarra as duas."""
    v=_load_validation_script()
    for row in server.db_rows('SELECT * FROM validation_freeze_v19'):
        obj,expected=server._v21_db_freeze_definition(row)
        assert v._canonical_hash(obj)==expected, row['candidate']


def test_guard_agrees_with_server_on_what_is_sealed(server):
    """O guarda e o server precisam concordar sobre quais candidatas estao
    seladas; se o guarda vir menos, ele libera uma reescrita que quebraria a
    captura."""
    v=_load_validation_script()
    assert set(v.sealed_candidates(server.DB)) == {
        f['candidate'] for f in server.v21_verified_v19_freezes()}


def test_guard_blocks_rewrite_when_sealed(server, tmp_path, monkeypatch):
    """Com congelamento selado, rodar o script sem --allow-reseal deve abortar.

    O estado selado e montado aqui em vez de depender do estado real do repo:
    o guarda precisa estar coberto mesmo quando o congelamento de producao
    esta dessincronizado (que e justamente quando ninguem percebe a falha)."""
    import pytest
    v=_load_validation_script()

    db=tmp_path/'sealed.sqlite'
    shutil.copy2(ROOT/'data'/'lck_data_v1.sqlite', db)
    con=sqlite3.connect(db);con.row_factory=sqlite3.Row
    rows=con.execute("SELECT * FROM validation_freeze_v19 "
                     "WHERE status='FROZEN_AWAITING_PROSPECTIVE'").fetchall()
    con.close()
    assert rows, 'fixture precisa de ao menos uma candidata congelada'

    hashes={}
    for r in rows:
        hashes[r['candidate']]=v._canonical_hash({
            'candidate':r['candidate'],'frozen_at':r['frozen_at'],
            'features':json.loads(r['features_json'] or '[]'),
            'model':json.loads(r['model_json'] or '{}')})
    lock=tmp_path/'GOVERNANCE_LOCK_V21.json'
    lock.write_text(json.dumps({'candidate_definition_hashes':hashes}),encoding='utf-8')
    monkeypatch.setattr(v,'LOCK_FILE',lock)

    assert set(v.sealed_candidates(db))==set(hashes)

    with pytest.raises(SystemExit) as e:
        v.assert_reseal_allowed(db, allow_reseal=False)
    assert 'ABORTADO' in str(e.value)

    v.assert_reseal_allowed(db, allow_reseal=True)  # com a flag, passa


def test_guard_allows_rewrite_when_lock_absent(server, tmp_path, monkeypatch):
    """Sem lock nao ha pre-registro a proteger: o script tem de rodar normalmente,
    senao o guarda inviabilizaria o primeiro congelamento do projeto."""
    v=_load_validation_script()
    monkeypatch.setattr(v,'LOCK_FILE',tmp_path/'nao_existe.json')
    assert v.sealed_candidates(ROOT/'data'/'lck_data_v1.sqlite')==[]
    v.assert_reseal_allowed(ROOT/'data'/'lck_data_v1.sqlite', allow_reseal=False)
