# -*- coding: utf-8 -*-
"""Aplica o modelo CALIBRADO aos drafts reais de BFX x NS (games 1 e 2)."""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import math, json
exec(open(_os.path.join(_HERE, "backtest.py"), encoding="utf-8").read().split("# ---------------- regressao")[0])

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
        for j in range(k): w[j] -= lr*(gw[j]/n + l2*w[j]/n)
    return w, b

TRAIN = [d for d in DATA if d["warm"] and 2021 <= d["year"] <= 2025]
FE = ["x_elo","x_fit","x_side","x_syn","x_lane"]
W, B = fit_logistic([[d[f] for f in FE] for d in TRAIN], [d["y"] for d in TRAIN])
WE, BE = fit_logistic([[d["x_elo"]] for d in TRAIN], [d["y"] for d in TRAIN])
print("coeficientes calibrados:", {f: round(W[i],4) for i,f in enumerate(FE)}, "b=", round(B,4))
print()

class Fake:
    def __init__(s, p, c, pos, team): s.d = dict(playername=p, champion=c, position=pos, teamname=team)
    def __getitem__(s, k): return s.d[k]

def build(roster, team): return [Fake(p, c, pos, team) for p, c, pos in roster]

GAMES = [
 ("GAME 1", "BNK FEARX", [("Clear","Jayce","top"),("Raptor","Lee Sin","jng"),("VicLa","Galio","mid"),
                          ("Taeyoon","Caitlyn","bot"),("Kellin","Bard","sup")],
            "Nongshim RedForce", [("Kingen","Camille","top"),("Sponge","Jarvan IV","jng"),("Scout","Orianna","mid"),
                          ("Diable","Jhin","bot"),("Lehends","Shen","sup")]),
 ("GAME 2", "Nongshim RedForce", [("Kingen","Ambessa","top"),("Sponge","Nocturne","jng"),("Scout","Locke","mid"),
                          ("Diable","Yunara","bot"),("Lehends","Lulu","sup")],
            "BNK FEARX", [("Clear","Rumble","top"),("Raptor","Vi","jng"),("VicLa","Ahri","mid"),
                          ("Taeyoon","Ezreal","bot"),("Kellin","Karma","sup")]),
]

for label, tb, rb, tr, rr in GAMES:
    blue, red = build(rb, tb), build(rr, tr)
    eb = elo.get(tb, ELO_START); er = elo.get(tr, ELO_START)
    p_elo = 1/(1+10**((er-eb)/400))
    fb, sb, yb = team_features(blue, "Blue")
    fr, sr, yr = team_features(red, "Red")
    lane = lane_feature(blue, red)
    x = dict(x_elo=logit(p_elo), x_fit=fb-fr, x_side=sb-sr, x_syn=yb-yr, x_lane=lane)
    p_full = sig(B + sum(W[i]*x[f] for i, f in enumerate(FE)))
    p_eloc = sig(BE + WE[0]*x["x_elo"])
    print(f"--- {label}: {tb} (azul) x {tr} (verm) ---")
    print(f"  elo: {eb:.1f} x {er:.1f}   features: " + " ".join(f"{f.replace('x_','')}={x[f]:+.3f}" for f in FE))
    print(f"  Elo bruto            : azul {p_elo*100:5.1f}%")
    print(f"  Elo calibrado        : azul {p_eloc*100:5.1f}%")
    print(f"  Modelo completo calib: azul {p_full*100:5.1f}%   (delta vs elo calib: {(p_full-p_eloc)*100:+.2f} p.p.)")
    print()
