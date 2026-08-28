from pathlib import Path
import sqlite3,json,argparse,sys
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'lck_data_v1.sqlite'
CHECKPOINTS=(5,10,15,20,25,30)

def readiness(con):
    pol={k:v for k,v in con.execute('select key,value from live_readiness_policy_v20')}
    rows=con.execute('select game_id,blue_team,red_team,checkpoint_second,outcome_blue from live_training_snapshots_v20 where outcome_blue is not null').fetchall()
    games={r[0] for r in rows};teams={x for r in rows for x in (r[1],r[2]) if x}
    cp={m:len({r[0] for r in rows if r[3]==m*60}) for m in CHECKPOINTS}
    th={'maps':int(pol.get('min_completed_maps',120)),'teams':int(pol.get('min_teams',8)),**{f'm{m}':int(pol.get(f'checkpoint_{m}',0)) for m in CHECKPOINTS}}
    ok={'maps':len(games)>=th['maps'],'teams':len(teams)>=th['teams'],**{f'm{m}':cp[m]>=th[f'm{m}'] for m in CHECKPOINTS}}
    return {'ready':all(ok.values()),'games':len(games),'teams':len(teams),'checkpoints':cp,'thresholds':th,'checks':ok}

def main():
    ap=argparse.ArgumentParser(description='V20 development-only live-model trainer. Grouped chronological split; refuses to train before readiness gate.')
    ap.add_argument('--db',default=str(DB));ap.add_argument('--check-only',action='store_true');args=ap.parse_args()
    con=sqlite3.connect(args.db);r=readiness(con);print(json.dumps(r,indent=2,ensure_ascii=False))
    if args.check_only:return 0
    if not r['ready']:
        print('\nTRAINING BLOCKED: readiness gate not satisfied. No model was fitted.')
        return 2
    try:
        import numpy as np, pandas as pd
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import log_loss,brier_score_loss,accuracy_score,roc_auc_score
    except Exception as e:
        print('Training environment requires numpy/pandas/scikit-learn:',e);return 3
    df=pd.read_sql_query('select * from live_training_snapshots_v20 where outcome_blue is not null order by captured_at,game_id,checkpoint_second',con)
    # Split by whole games, never by snapshots.
    game_order=df[['game_id','captured_at']].groupby('game_id',as_index=False).captured_at.min().sort_values('captured_at').game_id.tolist()
    n=len(game_order);a=max(1,int(n*.70));b=max(a+1,int(n*.85));tr=set(game_order[:a]);va=set(game_order[a:b]);te=set(game_order[b:])
    feats=['draft_probability_blue','game_time_seconds','gold_diff','kill_diff','tower_diff','dragon_diff','baron_diff','inhibitor_diff','top_gold_diff','jng_gold_diff','mid_gold_diff','bot_gold_diff','sup_gold_diff','lead_breadth']
    X=df[feats].fillna(0);y=df.outcome_blue.astype(int)
    grid=[]
    for C in [.01,.03,.1,.3,1.0]:
        pipe=Pipeline([('sc',StandardScaler()),('lr',LogisticRegression(C=C,max_iter=3000))]);mask=df.game_id.isin(tr);pipe.fit(X[mask],y[mask]);vm=df.game_id.isin(va);p=pipe.predict_proba(X[vm])[:,1];grid.append((log_loss(y[vm],p,labels=[0,1]),C,pipe))
    grid.sort();C=grid[0][1]
    fitmask=df.game_id.isin(tr|va);pipe=Pipeline([('sc',StandardScaler()),('lr',LogisticRegression(C=C,max_iter=3000))]);pipe.fit(X[fitmask],y[fitmask]);tm=df.game_id.isin(te);p=pipe.predict_proba(X[tm])[:,1]
    metrics={'games_test':len(te),'snapshots_test':int(tm.sum()),'C':C,'log_loss':float(log_loss(y[tm],p,labels=[0,1])),'brier':float(brier_score_loss(y[tm],p)),'accuracy':float(accuracy_score(y[tm],p>=.5)),'auc':float(roc_auc_score(y[tm],p))}
    model={'features':feats,'means':[float(x) for x in pipe.named_steps['sc'].mean_],'scales':[float(x) for x in pipe.named_steps['sc'].scale_],'coef':[float(x) for x in pipe.named_steps['lr'].coef_[0]],'intercept':float(pipe.named_steps['lr'].intercept_[0]),'C':C}
    con.execute('insert into live_training_runs_v20(created_at,status,maps,snapshots,train_cutoff,test_start,features_json,metrics_json,model_json,note) values(datetime("now"),?,?,?,?,?,?,?,?,?)',('CANDIDATE_NOT_PROMOTED',n,len(df),game_order[b-1] if b else None,game_order[b] if b<n else None,json.dumps(feats),json.dumps(metrics),json.dumps(model),'Chronological game-group split. Candidate still requires model review/calibration before app use.'))
    con.commit();print(json.dumps(metrics,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
