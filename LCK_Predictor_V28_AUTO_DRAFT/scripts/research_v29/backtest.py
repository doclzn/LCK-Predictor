# -*- coding: utf-8 -*-
"""
Backtest walk-forward das camadas de predicao.
CRITICO: todas as features de um jogo sao calculadas APENAS com jogos anteriores
(acumuladores incrementais), evitando vazamento temporal.
"""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import sqlite3, math, itertools, json, random

# DB definido no header portatil acima
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

def logit(p):
    p = min(max(p, 1e-9), 1-1e-9)
    return math.log(p/(1-p))
def sig(x):
    if x < -60: return 1e-26
    if x >  60: return 1-1e-16
    return 1/(1+math.exp(-x))

# ---------------- carregar e montar jogos ----------------
rows = con.execute("""SELECT gameid, date, year, side, position, playername, teamname,
                             champion, result, golddiffat10, golddiffat15
                      FROM player_games
                      WHERE league='LCK' AND result IS NOT NULL AND champion IS NOT NULL
                      ORDER BY date, gameid""").fetchall()

sides = {}
for r in rows:
    sides.setdefault((r["gameid"], r["side"]), []).append(r)

games = {}
for (gid, side), lst in sides.items():
    games.setdefault(gid, {})[side] = lst

ordered = []
for gid, d in games.items():
    if "Blue" not in d or "Red" not in d: continue
    if len(d["Blue"]) != 5 or len(d["Red"]) != 5: continue
    date = d["Blue"][0]["date"]; year = d["Blue"][0]["year"]
    ordered.append((date, gid, year, d["Blue"], d["Red"]))
ordered.sort(key=lambda x: (x[0] or "", x[1]))
print(f"jogos completos: {len(ordered)}  ({ordered[0][0][:10]} -> {ordered[-1][0][:10]})")

# ---------------- acumuladores (estado = so o passado) ----------------
elo = {}
P  = {}   # player -> [n,w]
PC = {}   # (player,champ) -> [n,w]
PCS= {}   # (player,champ,side) -> [n,w]
PP = {}   # ((p1,c1),(p2,c2)) -> [n,w]
CC = {}   # (c1,c2) -> [n,w]
LANE = {} # (champ_a, champ_b, position) -> [n,w]  matchup direto na rota

K_BASE, K_CHAMP, K_SIDE, K_SYN, K_CC, K_LANE = 20, 8, 6, 6, 10, 8
ELO_K, ELO_START = 24.0, 1350.0

def get(d, k):
    return d.get(k, [0, 0])

def base_of(p):
    n, w = get(P, p)
    return (w + K_BASE*0.5)/(n + K_BASE)

def champ_of(p, c):
    n, w = get(PC, (p, c))
    b = base_of(p)
    return (w + K_CHAMP*b)/(n + K_CHAMP), b, n

def side_of(p, c, s):
    n, w = get(PCS, (p, c, s))
    cs, _, _ = champ_of(p, c)
    return (w + K_SIDE*cs)/(n + K_SIDE), cs, n

def team_features(lst, side):
    deltas, side_deltas = [], []
    roster = [(x["playername"], x["champion"]) for x in lst]
    for p, c in roster:
        cs, b, _ = champ_of(p, c)
        ss, _, _ = side_of(p, c, side)
        deltas.append(logit(cs) - logit(b))
        side_deltas.append(logit(ss) - logit(cs))
    lifts = []
    for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
        key_pp = tuple(sorted([(p1, c1), (p2, c2)]))
        key_cc = tuple(sorted([c1, c2]))
        n_pp, w_pp = get(PP, key_pp)
        n_cc, w_cc = get(CC, key_cc)
        s1, _, _ = champ_of(p1, c1); s2, _, _ = champ_of(p2, c2)
        expected = sig((logit(s1)+logit(s2))/2)
        cc_shrunk = (w_cc + K_CC*0.5)/(n_cc + K_CC)
        prior = sig(logit(expected) + logit(cc_shrunk) - logit(0.5))
        pp_shrunk = (w_pp + K_SYN*prior)/(n_pp + K_SYN)
        lifts.append(logit(pp_shrunk) - logit(expected))
    return (sum(deltas)/5.0, sum(side_deltas)/5.0, sum(lifts)/len(lifts))

def lane_feature(blue, red):
    """matchup direto por rota: winrate do campeao azul contra o vermelho."""
    bym_b = {x["position"]: x for x in blue}
    bym_r = {x["position"]: x for x in red}
    vals = []
    for pos in ("top", "jng", "mid", "bot", "sup"):
        a, b = bym_b.get(pos), bym_r.get(pos)
        if not a or not b: continue
        n, w = get(LANE, (a["champion"], b["champion"], pos))
        sh = (w + K_LANE*0.5)/(n + K_LANE)
        vals.append(logit(sh))
    return sum(vals)/len(vals) if vals else 0.0

def update(blue, red, res_blue, year):
    tb = blue[0]["teamname"]; tr = red[0]["teamname"]
    eb = elo.get(tb, ELO_START); er = elo.get(tr, ELO_START)
    exp_b = 1/(1+10**((er-eb)/400))
    elo[tb] = eb + ELO_K*(res_blue - exp_b)
    elo[tr] = er + ELO_K*((1-res_blue) - (1-exp_b))
    for lst, side, res in ((blue, "Blue", res_blue), (red, "Red", 1-res_blue)):
        roster = [(x["playername"], x["champion"]) for x in lst]
        for p, c in roster:
            for d, k in ((P, p), (PC, (p, c)), (PCS, (p, c, side))):
                cur = d.setdefault(k, [0, 0]); cur[0] += 1; cur[1] += res
        for (p1, c1), (p2, c2) in itertools.combinations(roster, 2):
            for d, k in ((PP, tuple(sorted([(p1, c1), (p2, c2)]))),
                         (CC, tuple(sorted([c1, c2])))):
                cur = d.setdefault(k, [0, 0]); cur[0] += 1; cur[1] += res
    bym_b = {x["position"]: x for x in blue}
    bym_r = {x["position"]: x for x in red}
    for pos in ("top", "jng", "mid", "bot", "sup"):
        a, b = bym_b.get(pos), bym_r.get(pos)
        if not a or not b: continue
        cur = LANE.setdefault((a["champion"], b["champion"], pos), [0, 0])
        cur[0] += 1; cur[1] += res_blue
        cur = LANE.setdefault((b["champion"], a["champion"], pos), [0, 0])
        cur[0] += 1; cur[1] += (1-res_blue)

# ---------------- varredura cronologica ----------------
DATA = []
for date, gid, year, blue, red in ordered:
    tb = blue[0]["teamname"]; tr = red[0]["teamname"]
    eb = elo.get(tb, ELO_START); er = elo.get(tr, ELO_START)
    seen_b = tb in elo; seen_r = tr in elo
    p_elo = 1/(1+10**((er-eb)/400))
    fb, sb, yb = team_features(blue, "Blue")
    fr, sr, yr = team_features(red, "Red")
    lane = lane_feature(blue, red)
    res_blue = blue[0]["result"]
    DATA.append(dict(date=date, gid=gid, year=year, y=res_blue,
                     x_elo=logit(p_elo), x_fit=fb-fr, x_side=sb-sr,
                     x_syn=yb-yr, x_lane=lane, warm=(seen_b and seen_r)))
    update(blue, red, res_blue, year)

print(f"linhas com features: {len(DATA)}")

# ---------------- regressao logistica (L2, gradiente) ----------------
def fit_logistic(X, Y, l2=1.0, iters=4000, lr=0.25):
    k = len(X[0]); w = [0.0]*k; b = 0.0; n = len(X)
    for _ in range(iters):
        gw = [0.0]*k; gb = 0.0
        for xi, yi in zip(X, Y):
            z = b + sum(w[j]*xi[j] for j in range(k))
            e = sig(z) - yi
            gb += e
            for j in range(k): gw[j] += e*xi[j]
        b -= lr*gb/n
        for j in range(k):
            w[j] -= lr*(gw[j]/n + l2*w[j]/n)
    return w, b

def metrics(P_, Y):
    n = len(Y)
    ll = -sum(math.log(max(p if y else 1-p, 1e-12)) for p, y in zip(P_, Y))/n
    br = sum((p-y)**2 for p, y in zip(P_, Y))/n
    ac = sum(1 for p, y in zip(P_, Y) if (p >= .5) == (y == 1))/n
    return ll, br, ac

TRAIN = [d for d in DATA if d["warm"] and 2021 <= d["year"] <= 2025]
TEST  = [d for d in DATA if d["warm"] and d["year"] == 2026]
print(f"\ntreino: {len(TRAIN)} jogos (2021-2025) | teste: {len(TEST)} jogos (2026)")

FEATSETS = [
    ("1) Elo",                 ["x_elo"]),
    ("2) Elo+fit",             ["x_elo", "x_fit"]),
    ("3) Elo+fit+side",        ["x_elo", "x_fit", "x_side"]),
    ("4) Elo+fit+side+syn",    ["x_elo", "x_fit", "x_side", "x_syn"]),
    ("5) +lane(counter)",      ["x_elo", "x_fit", "x_side", "x_syn", "x_lane"]),
]

print("\n" + "="*92)
print(f"{'modelo':24s} {'logloss':>9s} {'Brier':>8s} {'acc':>7s} | coeficientes")
print("="*92)

ybar = sum(d["y"] for d in TRAIN)/len(TRAIN)
base_p = [ybar]*len(TEST)
ll, br, ac = metrics(base_p, [d["y"] for d in TEST])
print(f"{'0) base (blue rate)':24s} {ll:9.4f} {br:8.4f} {ac:6.1%} | p={ybar:.4f}")

results = {}
for name, feats in FEATSETS:
    X = [[d[f] for f in feats] for d in TRAIN]
    Y = [d["y"] for d in TRAIN]
    w, b = fit_logistic(X, Y)
    Xt = [[d[f] for f in feats] for d in TEST]
    Yt = [d["y"] for d in TEST]
    Pt = [sig(b + sum(w[j]*xi[j] for j in range(len(w)))) for xi in Xt]
    ll, br, ac = metrics(Pt, Yt)
    coef = "  ".join(f"{f.replace('x_',''):}={w[j]:+.3f}" for j, f in enumerate(feats))
    print(f"{name:24s} {ll:9.4f} {br:8.4f} {ac:6.1%} | b={b:+.3f}  {coef}")
    results[name] = dict(w=w, b=b, feats=feats, ll=ll, br=br, ac=ac)

json.dump({k: dict(w=v["w"], b=v["b"], feats=v["feats"]) for k, v in results.items()},
          open(_os.path.join(_HERE, "coefs.json"), "w"))

# ---------------- diagnostico das features ----------------
print("\n" + "="*92)
print("DIAGNOSTICO (conjunto de teste 2026)")
print("="*92)
import statistics as st
for f in ("x_elo", "x_fit", "x_side", "x_syn", "x_lane"):
    v = [d[f] for d in TEST]
    ones = [d[f] for d in TEST if d["y"] == 1]
    zeros = [d[f] for d in TEST if d["y"] == 0]
    sep = st.mean(ones) - st.mean(zeros)
    print(f"{f:8s} media={st.mean(v):+.4f} dp={st.pstdev(v):.4f}  separacao(vit-der)={sep:+.4f}")
