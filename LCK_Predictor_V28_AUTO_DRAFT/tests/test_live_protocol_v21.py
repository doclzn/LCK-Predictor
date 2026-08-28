from pathlib import Path
import sqlite3, shutil, tempfile, subprocess, sys, json, os
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'train_live_model_v21.py'
with tempfile.TemporaryDirectory() as td:
    tdb=Path(td)/'live.sqlite';shutil.copy2(ROOT/'data'/'lck_data_v1.sqlite',tdb)
    con=sqlite3.connect(tdb);con.execute('DELETE FROM live_training_snapshots_v20');con.execute('DELETE FROM live_model_experiments_v21')
    teams=['GEN','DK','HLE','T1','KT','BFX','BRO','NS','DNS','KRX']
    rid=0
    for i in range(120):
        y=1 if i%2==0 else 0;sgn=1 if y else -1;blue=teams[i%10];red=teams[(i+3)%10]
        for minute in (5,10,15,20,25,30):
            rid+=1;t=minute*60;strength=minute/30
            con.execute('''INSERT INTO live_training_snapshots_v20
              (game_id,event_id,game_number,checkpoint_second,captured_at,game_time_seconds,patch,blue_team,red_team,draft_probability_blue,
               gold_diff,kill_diff,tower_diff,dragon_diff,baron_diff,inhibitor_diff,top_gold_diff,jng_gold_diff,mid_gold_diff,bot_gold_diff,sup_gold_diff,
               lead_breadth,outcome_blue,scored_at,capture_source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (f'G{i:03d}',f'E{i//3:03d}',(i%3)+1,t,f'2026-09-{1+i//10:02d}T{(i%10):02d}:00:00Z',t,'16.17',blue,red,.5,
               sgn*(500+3500*strength),sgn*(1+5*strength),sgn*(1+3*strength),sgn*(1+2*strength),sgn*(1 if minute>=20 else 0),0,
               sgn*(100+600*strength),sgn*(80+500*strength),sgn*(120+800*strength),sgn*(160+1100*strength),sgn*(40+300*strength),sgn*.8,
               y,'2026-09-30T00:00:00Z','synthetic test'))
    con.commit();con.close()
    r=subprocess.run([sys.executable,str(SCRIPT),'--db',str(tdb)],cwd=str(ROOT),capture_output=True,text=True,timeout=90)
    if r.returncode!=0:raise AssertionError(r.stdout+'\n'+r.stderr)
    con=sqlite3.connect(tdb);row=con.execute('SELECT protocol_id,test_metrics_json,decision FROM live_model_experiments_v21').fetchone();con.close()
    assert row and row[0]=='live_model_v1_preregistered'
    metrics=json.loads(row[1]);assert metrics['delta']['log_loss']<0 and metrics['delta']['brier']<0,metrics
    # Same protocol is one-shot: second attempt must refuse to reopen test.
    r2=subprocess.run([sys.executable,str(SCRIPT),'--db',str(tdb)],cwd=str(ROOT),capture_output=True,text=True,timeout=30)
    assert r2.returncode==4,(r2.returncode,r2.stdout,r2.stderr)
# Remove synthetic run artifact, if created.
for f in (ROOT/'governance').glob('LIVE_MODEL_RUN_V21_*.json'):f.unlink()
print('V21 live protocol test: OK')
