"""Tres canais liga-agnosticos, testados separadamente:

  1. campeao isolado por role      (Camille top)
  2. dupla de campeoes do mesmo time (Camille top + Jarvan jng)
  3. matchup direto na role         (Camille top vs Ambessa top)

Para cada um: quanta ESCASSEZ existe hoje so com LCK, quanto a LPL alivia,
e se isso vira predicao melhor na LCK 2026. Priors expanding (so passado).
"""
import os, sys, sqlite3
import numpy as np
from itertools import combinations
from collections import defaultdict
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

sys.path.insert(0, r"c:\Users\pc\OneDrive\Desktop\LCK_Predictor_V28_AUTO_DRAFT (1)\LCK_Predictor_V28_AUTO_DRAFT\scripts")
os.environ["MODEL_LEAGUES"]="LCK"; os.environ["EVAL_LEAGUES"]="LCK"
import run_validation_v19 as V

ROLES=('top','jng','mid','bot','sup')
K=10.0   # suavizacao para 0.5


def games_of(leagues):
    """{gameid: (date, {side:{role:champ}}, result_blue)} das ligas dadas."""
    con=sqlite3.connect(V.DB)
    q=("SELECT gameid,date,side,position,champion,result FROM player_games "
       "WHERE position IN ('top','jng','mid','bot','sup') AND champion IS NOT NULL "
       "AND result IS NOT NULL AND league IN ("+",".join("?"*len(leagues))+")")
    g=defaultdict(lambda:{'blue':{}, 'red':{}})
    meta={}
    for gid,d,side,role,ch,res in con.execute(q,tuple(leagues)):
        s=str(side).lower()
        if s not in ('blue','red'): continue
        gid=str(gid); g[gid][s][role]=ch
        if gid not in meta: meta[gid]=[d,None]
        if s=='blue': meta[gid][1]=int(res)
    con.close()
    out={}
    for gid,c in g.items():
        d,y=meta[gid]
        if y is None or len(c['blue'])<5 or len(c['red'])<5: continue
        out[gid]=(d,c,y)
    return out


class Stats:
    def __init__(self):
        self.solo=defaultdict(lambda:[0.0,0.0])
        self.pair=defaultdict(lambda:[0.0,0.0])
        self.mu  =defaultdict(lambda:[0.0,0.0])
    def update(self,c,y):
        for side,win in (('blue',y),('red',1-y)):
            comp=c[side]
            for r in ROLES:
                ch=comp.get(r)
                if ch is None: continue
                s=self.solo[(r,ch)]; s[1]+=1; s[0]+=win
            chs=sorted(comp[r] for r in ROLES if comp.get(r))
            for a,b in combinations(chs,2):
                s=self.pair[(a,b)]; s[1]+=1; s[0]+=win
        for r in ROLES:
            a,b=c['blue'].get(r),c['red'].get(r)
            if a is None or b is None: continue
            s=self.mu[(r,a,b)]; s[1]+=1; s[0]+=y
            s=self.mu[(r,b,a)]; s[1]+=1; s[0]+=1-y
    def sm(self,d,k):
        w,n=d[k] if k in d else (0.0,0.0)
        return (w+K/2)/(n+K), n


def features(df, leagues):
    hist=games_of(leagues)
    order=sorted(hist.items(), key=lambda kv: kv[1][0])
    dates=[v[0] for _,v in order]
    st=Stats(); ptr=0
    cols={k:np.full(len(df),np.nan) for k in ('solo','pair','mu')}
    seen={'pair':[], 'mu':[]}
    target=games_of(["LCK"])
    for i in df.sort_values(["date","gameid"]).index:
        d=df.at[i,"date"]
        while ptr<len(order) and dates[ptr]<d:
            _,(dd,cc,yy)=order[ptr]; st.update(cc,yy); ptr+=1
        t=target.get(str(df.at[i,"gameid"]))
        if not t: continue
        _,c,_=t
        tot={'blue':0.0,'red':0.0}
        for side in ('blue','red'):
            for r in ROLES:
                ch=c[side].get(r)
                if ch: tot[side]+=st.sm(st.solo,(r,ch))[0]
        cols['solo'][i]=tot['blue']-tot['red']
        tot={'blue':0.0,'red':0.0}
        for side in ('blue','red'):
            chs=sorted(c[side][r] for r in ROLES if c[side].get(r))
            vals=[]
            for a,b in combinations(chs,2):
                v,n=st.sm(st.pair,(a,b)); vals.append(v)
                if df.at[i,"year"]==2026: seen['pair'].append(n)
            tot[side]=float(np.mean(vals)) if vals else .5
        cols['pair'][i]=tot['blue']-tot['red']
        acc=0.0
        for r in ROLES:
            a,b=c['blue'].get(r),c['red'].get(r)
            if a is None or b is None: continue
            v,n=st.sm(st.mu,(r,a,b)); acc+=v-.5
            if df.at[i,"year"]==2026: seen['mu'].append(n)
        cols['mu'][i]=acc
    return cols, seen


con=sqlite3.connect(V.DB); con.row_factory=sqlite3.Row
df=V.build_dataset(con); con.close()
print(f"avaliacao: {int((df.year==2026).sum())} jogos de LCK 2026\n")

res={}
for tag,lgs in (("LCK",["LCK"]),("LCK+LPL",["LCK","LPL"])):
    cols,seen=features(df,lgs)
    for k,v in cols.items(): df[f"{k}_{tag}"]=v
    res[tag]=seen
    print(f"--- fonte {tag}")
    for canal,rot in (("pair","duplas de campeoes"),("mu","matchups na role")):
        a=np.asarray(res[tag][canal])
        print(f"    {rot:22s} amostra mediana={np.median(a):5.1f} | "
              f"com 0 jogos={np.mean(a==0)*100:5.1f}% | <5 jogos={np.mean(a<5)*100:5.1f}% | "
              f">=10 jogos={np.mean(a>=10)*100:5.1f}%")

BASE=["elo_diff","mastery_diff","synergy_diff"]
te=df[df.year==2026].reset_index(drop=True)

def ev(f):
    best,_=V.tune_2025(df,f)
    _,p,m=V.fit_eval(df,f,best["C"])
    return p,m

print()
combos={
  "core (hoje)": BASE,
  "core + campeao isolado": ["solo"],
  "core + duplas":          ["pair"],
  "core + matchups":        ["mu"],
  "core + os tres":         ["solo","pair","mu"],
}
preds={}
for nome,extra in combos.items():
    line=f"{nome:26s}"
    for tag in ("LCK","LCK+LPL"):
        f=BASE+[f"{k}_{tag}" for k in extra] if extra!=BASE else BASE
        p,m=ev(f); preds[(nome,tag)]=p
        line+=f"  {tag}: acc={m['accuracy']:.4f} ll={m['log_loss']:.4f} auc={m['roc_auc']:.4f}"
        if extra==BASE: break
    print(line)

y=te.y.to_numpy(); series=te.series_key.to_numpy()
uniq=np.unique(series); idx_by={s:np.flatnonzero(series==s) for s in uniq}
print("\nefeito da LPL em cada canal (bootstrap 5000, delta = LCK+LPL menos LCK):")
for nome in combos:
    if (nome,"LCK+LPL") not in preds: continue
    pA,pB=preds[(nome,"LCK")],preds[(nome,"LCK+LPL")]
    rng=np.random.default_rng(19); dl=[];da=[]
    for _ in range(5000):
        idx=np.concatenate([idx_by[s] for s in rng.choice(uniq,size=len(uniq),replace=True)])
        yy=y[idx]
        if len(set(yy))<2: continue
        a=np.clip(pA[idx],1e-6,1-1e-6); b=np.clip(pB[idx],1e-6,1-1e-6)
        dl.append(log_loss(yy,b,labels=[0,1])-log_loss(yy,a,labels=[0,1]))
        da.append(roc_auc_score(yy,b)-roc_auc_score(yy,a))
    for k,v,menor in (("log_loss",np.asarray(dl),True),("roc_auc",np.asarray(da),False)):
        lo,hi=np.quantile(v,[.025,.975]); sig="SIM" if (hi<0 or lo>0) else "nao"
        bom=(v.mean()<0) if menor else (v.mean()>0)
        print(f"   {nome:24s} {k:9s} {v.mean():+.5f} IC95=[{lo:+.5f},{hi:+.5f}] sig={sig} ({'melhora' if bom else 'piora'})")
