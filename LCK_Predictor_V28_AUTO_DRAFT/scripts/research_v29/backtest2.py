# -*- coding: utf-8 -*-
"""
Backtest v2: baseline do jogador com JANELA MOVEL (ultimos N jogos) em vez de
carreira inteira, para tornar x_fit ortogonal ao Elo.
Testa varias janelas + remove x_side per-jogador.
"""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import sqlite3, math, itertools, json, random, statistics as st
from collections import deque, defaultdict

# DB definido no header portatil acima
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row

def logit(p):
    p = min(max(p, 1e-9), 1-1e-9); return math.log(p/(1-p))
def sig(x):
    if x < -60: return 1e-26
    if x > 60: return 1-1e-16
    return 1/(1+math.exp(-x))

rows = con.execute("""SELECT gameid, date, year, side, position, playername, teamname,
                             champion, result
                      FROM player_games
                      WHERE league='LCK' AND result IS NOT NULL AND champion IS NOT NULL
                      ORDER BY date, gameid""").fetchall()
sides = {}
for r in rows: sides.setdefault((r["gameid"], r["side"]), []).append(r)
games = {}
for (gid, side), lst in sides.items(): games.setdefault(gid, {})[side] = lst
ordered = []
for gid, d in games.items():
    if "Blue" in d and "Red" in d and len(d["Blue"]) == 5 and len(d["Red"]) == 5:
        ordered.append((d["Blue"][0]["date"], gid, d["Blue"][0]["year"], d["Blue"], d["Red"]))
ordered.sort(key=lambda x: (x[0] or "", x[1]))

K_CHAMP, K_SYN, K_CC, K_LANE = 8, 6, 10, 8
ELO_K, ELO_START = 24.0, 1350.0

def run(WINDOW):
    """WINDOW=None -> baseline de carreira (v1). Caso contrario, janela movel."""
    elo = {}
    PW = defaultdict(lambda: deque(maxlen=WINDOW) if WINDOW else None)
    Pc = {}   # carreira: player -> [n,w]
    PC, PCS, PP, CC, LANE = {}, {}, {}, {}, {}

    def base_of(p):
        if WINDOW:
            dq = PW[p]
            n, w = len(dq), sum(dq)
            return (w + 20*0.5)/(n + 20)
        n, w = Pc.get(p, [0, 0])
        return (w + 20*0.5)/(n + 20)

    def champ_of(p, c):
        n, w = PC.get((p, c), [0, 0]); b = base_of(p)
        return (w + K_CHAMP*b)/(n + K_CHAMP), b

    def team_features(lst, side):
        roster = [(x["playername"], x["champion"]) for x in lst]
        deltas = []
        for p, c in roster:
            cs, b = champ_of(p, c); deltas.append(logit(cs) - logit(b))
        lifts = []
        for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
            n_pp, w_pp = PP.get(tuple(sorted([(p1, c1), (p2, c2)])), [0, 0])
            n_cc, w_cc = CC.get(tuple(sorted([c1, c2])), [0, 0])
            s1, _ = champ_of(p1, c1); s2, _ = champ_of(p2, c2)
            expected = sig((logit(s1)+logit(s2))/2)
            cc_sh = (w_cc + K_CC*0.5)/(n_cc + K_CC)
            prior = sig(logit(expected) + logit(cc_sh) - logit(0.5))
            pp_sh = (w_pp + K_SYN*prior)/(n_pp + K_SYN)
            lifts.append(logit(pp_sh) - logit(expected))
        return sum(deltas)/5.0, sum(lifts)/len(lifts)

    def lane_feature(blue, red):
        bb = {x["position"]: x for x in blue}; rr_ = {x["position"]: x for x in red}
        vals = []
        for pos in ("top", "jng", "mid", "bot", "sup"):
            a, b = bb.get(pos), rr_.get(pos)
            if not a or not b: continue
            n, w = LANE.get((a["champion"], b["champion"], pos), [0, 0])
            vals.append(logit((w + K_LANE*0.5)/(n + K_LANE)))
        return sum(vals)/len(vals) if vals else 0.0

    DATA = []
    for date, gid, year, blue, red in ordered:
        tb, tr = blue[0]["teamname"], red[0]["teamname"]
        eb, er = elo.get(tb, ELO_START), elo.get(tr, ELO_START)
        warm = tb in elo and tr in elo
        p_elo = 1/(1+10**((er-eb)/400))
        fb, yb = team_features(blue, "Blue"); fr, yr = team_features(red, "Red")
        lane = lane_feature(blue, red)
        y = blue[0]["result"]
        DATA.append(dict(year=year, y=y, x_elo=logit(p_elo), x_fit=fb-fr,
                         x_syn=yb-yr, x_lane=lane, warm=warm))
        # update
        exp_b = 1/(1+10**((er-eb)/400))
        elo[tb] = eb + ELO_K*(y - exp_b); elo[tr] = er + ELO_K*((1-y)-(1-exp_b))
        for lst, side, res in ((blue, "Blue", y), (red, "Red", 1-y)):
            roster = [(x["playername"], x["champion"]) for x in lst]
            for p, c in roster:
                if WINDOW: PW[p].append(res)
                cur = Pc.setdefault(p, [0, 0]); cur[0] += 1; cur[1] += res
                for d, k in ((PC, (p, c)), (PCS, (p, c, side))):
                    cc = d.setdefault(k, [0, 0]); cc[0] += 1; cc[1] += res
            for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
                for d, k in ((PP, tuple(sorted([(p1, c1), (p2, c2)]))), (CC, tuple(sorted([c1, c2])))):
                    cc = d.setdefault(k, [0, 0]); cc[0] += 1; cc[1] += res
        bb = {x["position"]: x for x in blue}; rr_ = {x["position"]: x for x in red}
        for pos in ("top", "jng", "mid", "bot", "sup"):
            a, b = bb.get(pos), rr_.get(pos)
            if not a or not b: continue
            for k, v in (((a["champion"], b["champion"], pos), y), ((b["champion"], a["champion"], pos), 1-y)):
                cc = LANE.setdefault(k, [0, 0]); cc[0] += 1; cc[1] += v
    return DATA

def fit_logistic(X, Y, l2=1.0, iters=4000, lr=0.25):
    k = len(X[0]); w = [0.0]*k; b = 0.0; n = len(X)
    for _ in range(iters):
        gw = [0.0]*k; gb = 0.0
        for xi, yi in zip(X, Y):
            z = b + sum(w[j]*xi[j] for j in range(k)); e = sig(z)-yi
            gb += e
            for j in range(k): gw[j] += e*xi[j]
        b -= lr*gb/n
        for j in range(k): w[j] -= lr*(gw[j]/n + l2*w[j]/n)
    return w, b

def metrics(P_, Y):
    n = len(Y)
    ll = -sum(math.log(max(p if y else 1-p, 1e-12)) for p, y in zip(P_, Y))/n
    br = sum((p-y)**2 for p, y in zip(P_, Y))/n
    ac = sum(1 for p, y in zip(P_, Y) if (p >= .5) == (y == 1))/n
    return ll, br, ac

def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return num/den if den else 0.0

print("="*94)
print(f"{'janela':>10s} {'corr(fit,elo)':>14s} | {'Elo ll':>8s} {'Elo+fit+syn+lane ll':>20s} {'ganho':>9s} {'acc':>7s}")
print("="*94)
BEST = {}
for WINDOW in (None, 50, 30, 20, 10):
    D = run(WINDOW)
    TR = [d for d in D if d["warm"] and 2021 <= d["year"] <= 2025]
    TE = [d for d in D if d["warm"] and d["year"] == 2026]
    c = corr([d["x_fit"] for d in TR], [d["x_elo"] for d in TR])
    Ytr = [d["y"] for d in TR]; Yte = [d["y"] for d in TE]
    wA, bA = fit_logistic([[d["x_elo"]] for d in TR], Ytr)
    PA = [sig(bA + wA[0]*d["x_elo"]) for d in TE]
    llA, brA, acA = metrics(PA, Yte)
    FE = ["x_elo", "x_fit", "x_syn", "x_lane"]
    wB, bB = fit_logistic([[d[f] for f in FE] for d in TR], Ytr)
    PB = [sig(bB + sum(wB[j]*d[f] for j, f in enumerate(FE))) for d in TE]
    llB, brB, acB = metrics(PB, Yte)
    lbl = "carreira" if WINDOW is None else f"{WINDOW} jogos"
    print(f"{lbl:>10s} {c:+14.4f} | {llA:8.4f} {llB:20.4f} {llA-llB:+9.5f} {acB:6.1%}")
    BEST[lbl] = dict(D=D, w=wB, b=bB, FE=FE, ll=llB, llA=llA, corr=c,
                     coefs={f: round(wB[i], 4) for i, f in enumerate(FE)})

print()
for lbl, v in BEST.items():
    print(f"  {lbl:>10s}: {v['coefs']}")

# bootstrap na melhor janela
best_lbl = min(BEST, key=lambda k: BEST[k]["ll"])
print(f"\nmelhor janela: {best_lbl}")
v = BEST[best_lbl]
TE = [d for d in v["D"] if d["warm"] and d["year"] == 2026]
TR = [d for d in v["D"] if d["warm"] and 2021 <= d["year"] <= 2025]
Yte = [d["y"] for d in TE]
wA, bA = fit_logistic([[d["x_elo"]] for d in TR], [d["y"] for d in TR])
PA = [sig(bA + wA[0]*d["x_elo"]) for d in TE]
PB = [sig(v["b"] + sum(v["w"][j]*d[f] for j, f in enumerate(v["FE"]))) for d in TE]
random.seed(7); n = len(TE); diffs = []
for _ in range(2000):
    idx = [random.randrange(n) for _ in range(n)]
    llA = -sum(math.log(max(PA[i] if Yte[i] else 1-PA[i], 1e-12)) for i in idx)/n
    llB = -sum(math.log(max(PB[i] if Yte[i] else 1-PB[i], 1e-12)) for i in idx)/n
    diffs.append(llA-llB)
diffs.sort()
lo, hi = diffs[50], diffs[1949]
print(f"ganho medio logloss={st.mean(diffs):+.5f}  IC95%=[{lo:+.5f},{hi:+.5f}]  -> "
      f"{'SIGNIFICATIVO' if lo > 0 else 'NAO significativo'}")
