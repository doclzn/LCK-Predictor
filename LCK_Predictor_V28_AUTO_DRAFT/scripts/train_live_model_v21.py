from __future__ import annotations
from pathlib import Path
import argparse, sqlite3, json, math, hashlib, random, sys, datetime

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'lck_data_v1.sqlite'
PROTOCOL_FILE=ROOT/'governance'/'LIVE_TRAINING_PROTOCOL_V21.json'
CHECKPOINTS=(5,10,15,20,25,30)

def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def hobj(obj):return hashlib.sha256(canonical(obj).encode()).hexdigest()
def sigmoid(z):
    z=max(-35.0,min(35.0,z));return 1/(1+math.exp(-z))

def load_protocol():
    p=json.loads(PROTOCOL_FILE.read_text(encoding='utf-8'))
    expected=p.get('protocol_hash');actual=hobj({k:v for k,v in p.items() if k!='protocol_hash'})
    if not expected or expected!=actual:raise RuntimeError('LIVE_TRAINING_PROTOCOL_V21.json failed hash verification')
    return p

def readiness(con,protocol):
    rows=con.execute('''SELECT game_id,blue_team,red_team,checkpoint_second,outcome_blue
                        FROM live_training_snapshots_v20 WHERE outcome_blue IS NOT NULL''').fetchall()
    games={r[0] for r in rows};teams={x for r in rows for x in (r[1],r[2]) if x}
    cp={m:len({r[0] for r in rows if int(r[3] or -1)==m*60}) for m in CHECKPOINTS}
    outcomes={r[0]:int(r[4]) for r in rows};blue_rate=sum(outcomes.values())/len(outcomes) if outcomes else None
    gate=protocol['eligibility_gate'];req={int(k):int(v) for k,v in gate['required_checkpoint_maps'].items()}
    checks={'maps':len(games)>=int(gate['min_completed_maps']),'teams':len(teams)>=int(gate['min_teams'])}
    checks.update({f'm{m}':cp[m]>=req[m] for m in CHECKPOINTS})
    lo,hi=gate['blue_win_rate_range'];checks['class_balance']=blue_rate is not None and lo<=blue_rate<=hi
    return {'ready':bool(games) and all(checks.values()),'completed_maps':len(games),'teams':len(teams),'checkpoints':cp,
            'blue_win_rate':blue_rate,'checks':checks,'thresholds':{'maps':gate['min_completed_maps'],'teams':gate['min_teams'],**{f'm{m}':req[m] for m in CHECKPOINTS}}}

def weighted_scaler(rows,features,weights):
    sw=sum(weights);means=[];scales=[]
    for f in features:
        vals=[float(r.get(f) or 0) for r in rows]
        mu=sum(w*x for w,x in zip(weights,vals))/sw
        var=sum(w*(x-mu)**2 for w,x in zip(weights,vals))/sw
        means.append(mu);scales.append(math.sqrt(var) if var>1e-12 else 1.0)
    return means,scales

def transform(rows,features,means,scales):
    return [[1.0]+[(float(r.get(f) or 0)-means[j])/scales[j] for j,f in enumerate(features)] for r in rows]

def solve(A,b):
    n=len(b);M=[list(map(float,A[i]))+[float(b[i])] for i in range(n)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(M[r][col]))
        if abs(M[pivot][col])<1e-10:M[pivot][col]=1e-10
        M[col],M[pivot]=M[pivot],M[col]
        pv=M[col][col]
        for j in range(col,n+1):M[col][j]/=pv
        for r in range(n):
            if r==col:continue
            fac=M[r][col]
            if fac==0:continue
            for j in range(col,n+1):M[r][j]-=fac*M[col][j]
    return [M[i][n] for i in range(n)]

def game_weights(rows):
    counts={}
    for r in rows:counts[r['game_id']]=counts.get(r['game_id'],0)+1
    return [1.0/counts[r['game_id']] for r in rows]

def fit(rows,features,C,max_iter=45):
    w=game_weights(rows);means,scales=weighted_scaler(rows,features,w);X=transform(rows,features,means,scales);y=[int(r['outcome_blue']) for r in rows]
    d=len(features)+1;beta=[0.0]*d;lam=1.0/max(1e-9,float(C))
    for _ in range(max_iter):
        grad=[0.0]*d;H=[[0.0]*d for _ in range(d)]
        for xi,yi,wi in zip(X,y,w):
            p=sigmoid(sum(a*b for a,b in zip(beta,xi)));err=(p-yi)*wi;curv=max(1e-7,p*(1-p))*wi
            for j in range(d):
                grad[j]+=err*xi[j]
                for k in range(j,d):H[j][k]+=curv*xi[j]*xi[k]
        for j in range(1,d):grad[j]+=lam*beta[j];H[j][j]+=lam
        for j in range(d):
            for k in range(j):H[j][k]=H[k][j]
        step=solve(H,grad);mx=max(abs(x) for x in step);beta=[b-s for b,s in zip(beta,step)]
        if mx<1e-6:break
    return {'features':features,'means':means,'scales':scales,'intercept':beta[0],'coef':beta[1:],'C':C,'implementation':'stdlib weighted IRLS L2 logistic'}

def predict(model,rows):
    out=[]
    for r in rows:
        z=model['intercept']
        for j,f in enumerate(model['features']):z+=model['coef'][j]*((float(r.get(f) or 0)-model['means'][j])/model['scales'][j])
        out.append(sigmoid(z))
    return out

def metrics(rows,preds):
    if not rows:return None
    y=[int(r['outcome_blue']) for r in rows];ps=[max(1e-6,min(1-1e-6,float(x))) for x in preds];n=len(y)
    ll=sum(-(yy*math.log(p)+(1-yy)*math.log(1-p)) for yy,p in zip(y,ps))/n
    br=sum((p-yy)**2 for yy,p in zip(y,ps))/n;acc=sum((p>=.5)==bool(yy) for yy,p in zip(y,ps))/n
    ece=0.0
    for i in range(10):
        lo=i/10;hi=(i+1)/10;ix=[j for j,p in enumerate(ps) if p>=lo and (p<hi or (i==9 and p<=hi))]
        if ix:ece+=len(ix)/n*abs(sum(y[j] for j in ix)/len(ix)-sum(ps[j] for j in ix)/len(ix))
    return {'n':n,'log_loss':ll,'brier':br,'accuracy':acc,'ece':ece}

def checkpoint_eval(rows,model=None,baseline=False):
    out={}
    for m in CHECKPOINTS:
        rr=[r for r in rows if int(r['checkpoint_second'])==m*60]
        if not rr:continue
        pp=[float(r['draft_probability_blue']) for r in rr] if baseline else predict(model,rr)
        out[str(m)]=metrics(rr,pp)
    usable=[v for v in out.values() if v]
    macro={k:sum(v[k] for v in usable)/len(usable) for k in ('log_loss','brier','accuracy','ece')} if usable else None
    return {'macro':macro,'checkpoints':out}

def split_games(rows,protocol):
    first={}
    for r in rows:first[r['game_id']]=min(first.get(r['game_id'],r['captured_at']),r['captured_at'])
    order=[g for g,_ in sorted(first.items(),key=lambda x:(x[1],x[0]))];n=len(order)
    trf=protocol['chronological_split']['train'];vaf=protocol['chronological_split']['validation']
    a=max(1,int(n*trf));b=max(a+1,int(n*(trf+vaf)));b=min(b,n-1)
    return order,set(order[:a]),set(order[a:b]),set(order[b:])

def weighted_training_rows(rows,games):return [r for r in rows if r['game_id'] in games]

def bootstrap_delta(test_rows,model,reps=2000,seed=21):
    games=sorted({r['game_id'] for r in test_rows});rng=random.Random(seed);dll=[];dbr=[]
    by={g:[r for r in test_rows if r['game_id']==g] for g in games}
    for _ in range(reps):
        sample=[rng.choice(games) for __ in games];rr=[]
        for g in sample:rr.extend(by[g])
        a=checkpoint_eval(rr,model=model)['macro'];b=checkpoint_eval(rr,baseline=True)['macro']
        if a and b:dll.append(a['log_loss']-b['log_loss']);dbr.append(a['brier']-b['brier'])
    def qs(a):
        a=sorted(a);return {'mean':sum(a)/len(a),'lo':a[int(.025*(len(a)-1))],'hi':a[int(.975*(len(a)-1))]}
    return {'log_loss_delta':qs(dll),'brier_delta':qs(dbr),'reps':len(dll)}

def main():
    ap=argparse.ArgumentParser(description='V21 preregistered live-model trainer. Opens the chronological test set at most once per protocol ID.')
    ap.add_argument('--db',default=str(DB));ap.add_argument('--check-only',action='store_true');args=ap.parse_args()
    protocol=load_protocol();con=sqlite3.connect(args.db);con.row_factory=sqlite3.Row
    ready=readiness(con,protocol);print(json.dumps({'protocol_id':protocol['protocol_id'],'protocol_hash':protocol['protocol_hash'],'readiness':ready},ensure_ascii=False,indent=2))
    if args.check_only:return 0
    if not ready['ready']:
        print('\nTRAINING BLOCKED: preregistered readiness gate not satisfied. Test set remains unopened.');return 2
    prior=con.execute('SELECT run_id,decision FROM live_model_experiments_v21 WHERE protocol_id=? LIMIT 1',(protocol['protocol_id'],)).fetchone()
    if prior:
        print(f'\nTRAINING REFUSED: protocol {protocol["protocol_id"]} already opened the test set in run {prior[0]}. Create a new protocol/epoch for any retuning.');return 4
    rows=[dict(r) for r in con.execute('SELECT * FROM live_training_snapshots_v20 WHERE outcome_blue IS NOT NULL ORDER BY captured_at,game_id,checkpoint_second')]
    order,tr,va,te=split_games(rows,protocol);trrows=weighted_training_rows(rows,tr);varows=weighted_training_rows(rows,va);terows=weighted_training_rows(rows,te)
    sanity=protocol.get('split_sanity') or {}
    for label,rr in [('train',trrows),('validation',varows),('test',terows)]:
        if sanity.get('require_both_outcome_classes_in_each_split') and len({int(x['outcome_blue']) for x in rr})<2:
            print(f'\nTRAINING BLOCKED: {label} split does not contain both outcome classes. Test metrics remain unopened.');return 5
    for minute,minimum in (sanity.get('minimum_test_checkpoint_maps') or {}).items():
        ncp=len({r['game_id'] for r in terows if int(r['checkpoint_second'])==int(minute)*60})
        if ncp<int(minimum):
            print(f'\nTRAINING BLOCKED: test split has only {ncp} maps at {minute} min; requires {minimum}.');return 5
    validation=[]
    for family,features in protocol['families'].items():
        for C in protocol['C_grid']:
            model=fit(trrows,features,C);ev=checkpoint_eval(varows,model=model)
            validation.append({'family':family,'C':C,'metrics':ev['macro']})
    validation.sort(key=lambda x:(x['metrics']['log_loss'],x['metrics']['brier'],x['family'],x['C']))
    chosen=validation[0];features=protocol['families'][chosen['family']];model=fit(weighted_training_rows(rows,tr|va),features,chosen['C'])
    test=checkpoint_eval(terows,model=model);base=checkpoint_eval(terows,baseline=True);boot=bootstrap_delta(terows,model,2000,21)
    dll=test['macro']['log_loss']-base['macro']['log_loss'];dbr=test['macro']['brier']-base['macro']['brier']
    chk_good=0
    for m in ('5','10','15','20'):
        if m in test['checkpoints'] and m in base['checkpoints'] and test['checkpoints'][m]['log_loss']<base['checkpoints'][m]['log_loss']:chk_good+=1
    gate=protocol['promotion_review_gate'];ece_ok=test['macro']['ece']<=base['macro']['ece']+float(gate['max_ece_degradation_vs_draft'])
    ci_ok=boot['log_loss_delta']['hi']<=0 and boot['brier_delta']['hi']<=0
    decision='ELIGIBLE_FOR_REVIEW' if dll<0 and dbr<0 and ci_ok and ece_ok and chk_good>=3 else 'NOT_ELIGIBLE'
    # Hash exact labeled rows used in the experiment.
    dataset_payload=[{k:r.get(k) for k in ['game_id','checkpoint_second','captured_at','outcome_blue']+sorted(set(sum(protocol['families'].values(),[])))} for r in rows]
    dataset_hash=hashlib.sha256(canonical(dataset_payload).encode()).hexdigest()
    test_payload={'candidate':test,'draft_baseline':base,'delta':{'log_loss':dll,'brier':dbr},'checkpoint_log_loss_wins_5_20':chk_good,'ece_ok':ece_ok}
    con.execute('''INSERT INTO live_model_experiments_v21
      (protocol_id,created_at,protocol_hash,dataset_hash,games,snapshots,train_games,validation_games,test_games,selected_family,selected_c,
       validation_json,test_metrics_json,checkpoint_metrics_json,bootstrap_json,model_json,decision,note)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (protocol['protocol_id'],datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol['protocol_hash'],dataset_hash,len(order),len(rows),len(tr),len(va),len(te),chosen['family'],chosen['C'],
       canonical(validation),canonical(test_payload),canonical(test['checkpoints']),canonical(boot),canonical(model),decision,
       'Test set opened once under preregistered V21 protocol. No automatic production promotion.'))
    con.commit();run_id=con.execute('SELECT last_insert_rowid()').fetchone()[0]
    artifact={'run_id':run_id,'protocol_id':protocol['protocol_id'],'protocol_hash':protocol['protocol_hash'],'dataset_hash':dataset_hash,
              'split':{'train_games':len(tr),'validation_games':len(va),'test_games':len(te),'test_first_game':next(iter(sorted(te)),None)},
              'selected':chosen,'test':test_payload,'bootstrap':boot,'decision':decision,'model':model}
    out=ROOT/'governance'/f'LIVE_MODEL_RUN_V21_{run_id}.json';out.write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\n'+json.dumps(artifact,ensure_ascii=False,indent=2));print('\nSaved:',out);return 0

if __name__=='__main__':raise SystemExit(main())
