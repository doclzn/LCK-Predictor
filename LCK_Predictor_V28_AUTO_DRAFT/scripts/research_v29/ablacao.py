# -*- coding: utf-8 -*-
"""Ablacao: qual feature carrega o ganho? E x_lane e counter ou forca de campeao?"""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import math, itertools, numpy as np, statistics as st
src = open(_os.path.join(_HERE, "backtest3.py"), encoding="utf-8").read()
exec(src.split('print("\\n" + "="*100)')[0])

D = run(30)
TR = [d for d in D if d["warm"] and 2024 <= d["year"] <= 2025]
TE = [d for d in D if d["warm"] and d["year"] == 2026]
Ytr = [d["y"] for d in TR]; Yte = [d["y"] for d in TE]

def ev(feats):
    w = fit_np([[d[f] for f in feats] for d in TR], Ytr)
    P = pred(w, [[d[f] for f in feats] for d in TE])
    ll, br, ac = mets(P, Yte)
    return ll, ac, w

print("="*88)
print("A) INCREMENTAL - adicionando uma de cada vez")
print("="*88)
prev = None
for feats in (["x_elo"], ["x_elo","x_fit"], ["x_elo","x_fit","x_syn"],
              ["x_elo","x_fit","x_syn","x_lane"]):
    ll, ac, w = ev(feats)
    delta = f"{prev-ll:+.5f}" if prev else "   -   "
    print(f"  {'+'.join(f.replace('x_','') for f in feats):28s} ll={ll:.4f} acc={ac:5.1%} ganho={delta}")
    prev = ll

print()
print("="*88)
print("B) ABLACAO - remove UMA do modelo completo (quanto piora?)")
print("="*88)
FULL = ["x_elo","x_fit","x_syn","x_lane"]
ll_full, ac_full, _ = ev(FULL)
print(f"  completo                     ll={ll_full:.4f} acc={ac_full:5.1%}")
for f in FULL:
    sub = [x for x in FULL if x != f]
    ll, ac, _ = ev(sub)
    print(f"  sem {f:24s} ll={ll:.4f} acc={ac:5.1%}  piora={ll-ll_full:+.5f}")

print()
print("="*88)
print("C) x_lane e 'counter' ou 'forca do campeao no meta'?")
print("="*88)
# x_lane = media de logit(WR do campeao azul CONTRA o vermelho naquela rota).
# Se fosse so forca de campeao, uma versao 'marginal' (WR do campeao contra
# QUALQUER adversario) capturaria o mesmo. Recomputamos com WR marginal.
def run_marginal():
    elo = {}; PW = defaultdict(lambda: deque(maxlen=30))
    PC, CHAMP = {}, {}
    def bump(d,k,res):
        n,w = d.get(k,(0,0)); d[k]=(n+1,w+res)
    OUT=[]
    for date, gid, year, lg, blue, red in ordered:
        tb, tr = blue[0]["teamname"], red[0]["teamname"]
        eb, er = elo.get(tb, ELO_START), elo.get(tr, ELO_START)
        warm = tb in elo and tr in elo
        p_elo = 1/(1+10**((er-eb)/400))
        def marg(lst):
            v=[]
            for x in lst:
                n,w = CHAMP.get((x["champion"], x["position"]),(0,0))
                v.append(logit((w+8*0.5)/(n+8)))
            return sum(v)/len(v)
        y = int(blue[0]["result"])
        OUT.append(dict(year=year, league=lg, y=y, x_elo=logit(p_elo),
                        x_marg=marg(blue)-marg(red), warm=warm))
        elo[tb]=eb+ELO_K*(y-p_elo); elo[tr]=er+ELO_K*((1-y)-(1-p_elo))
        for lst,res in ((blue,y),(red,1-y)):
            for x in lst: bump(CHAMP,(x["champion"],x["position"]),res)
    return OUT
DM = run_marginal()
TRm = [d for d in DM if d["warm"] and 2024<=d["year"]<=2025]
TEm = [d for d in DM if d["warm"] and d["year"]==2026]
Ym = [d["y"] for d in TEm]
wm = fit_np([[d["x_elo"],d["x_marg"]] for d in TRm],[d["y"] for d in TRm])
Pm = pred(wm, [[d["x_elo"],d["x_marg"]] for d in TEm])
llm, brm, acm = mets(Pm, Ym)
wme = fit_np([[d["x_elo"]] for d in TRm],[d["y"] for d in TRm])
Pme = pred(wme, [[d["x_elo"]] for d in TEm])
lle,_,ace = mets(Pme, Ym)
print(f"  Elo                          ll={lle:.4f} acc={ace:5.1%}")
print(f"  Elo + WR marginal do campeao  ll={llm:.4f} acc={acm:5.1%} ganho={lle-llm:+.5f}  coef={wm[2]:+.3f}")
print(f"  Elo + x_lane (matchup direto) ll={ev(['x_elo','x_lane'])[0]:.4f} "
      f"acc={ev(['x_elo','x_lane'])[1]:5.1%} ganho={ev(['x_elo'])[0]-ev(['x_elo','x_lane'])[0]:+.5f}")
print()
c = np.corrcoef([d["x_lane"] for d in TE],[d["x_marg"] for d in TEm])[0,1]
print(f"  corr(x_lane, WR_marginal) = {c:+.4f}")
print("  -> se corr for muito alta, x_lane e majoritariamente forca de campeao, nao counter")

print()
print("="*88)
print("D) COBERTURA dos matchups de rota (quantos ja tinham historico?)")
print("="*88)
print(f"  jogos de teste: {len(TE)}")
v = [abs(d["x_lane"]) for d in TE]
print(f"  x_lane medio abs = {st.mean(v):.4f}  (0 = sem historico nenhum)")
print(f"  jogos com |x_lane| > 0.01: {sum(1 for x in v if x>0.01)}/{len(v)}")
