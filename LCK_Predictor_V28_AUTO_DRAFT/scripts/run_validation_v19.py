from __future__ import annotations
import sqlite3, json, math, itertools, argparse, time
from pathlib import Path
from collections import defaultdict
import numpy as np
import os
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import log_loss, brier_score_loss, accuracy_score, roc_auc_score

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'lck_data_v1.sqlite'
ROLES=['top','jng','mid','bot','sup']
ROLE_ALIASES={'top':'top','jng':'jng','jungle':'jng','mid':'mid','middle':'mid','bot':'bot','bottom':'bot','adc':'bot','sup':'sup','support':'sup'}
C_GRID=[0.01,0.03,0.1,0.3,1.0]
MODEL_SPECS={
    'core': ['elo_diff','mastery_diff','synergy_diff'],
    'core_pool_exhaustion': ['elo_diff','mastery_diff','synergy_diff','pool_exhaustion_adv'],
    'core_pool_remaining': ['elo_diff','mastery_diff','synergy_diff','remaining_pool_diff'],
    'core_flex': ['elo_diff','mastery_diff','synergy_diff','flex_diff'],
    'core_pool_flex': ['elo_diff','mastery_diff','synergy_diff','pool_exhaustion_adv','flex_diff'],
    'core_champ_solo': ['elo_diff','mastery_diff','synergy_diff','champ_solo_diff'],
    'core_champ_pair': ['elo_diff','mastery_diff','synergy_diff','champ_pair_diff'],
    'core_champ_matchup': ['elo_diff','mastery_diff','synergy_diff','matchup_diff'],
    'core_champ_all': ['elo_diff','mastery_diff','synergy_diff','champ_solo_diff','champ_pair_diff','matchup_diff'],
}
K_CHAMP=10.0  # suavizacao bayesiana das taxas de vitoria por campeao, em direcao a 0.5

def siglog(x):
    return 1/(1+math.exp(-max(-30,min(30,x))))

def safe_metric(y,p):
    p=np.clip(np.asarray(p,float),1e-6,1-1e-6); y=np.asarray(y,int)
    return {
        'accuracy': float(accuracy_score(y,p>=.5)),
        'log_loss': float(log_loss(y,p,labels=[0,1])),
        'brier': float(brier_score_loss(y,p)),
        'roc_auc': float(roc_auc_score(y,p)) if len(set(y))>1 else None,
        'ece': float(ece(y,p,10)),
        'calibration_slope': calibration(y,p)[0],
        'calibration_intercept': calibration(y,p)[1],
    }

def ece(y,p,bins=10):
    y=np.asarray(y);p=np.asarray(p)
    cuts=np.linspace(0,1,bins+1); out=0.0
    for i in range(bins):
        mask=(p>=cuts[i]) & (p<(cuts[i+1] if i<bins-1 else cuts[i+1]+1e-12))
        if mask.any(): out += mask.mean()*abs(y[mask].mean()-p[mask].mean())
    return out

def calibration(y,p):
    p=np.clip(np.asarray(p,float),1e-5,1-1e-5); y=np.asarray(y,int)
    x=np.log(p/(1-p)).reshape(-1,1)
    if len(set(y))<2:return None,None
    lr=LogisticRegression(C=1e6,solver='lbfgs',max_iter=2000).fit(x,y)
    return float(lr.coef_[0,0]),float(lr.intercept_[0])

def build_series_elo_map(con):
    rows=con.execute('SELECT series_key,team1,team2,elo_diff FROM pregame_series_features_snapshot').fetchall()
    return {r[0]:(r[1],r[2],r[3]) for r in rows}

def eb(player,champ,overall,pc,strength=32.0):
    g,w=overall.get(player,(0,0)); prior=(w/g) if g else .5
    cg,cw=pc.get((player,champ),(0,0))
    return (cw+strength*prior)/(cg+strength),cg

def pool_role(player,exclude,overall,pc,player_champs,topn=3):
    vals=[]
    for champ in player_champs.get(player,set()):
        if champ in exclude:continue
        v,g=eb(player,champ,overall,pc,32.0)
        vals.append((v,g,champ))
    vals.sort(reverse=True)
    vals=vals[:topn]
    if not vals:return .5,0
    wt=[.60,.28,.12][:len(vals)]; den=sum(wt)
    return sum(vals[i][0]*wt[i] for i in range(len(vals)))/den, sum(x[1] for x in vals)

def pool_team(players_by_role,exclude,overall,pc,player_champs):
    role_vals=[]; coverage=0
    for role in ROLES:
        player=players_by_role.get(role)
        if not player:
            role_vals.append(.5);continue
        v,c=pool_role(player,exclude,overall,pc,player_champs)
        role_vals.append(v);coverage += int(c>0)
    avg=sum(role_vals)/5; bottleneck=min(role_vals)
    return .76*avg+.24*bottleneck,coverage

def flex_score(champ,role_counts):
    roles=role_counts.get(champ,{})
    vals=[v for v in roles.values() if v>0]
    total=sum(vals); rc=len(vals)
    if rc<=1 or total<=0:return 0.0
    probs=[v/total for v in vals]
    ent=-sum(p*math.log(p,2) for p in probs)
    maxent=math.log(rc,2)
    norm=ent/maxent if maxent>0 else 0
    volume=min(1,total/40)
    return .55*min(1,(rc-1)/2)+.30*norm+.15*volume

# Ligas que compoem o dataset de validacao. O banco pode conter LPL para
# avaliacao comparativa; sem este filtro o dataset misturaria as ligas.
MODEL_LEAGUES=tuple(x.strip() for x in
                    os.environ.get('MODEL_LEAGUES','LCK').split(',') if x.strip())


# Ligas em que o modelo e AVALIADO. Permite treinar com LCK+LPL (amostra
# maior) e medir o efeito no que interessa: acerto na LCK. Vazio = todas.
EVAL_LEAGUES=tuple(x.strip() for x in
                   os.environ.get('EVAL_LEAGUES','').split(',') if x.strip())


def eval_mask(df):
    if not EVAL_LEAGUES or 'league' not in df.columns:
        return pd.Series(True,index=df.index)
    return df.league.isin(EVAL_LEAGUES)


def _lg():
    if not MODEL_LEAGUES:
        return '',()
    return ' WHERE league IN ('+','.join('?'*len(MODEL_LEAGUES))+')',tuple(MODEL_LEAGUES)


def build_dataset(con):
    w,a=_lg()
    team=pd.read_sql_query('SELECT * FROM team_games'+w+' ORDER BY date,gameid,side',con,params=a)
    players=pd.read_sql_query('SELECT gameid,date,side,position,playername,team,champion,result,year FROM player_games'+w+' ORDER BY date,gameid,side,position',con,params=a)
    elo_map=build_series_elo_map(con)
    pgroup={gid:g.copy() for gid,g in players.groupby('gameid')}
    overall={}; pc={}; player_champs=defaultdict(set); synergy={}; role_counts=defaultdict(lambda:defaultdict(int)); used_series=defaultdict(set)
    champ_solo={}; champ_pair={}; champ_mu={}
    def smooth(d,k):
        g,w=d.get(k,(0.0,0.0))
        return (w+K_CHAMP/2)/(g+K_CHAMP)
    def solo_score(rc):
        vals=[smooth(champ_solo,(r,rc[r])) for r in ROLES if r in rc]
        return sum(vals)/len(vals) if vals else .5
    def pair_score(rc):
        chs=sorted(rc[r] for r in ROLES if r in rc)
        vals=[smooth(champ_pair,tuple(sorted((a,b)))) for a,b in itertools.combinations(chs,2)]
        return sum(vals)/len(vals) if vals else .5
    def matchup_edge(rc_a,rc_b):
        acc=0.0
        for r in ROLES:
            a,b=rc_a.get(r),rc_b.get(r)
            if a is None or b is None: continue
            acc += smooth(champ_mu,(r,a,b))-.5
        return acc
    rows=[]
    for gid,tg in team.groupby('gameid',sort=False):
        if len(tg)!=2 or gid not in pgroup: continue
        pg=pgroup[gid]
        if len(pg)!=10: continue
        bt=tg[tg.side.str.lower()=='blue']; rt=tg[tg.side.str.lower()=='red']
        if len(bt)!=1 or len(rt)!=1: continue
        br=bt.iloc[0]; rr=rt.iloc[0]
        blue=str(br['team']); red=str(rr['team']); day=str(br['date'])[:10]
        league=br['league'] if 'league' in tg.columns else None
        series_key=f"{day}__{'|'.join(sorted([blue,red]))}"
        game_num=int(br['game']) if not pd.isna(br['game']) else 1
        y=int(br['result'])
        ep=elo_map.get(series_key)
        if ep:
            t1,t2,ed=ep
            elo_diff=float(ed if blue==t1 else -ed)
        else: elo_diff=np.nan

        bpg=pg[pg.side.str.lower()=='blue']; rpg=pg[pg.side.str.lower()=='red']
        def side_info(g):
            prs={};champs=[]; mastery=[]; rc={}
            for _,r in g.iterrows():
                role=ROLE_ALIASES.get(str(r['position']).lower(),str(r['position']).lower())
                if role not in ROLES:continue
                player=str(r['playername']); champ=str(r['champion'])
                prs[role]=player; champs.append(champ); rc[role]=champ
                mastery.append(eb(player,champ,overall,pc)[0])
            pairs=[]
            for a,b in itertools.combinations(champs,2):
                k=tuple(sorted((a,b))); gg,ww=synergy.get(k,(0,0));pairs.append((ww+2)/(gg+4))
            syn=sum(pairs)/len(pairs) if pairs else .5
            flex=sum(flex_score(c,role_counts) for c in champs)/len(champs) if champs else 0.0
            return prs,champs,rc,(sum(mastery)/len(mastery) if mastery else .5),syn,flex
        bplayers,bchamps,brc,bmaster,bsyn,bflex=side_info(bpg)
        rplayers,rchamps,rrc,rmaster,rsyn,rflex=side_info(rpg)

        champ_solo_diff=solo_score(brc)-solo_score(rrc)
        champ_pair_diff=pair_score(brc)-pair_score(rrc)
        matchup_diff=matchup_edge(brc,rrc)

        excluded=set(used_series[series_key])
        bpool,bcover=pool_team(bplayers,excluded,overall,pc,player_champs)
        rpool,rcover=pool_team(rplayers,excluded,overall,pc,player_champs)
        bbase,_=pool_team(bplayers,set(),overall,pc,player_champs)
        rbase,_=pool_team(rplayers,set(),overall,pc,player_champs)
        bloss=max(0,bbase-bpool); rloss=max(0,rbase-rpool)

        rows.append({
            'gameid':gid,'date':str(br['date']),'year':int(br['year']),'series_key':series_key,'game_number':game_num,
            'league':league,
            'blue_team':blue,'red_team':red,'y':y,
            'elo_diff':elo_diff,'mastery_diff':bmaster-rmaster,'synergy_diff':bsyn-rsyn,
            'remaining_pool_diff':bpool-rpool,
            'pool_exhaustion_adv':rloss-bloss,
            'blue_pool_loss':bloss,'red_pool_loss':rloss,
            'flex_diff':bflex-rflex,
            'pool_coverage_blue':bcover,'pool_coverage_red':rcover,
            'used_champions_before':len(excluded),
            'champ_solo_diff':champ_solo_diff,'champ_pair_diff':champ_pair_diff,'matchup_diff':matchup_diff,
        })

        # Update state only after feature capture.
        for _,r in pg.iterrows():
            player=str(r['playername']);champ=str(r['champion']);win=int(r['result']);role=ROLE_ALIASES.get(str(r['position']).lower(),str(r['position']).lower())
            g,w=overall.get(player,(0,0));overall[player]=(g+1,w+win)
            g,w=pc.get((player,champ),(0,0));pc[(player,champ)]=(g+1,w+win);player_champs[player].add(champ)
            if role in ROLES: role_counts[champ][role]+=1
        for sideg in (bpg,rpg):
            champs=[str(x) for x in sideg['champion'].tolist()]
            win=int(sideg.iloc[0]['result'])
            for a,b in itertools.combinations(champs,2):
                k=tuple(sorted((a,b)));g,w=synergy.get(k,(0,0));synergy[k]=(g+1,w+win)
        for r in ROLES:
            ch=brc.get(r)
            if ch is not None:
                g,w=champ_solo.get((r,ch),(0,0));champ_solo[(r,ch)]=(g+1,w+y)
            ch=rrc.get(r)
            if ch is not None:
                g,w=champ_solo.get((r,ch),(0,0));champ_solo[(r,ch)]=(g+1,w+(1-y))
        for chs,win in ((bchamps,y),(rchamps,1-y)):
            for a,b in itertools.combinations(sorted(chs),2):
                k=(a,b);g,w=champ_pair.get(k,(0,0));champ_pair[k]=(g+1,w+win)
        for r in ROLES:
            a,b=brc.get(r),rrc.get(r)
            if a is None or b is None: continue
            g,w=champ_mu.get((r,a,b),(0,0));champ_mu[(r,a,b)]=(g+1,w+y)
            g,w=champ_mu.get((r,b,a),(0,0));champ_mu[(r,b,a)]=(g+1,w+(1-y))
        used_series[series_key].update(bchamps);used_series[series_key].update(rchamps)
    df=pd.DataFrame(rows).sort_values(['date','gameid']).reset_index(drop=True)
    return df

def series_time_splits(df2025,n_splits=4):
    series=df2025[['series_key','date']].drop_duplicates().sort_values('date')['series_key'].tolist()
    # expanding splits with ~equal validation blocks
    n=len(series); block=max(1,n//(n_splits+1)); out=[]
    for i in range(1,n_splits+1):
        train_end=block*i; val_end=min(n,block*(i+1))
        if val_end<=train_end:continue
        tr=set(series[:train_end]); va=set(series[train_end:val_end])
        ti=df2025.index[df2025.series_key.isin(tr)].to_numpy(); vi=df2025.index[df2025.series_key.isin(va)].to_numpy()
        if len(ti)>40 and len(vi)>20:out.append((ti,vi))
    return out

def make_pipe(c):
    return Pipeline([('imp',SimpleImputer(strategy='median')),('sc',StandardScaler()),('lr',LogisticRegression(C=c,solver='lbfgs',max_iter=3000))])

def tune_2025(df,features):
    d=df[df.year==2025].reset_index(drop=True); X=d[features];y=d.y.values
    splits=series_time_splits(d,4); scores=[]
    for c in C_GRID:
        mets=[]
        for ti,vi in splits:
            p=make_pipe(c);p.fit(X.iloc[ti],y[ti]);pr=p.predict_proba(X.iloc[vi])[:,1]
            mets.append(safe_metric(y[vi],pr))
        scores.append({'C':c,'mean_log_loss':float(np.mean([m['log_loss'] for m in mets])),
                       'mean_brier':float(np.mean([m['brier'] for m in mets])),
                       'mean_accuracy':float(np.mean([m['accuracy'] for m in mets])),
                       'folds':len(mets)})
    scores.sort(key=lambda x:(x['mean_log_loss'],x['mean_brier']))
    return scores[0],scores

def fit_eval(df,features,c,train_year=2025,test_year=2026):
    tr=df[df.year==train_year];te=df[(df.year==test_year)&eval_mask(df)]
    pipe=make_pipe(c);pipe.fit(tr[features],tr.y.values)
    pred=pipe.predict_proba(te[features])[:,1]
    return pipe,pred,safe_metric(te.y.values,pred)

def bootstrap_delta(test,pa,pb,n=2000,seed=19):
    # delta candidate - core. negative LL/Brier is improvement.
    rng=np.random.default_rng(seed); series=test.series_key.unique();vals=[]
    y=test.y.to_numpy(); idx_by={s:np.flatnonzero(test.series_key.to_numpy()==s) for s in series}
    for _ in range(n):
        sample=rng.choice(series,size=len(series),replace=True)
        idx=np.concatenate([idx_by[s] for s in sample])
        yy=y[idx]; a=np.clip(pa[idx],1e-6,1-1e-6); b=np.clip(pb[idx],1e-6,1-1e-6)
        lla=log_loss(yy,a,labels=[0,1]);llb=log_loss(yy,b,labels=[0,1])
        bra=brier_score_loss(yy,a);brb=brier_score_loss(yy,b)
        vals.append((lla-llb,bra-brb))
    arr=np.asarray(vals)
    return {'ll_delta_mean':float(arr[:,0].mean()),'ll_delta_lo':float(np.quantile(arr[:,0],.025)),'ll_delta_hi':float(np.quantile(arr[:,0],.975)),
            'brier_delta_mean':float(arr[:,1].mean()),'brier_delta_lo':float(np.quantile(arr[:,1],.025)),'brier_delta_hi':float(np.quantile(arr[:,1],.975))}

def extract_frozen(pipe,features):
    imp=pipe.named_steps['imp'];sc=pipe.named_steps['sc'];lr=pipe.named_steps['lr']
    return {'features':features,'imputer_medians':[float(x) for x in imp.statistics_],
            'means':[float(x) for x in sc.mean_],'scales':[float(x) for x in sc.scale_],
            'coef':[float(x) for x in lr.coef_[0]],'intercept':float(lr.intercept_[0])}

def run(db=DB):
    t0=time.time();con=sqlite3.connect(db)
    con.row_factory=sqlite3.Row
    df=build_dataset(con)
    print('dataset',len(df),'2025',sum(df.year==2025),'2026',sum(df.year==2026),'series',df.series_key.nunique())
    print('treino ligas:',','.join(MODEL_LEAGUES) or 'todas',
          '| avaliacao ligas:',','.join(EVAL_LEAGUES) or 'todas',
          '| jogos de avaliacao 2026:',int(((df.year==2026)&eval_mask(df)).sum()))
    # Pre-specified model family. No changes after 2026 metrics are computed in this run.
    tuned={};ext={};preds={};pipes={}
    for name,features in MODEL_SPECS.items():
        best,grid=tune_2025(df,features); tuned[name]={'best':best,'grid':grid}
        pipe,pred,met=fit_eval(df,features,best['C']);pipes[name]=pipe;preds[name]=pred;ext[name]=met
        print(name,best['C'],met)
    test=df[(df.year==2026)&eval_mask(df)].reset_index(drop=True);core=preds['core']
    boot={}
    for name in MODEL_SPECS:
        if name=='core':continue
        boot[name]=bootstrap_delta(test,preds[name],core,2000,19)
    # Retrospective verdicts: not promotion decisions.
    verdict={}
    for name in MODEL_SPECS:
        if name=='core':verdict[name]='REFERENCE'
        else:
            dLL=ext[name]['log_loss']-ext['core']['log_loss']; dB=ext[name]['brier']-ext['core']['brier'];ci=boot[name]
            if dLL<0 and dB<0 and (ci['ll_delta_hi']<=0 or ci['brier_delta_hi']<=0): verdict[name]='RETROSPECTIVE_SUPPORT'
            elif dLL>0 and dB>0: verdict[name]='RETROSPECTIVE_REJECT'
            else: verdict[name]='INCONCLUSIVE'

    # Refit frozen prospective candidates on all currently available historical games.
    frozen={}
    for name,features in MODEL_SPECS.items():
        p=make_pipe(tuned[name]['best']['C']);p.fit(df[features],df.y.values);frozen[name]=extract_frozen(p,features)
        frozen[name]['C']=tuned[name]['best']['C']

    con.executescript('''
    DROP TABLE IF EXISTS validation_dataset_v19;
    CREATE TABLE IF NOT EXISTS validation_dataset_v19(
      gameid TEXT PRIMARY KEY,date TEXT,year INTEGER,series_key TEXT,game_number INTEGER,blue_team TEXT,red_team TEXT,y INTEGER,
      elo_diff REAL,mastery_diff REAL,synergy_diff REAL,remaining_pool_diff REAL,pool_exhaustion_adv REAL,
      blue_pool_loss REAL,red_pool_loss REAL,flex_diff REAL,pool_coverage_blue INTEGER,pool_coverage_red INTEGER,used_champions_before INTEGER,
      champ_solo_diff REAL,champ_pair_diff REAL,matchup_diff REAL);
    CREATE TABLE IF NOT EXISTS validation_experiments_v19(
      candidate TEXT PRIMARY KEY,features_json TEXT,selected_c REAL,cv2025_log_loss REAL,cv2025_brier REAL,
      eval2026_accuracy REAL,eval2026_log_loss REAL,eval2026_brier REAL,eval2026_auc REAL,eval2026_ece REAL,
      calibration_slope REAL,calibration_intercept REAL,delta_log_loss_vs_core REAL,delta_brier_vs_core REAL,
      bootstrap_json TEXT,retrospective_verdict TEXT,blind_status TEXT,note TEXT);
    CREATE TABLE IF NOT EXISTS validation_freeze_v19(
      candidate TEXT PRIMARY KEY,frozen_at TEXT,features_json TEXT,model_json TEXT,status TEXT,min_future_games INTEGER,min_future_series INTEGER,
      promotion_rule TEXT,retrospective_verdict TEXT);
    CREATE TABLE IF NOT EXISTS validation_layer_status_v19(
      layer TEXT PRIMARY KEY,retrospective_testable INTEGER,prospective_testable INTEGER,current_evidence TEXT,decision TEXT,note TEXT);
    CREATE TABLE IF NOT EXISTS prospective_predictions_v19(
      id INTEGER PRIMARY KEY AUTOINCREMENT,game_id TEXT,candidate TEXT,captured_at TEXT,blue_team TEXT,red_team TEXT,
      probability_blue REAL,features_json TEXT,model_frozen_at TEXT,outcome_blue INTEGER,scored_at TEXT,
      UNIQUE(game_id,candidate));
    CREATE TABLE IF NOT EXISTS prospective_gate_summary_v19(
      candidate TEXT PRIMARY KEY,games INTEGER,series_count INTEGER,log_loss REAL,brier REAL,accuracy REAL,ece REAL,
      delta_log_loss_vs_core REAL,delta_brier_vs_core REAL,bootstrap_json TEXT,gate_status TEXT,updated_at TEXT);
    ''')
    con.execute('DELETE FROM validation_dataset_v19')
    cols=['gameid','date','year','series_key','game_number','blue_team','red_team','y','elo_diff','mastery_diff','synergy_diff','remaining_pool_diff','pool_exhaustion_adv','blue_pool_loss','red_pool_loss','flex_diff','pool_coverage_blue','pool_coverage_red','used_champions_before','champ_solo_diff','champ_pair_diff','matchup_diff']
    con.executemany('INSERT INTO validation_dataset_v19 VALUES('+','.join('?' for _ in cols)+')',[tuple(None if pd.isna(r[c]) else r[c] for c in cols) for _,r in df.iterrows()])
    con.execute('DELETE FROM validation_experiments_v19')
    for name,features in MODEL_SPECS.items():
        m=ext[name];best=tuned[name]['best'];b=boot.get(name)
        con.execute('''INSERT INTO validation_experiments_v19 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
            name,json.dumps(features),best['C'],best['mean_log_loss'],best['mean_brier'],m['accuracy'],m['log_loss'],m['brier'],m['roc_auc'],m['ece'],m['calibration_slope'],m['calibration_intercept'],
            m['log_loss']-ext['core']['log_loss'],m['brier']-ext['core']['brier'],json.dumps(b) if b else None,verdict[name],
            'RETROSPECTIVE_NOT_PRISTINE','2026 was not used for hyperparameter tuning in this run, but it is not a pristine project-level holdout because prior versions already examined 2026 outcomes.'))
    con.execute('DELETE FROM validation_freeze_v19')
    now=pd.Timestamp.utcnow().isoformat()
    for name in MODEL_SPECS:
        con.execute('''INSERT INTO validation_freeze_v19 VALUES(?,?,?,?,?,?,?,?,?)''',(
            name,now,json.dumps(MODEL_SPECS[name]),json.dumps(frozen[name]),'FROZEN_AWAITING_PROSPECTIVE',100,40,
            'After >=100 future maps and >=40 series: candidate must improve both Log Loss and Brier vs frozen core; practical targets ΔLL<=-0.005 and ΔBrier<=-0.002, with no material calibration degradation. Bootstrap uncertainty is reported and no retuning is allowed before gate review.',verdict[name]))
    layers=[
      ('Fearless pool exhaustion',1,1,'Retrospective walk-forward + 2026 retrospective audit','FROZEN_PROSPECTIVE' if verdict['core_pool_exhaustion']!='RETROSPECTIVE_REJECT' else 'REJECTED_RETROSPECTIVELY','Feature is computed using only champions consumed earlier in the same series.'),
      ('Remaining pool resilience',1,1,'Retrospective walk-forward + 2026 retrospective audit','FROZEN_PROSPECTIVE' if verdict['core_pool_remaining']!='RETROSPECTIVE_REJECT' else 'REJECTED_RETROSPECTIVELY','Tests the V18 future-pool premise at map level.'),
      ('Flex value',1,1,'Retrospective post-draft predictive audit','FROZEN_PROSPECTIVE' if verdict['core_flex']!='RETROSPECTIVE_REJECT' else 'REJECTED_RETROSPECTIVELY','Final draft is known; flex score itself is calculated only from prior role usage.'),
      ('Ban Engine',0,1,'No historical ban-order table in current local corpus','DATA_BLOCKED','Do not infer ban value from picks/results. Requires ban sequence collection.'),
      ('Minimax / recommendation policy',0,1,'Counterfactual policy not observable from played drafts','PROSPECTIVE_OBSERVATIONAL_ONLY','Can audit stability and realized outcomes of chosen/recommended lines, but not causal optimality without stronger design.'),
      ('Live model',0,1,'Only one stored live snapshot in this build','INSUFFICIENT_DATA','Continue snapshot collection; train only after enough completed maps and time coverage.'),
    ]
    con.execute('DELETE FROM validation_layer_status_v19')
    con.executemany('INSERT INTO validation_layer_status_v19 VALUES(?,?,?,?,?,?)',layers)
    # Fix/create V18 run table that was missing in prior build.
    con.execute('''CREATE TABLE IF NOT EXISTS series_strategy_runs_v18(
      id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,team_a TEXT,team_b TEXT,score_a INTEGER,score_b INTEGER,best_of INTEGER,
      root_action_slot TEXT,root_team TEXT,current_series_probability_root REAL,result_json TEXT,nodes_evaluated INTEGER,elapsed_ms REAL,status TEXT,model_version TEXT)''')
    for k,v in {
      'app_version':'V19 Validation Lab','validation_v19_freeze_time':now,'validation_v19_status':'FROZEN_AWAITING_PROSPECTIVE',
      'validation_v19_blind_status':'RETROSPECTIVE_NOT_PRISTINE','validation_v19_dataset_games':str(len(df))
    }.items():
        con.execute('DELETE FROM metadata WHERE key=?',(k,));con.execute('INSERT INTO metadata(key,value) VALUES(?,?)',(k,v))
    con.execute('''INSERT OR REPLACE INTO model_registry_v10(layer,version,status,validated,primary_metric,metric_value,note)
                   VALUES(?,?,?,?,?,?,?)''',('Feature validation','V19 Validation Lab','FROZEN_CANDIDATES',0,'Prospective gate',None,
                   'Retrospective audit complete; project-level 2026 is not pristine. Frozen candidates await future LCK maps before any promotion.'))
    con.commit();con.close()
    report={'generated_at':now,'dataset':{'games':len(df),'games_2025':int((df.year==2025).sum()),'games_2026':int((df.year==2026).sum()),'series':int(df.series_key.nunique())},
            'model_specs':MODEL_SPECS,'tuning_2025':tuned,'retrospective_2026':ext,'bootstrap_vs_core':boot,'verdict':verdict,
            'blind_status':'RETROSPECTIVE_NOT_PRISTINE','prospective_gate':{'min_games':100,'min_series':40,'no_retuning':True}}
    (ROOT/'VALIDATION_V19_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('verdict',verdict,'elapsed',round(time.time()-t0,1),'s')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',default=str(DB));args=ap.parse_args();run(Path(args.db))
