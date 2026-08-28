# -*- coding: utf-8 -*-
"""
Backtest v3 - amostra ampliada: LCK + LPL + LCK Challengers, season 2026 (patches 16.x).
Warm-up 2023 | treino 2024-2025 | teste 2026.
Nao toca no banco nem no server.py: le os CSVs do Oracle's Elixir direto.
"""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import csv, math, itertools, os, random, statistics as st
from collections import deque, defaultdict
import numpy as np

csv.field_size_limit(10**7)
BASE = OE_DIR
LEAGUES = {"LCK", "LPL", "LCKC"}
YEARS = (2023, 2024, 2025, 2026)
NEED = ("gameid","date","year","side","position","playername","teamname",
        "champion","result","league","patch")

def logit(p):
    p = min(max(p, 1e-9), 1-1e-9); return math.log(p/(1-p))
def sig(x):
    return 1/(1+math.exp(-max(-60, min(60, x))))

# ---------- carregar ----------
raw = []
for y in YEARS:
    path = os.path.join(BASE, f"{y}_LoL_esports_match_data_from_OraclesElixir.csv")
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["league"] not in LEAGUES: continue
            if r["position"] == "team": continue
            if not r["result"] or not r["champion"]: continue
            raw.append({k: r[k] for k in NEED})
print(f"linhas carregadas: {len(raw)}")

sides = {}
for r in raw:
    sides.setdefault((r["gameid"], r["side"]), []).append(r)
games = {}
for (gid, side), lst in sides.items():
    games.setdefault(gid, {})[side] = lst

ordered = []
for gid, d in games.items():
    if "Blue" not in d or "Red" not in d: continue
    if len(d["Blue"]) != 5 or len(d["Red"]) != 5: continue
    b = d["Blue"][0]
    ordered.append((b["date"], gid, int(b["year"]), b["league"], d["Blue"], d["Red"]))
ordered.sort(key=lambda x: (x[0] or "", x[1]))
print(f"jogos completos: {len(ordered)}")
byyear = defaultdict(int)
for _, _, y, lg, _, _ in ordered: byyear[(y, lg)] += 1
for k in sorted(byyear): print(f"   {k}: {byyear[k]}")

K_CHAMP, K_SYN, K_CC, K_LANE, K_BASE = 8, 6, 10, 8, 20
ELO_K, ELO_START = 24.0, 1350.0

def run(WINDOW):
    elo = {}
    PW = defaultdict(lambda: deque(maxlen=WINDOW))
    Pc, PC, PP, CC, LANE = {}, {}, {}, {}, {}

    def base_of(p):
        if WINDOW:
            dq = PW[p]; n, w = len(dq), sum(dq)
        else:
            n, w = Pc.get(p, (0, 0))
        return (w + K_BASE*0.5)/(n + K_BASE)

    def champ_of(p, c):
        n, w = PC.get((p, c), (0, 0)); b = base_of(p)
        return (w + K_CHAMP*b)/(n + K_CHAMP), b

    def team_feats(lst):
        roster = [(x["playername"], x["champion"]) for x in lst]
        deltas = []
        for p, c in roster:
            cs, b = champ_of(p, c); deltas.append(logit(cs) - logit(b))
        lifts = []
        for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
            n_pp, w_pp = PP.get(tuple(sorted([(p1, c1), (p2, c2)])), (0, 0))
            n_cc, w_cc = CC.get(tuple(sorted([c1, c2])), (0, 0))
            s1, _ = champ_of(p1, c1); s2, _ = champ_of(p2, c2)
            exp = sig((logit(s1)+logit(s2))/2)
            cc = (w_cc + K_CC*0.5)/(n_cc + K_CC)
            prior = sig(logit(exp) + logit(cc) - logit(0.5))
            pp = (w_pp + K_SYN*prior)/(n_pp + K_SYN)
            lifts.append(logit(pp) - logit(exp))
        return sum(deltas)/5.0, sum(lifts)/len(lifts)

    def lane_feat(blue, red):
        bb = {x["position"]: x for x in blue}; rr = {x["position"]: x for x in red}
        v = []
        for pos in ("top","jng","mid","bot","sup"):
            a, b = bb.get(pos), rr.get(pos)
            if not a or not b: continue
            n, w = LANE.get((a["champion"], b["champion"], pos), (0, 0))
            v.append(logit((w + K_LANE*0.5)/(n + K_LANE)))
        return sum(v)/len(v) if v else 0.0

    def bump(d, k, res):
        n, w = d.get(k, (0, 0)); d[k] = (n+1, w+res)

    DATA = []
    for date, gid, year, lg, blue, red in ordered:
        tb, tr = blue[0]["teamname"], red[0]["teamname"]
        eb, er = elo.get(tb, ELO_START), elo.get(tr, ELO_START)
        warm = tb in elo and tr in elo
        p_elo = 1/(1+10**((er-eb)/400))
        fb, yb = team_feats(blue); fr, yr = team_feats(red)
        lane = lane_feat(blue, red)
        y = int(blue[0]["result"])
        DATA.append(dict(year=year, league=lg, y=y, x_elo=logit(p_elo),
                         x_fit=fb-fr, x_syn=yb-yr, x_lane=lane, warm=warm))
        elo[tb] = eb + ELO_K*(y - p_elo); elo[tr] = er + ELO_K*((1-y) - (1-p_elo))
        for lst, res in ((blue, y), (red, 1-y)):
            roster = [(x["playername"], x["champion"]) for x in lst]
            for p, c in roster:
                if WINDOW: PW[p].append(res)
                bump(Pc, p, res); bump(PC, (p, c), res)
            for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
                bump(PP, tuple(sorted([(p1, c1), (p2, c2)])), res)
                bump(CC, tuple(sorted([c1, c2])), res)
        bb = {x["position"]: x for x in blue}; rr = {x["position"]: x for x in red}
        for pos in ("top","jng","mid","bot","sup"):
            a, b = bb.get(pos), rr.get(pos)
            if not a or not b: continue
            bump(LANE, (a["champion"], b["champion"], pos), y)
            bump(LANE, (b["champion"], a["champion"], pos), 1-y)
    return DATA

def fit_np(X, Y, l2=1.0, iters=3000, lr=0.5):
    X = np.asarray(X, float); Y = np.asarray(Y, float)
    X = np.hstack([np.ones((len(X), 1)), X])
    w = np.zeros(X.shape[1]); n = len(X)
    for _ in range(iters):
        g = X.T @ (1/(1+np.exp(-X@w)) - Y)/n
        g[1:] += l2*w[1:]/n
        w -= lr*g
    return w

def pred(w, X):
    X = np.hstack([np.ones((len(X), 1)), np.asarray(X, float)])
    return 1/(1+np.exp(-X@w))

def mets(P, Y):
    P = np.clip(P, 1e-12, 1-1e-12); Y = np.asarray(Y, float)
    return (-(Y*np.log(P)+(1-Y)*np.log(1-P)).mean(),
            ((P-Y)**2).mean(), ((P >= .5) == (Y == 1)).mean())

print("\n" + "="*100)
print(f"{'janela':>10s} {'corr(fit,elo)':>13s} | {'Elo ll':>8s} {'+draft ll':>10s} {'ganho':>9s} | "
      f"{'Elo acc':>8s} {'+draft acc':>11s}")
print("="*100)
STORE = {}
for WINDOW in (None, 50, 30, 20):
    D = run(WINDOW)
    TR = [d for d in D if d["warm"] and 2024 <= d["year"] <= 2025]
    TE = [d for d in D if d["warm"] and d["year"] == 2026]
    Ytr = [d["y"] for d in TR]; Yte = [d["y"] for d in TE]
    c = np.corrcoef([d["x_fit"] for d in TR], [d["x_elo"] for d in TR])[0, 1]
    wA = fit_np([[d["x_elo"]] for d in TR], Ytr)
    PA = pred(wA, [[d["x_elo"]] for d in TE])
    llA, brA, acA = mets(PA, Yte)
    FE = ["x_elo", "x_fit", "x_syn", "x_lane"]
    wB = fit_np([[d[f] for f in FE] for d in TR], Ytr)
    PB = pred(wB, [[d[f] for f in FE] for d in TE])
    llB, brB, acB = mets(PB, Yte)
    lbl = "carreira" if WINDOW is None else f"{WINDOW} jogos"
    print(f"{lbl:>10s} {c:+13.4f} | {llA:8.4f} {llB:10.4f} {llA-llB:+9.5f} | {acA:7.1%} {acB:10.1%}")
    STORE[lbl] = dict(D=D, wA=wA, wB=wB, FE=FE, ll=llB, TR=TR, TE=TE,
                      coefs={f: round(float(wB[i+1]), 4) for i, f in enumerate(FE)},
                      intercept=round(float(wB[0]), 4))

print(f"\nn_treino={len(STORE['carreira']['TR'])}  n_teste={len(STORE['carreira']['TE'])}")
print("\ncoeficientes:")
for lbl, v in STORE.items():
    print(f"  {lbl:>10s}: b={v['intercept']:+.3f}  {v['coefs']}")

best = min(STORE, key=lambda k: STORE[k]["ll"])
print(f"\nmelhor janela: {best}")
v = STORE[best]; TE = v["TE"]; Yte = [d["y"] for d in TE]
PA = pred(v["wA"], [[d["x_elo"]] for d in TE])
PB = pred(v["wB"], [[d[f] for f in v["FE"]] for d in TE])

rng = np.random.default_rng(7); n = len(TE)
Yv = np.asarray(Yte, float)
diffs = []
for _ in range(4000):
    i = rng.integers(0, n, n)
    a = -(Yv[i]*np.log(np.clip(PA[i],1e-12,1))+(1-Yv[i])*np.log(np.clip(1-PA[i],1e-12,1))).mean()
    b = -(Yv[i]*np.log(np.clip(PB[i],1e-12,1))+(1-Yv[i])*np.log(np.clip(1-PB[i],1e-12,1))).mean()
    diffs.append(a-b)
diffs = np.sort(np.array(diffs))
lo, hi = diffs[100], diffs[3899]
print(f"ganho medio logloss = {diffs.mean():+.5f}   IC95% = [{lo:+.5f}, {hi:+.5f}]")
print(f"-> {'SIGNIFICATIVO (IC nao cruza zero)' if lo > 0 else 'NAO significativo (IC cruza zero)'}")
print(f"   fracao de reamostragens com ganho > 0: {(diffs>0).mean():.1%}")

print("\n" + "="*100)
print("QUEBRA POR LIGA (teste 2026, janela vencedora)")
print("="*100)
for lg in ("LCK", "LPL", "LCKC"):
    idx = [i for i, d in enumerate(TE) if d["league"] == lg]
    if not idx: continue
    Ys = [Yte[i] for i in idx]
    llA, brA, acA = mets(PA[idx], Ys); llB, brB, acB = mets(PB[idx], Ys)
    print(f"  {lg:5s} n={len(idx):4d} | Elo ll={llA:.4f} acc={acA:5.1%} | "
          f"+draft ll={llB:.4f} acc={acB:5.1%} | ganho={llA-llB:+.5f}")
