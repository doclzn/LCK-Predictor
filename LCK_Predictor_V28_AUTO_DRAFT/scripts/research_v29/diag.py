# -*- coding: utf-8 -*-
"""Diagnostico: as features de draft tem sinal proprio? Sao colineares com Elo?"""

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import math, json, statistics as st
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

def metrics(P_, Y):
    n = len(Y)
    ll = -sum(math.log(max(p if y else 1-p, 1e-12)) for p, y in zip(P_, Y))/n
    br = sum((p-y)**2 for p, y in zip(P_, Y))/n
    ac = sum(1 for p, y in zip(P_, Y) if (p >= .5) == (y == 1))/n
    return ll, br, ac

TRAIN = [d for d in DATA if d["warm"] and 2021 <= d["year"] <= 2025]
TEST  = [d for d in DATA if d["warm"] and d["year"] == 2026]

def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return num/den if den else 0.0

print("="*80)
print("A) CORRELACAO COM ELO (treino) - detecta colinearidade")
print("="*80)
elo_v = [d["x_elo"] for d in TRAIN]
for f in ("x_fit", "x_side", "x_syn", "x_lane"):
    v = [d[f] for d in TRAIN]
    print(f"  corr({f:7s}, x_elo) = {corr(v, elo_v):+.4f}   corr({f:7s}, y) = {corr(v, [d['y'] for d in TRAIN]):+.4f}")

print()
print("="*80)
print("B) CADA FEATURE SOZINHA (sem Elo) - tem sinal proprio? [teste 2026]")
print("="*80)
Yt = [d["y"] for d in TEST]
for f in ("x_elo", "x_fit", "x_side", "x_syn", "x_lane"):
    X = [[d[f]] for d in TRAIN]; Y = [d["y"] for d in TRAIN]
    w, b = fit_logistic(X, Y)
    Pt = [sig(b + w[0]*d[f]) for d in TEST]
    ll, br, ac = metrics(Pt, Yt)
    print(f"  {f:8s} coef={w[0]:+.3f}  logloss={ll:.4f}  Brier={br:.4f}  acc={ac:5.1%}")

print()
print("="*80)
print("C) COEF NO TREINO vs GANHO NO TESTE (overfit check)")
print("="*80)
for name, feats in [("Elo", ["x_elo"]), ("Elo+todas", ["x_elo","x_fit","x_side","x_syn","x_lane"])]:
    X = [[d[f] for f in feats] for d in TRAIN]; Y = [d["y"] for d in TRAIN]
    w, b = fit_logistic(X, Y)
    Ptr = [sig(b+sum(w[j]*d[f] for j, f in enumerate(feats))) for d in TRAIN]
    Pte = [sig(b+sum(w[j]*d[f] for j, f in enumerate(feats))) for d in TEST]
    lltr, brtr, actr = metrics(Ptr, Y)
    llte, brte, acte = metrics(Pte, Yt)
    print(f"  {name:12s} TREINO ll={lltr:.4f} acc={actr:5.1%} | TESTE ll={llte:.4f} acc={acte:5.1%}")

print()
print("="*80)
print("D) SIDE: a feature esta invertida? winrate azul por ano")
print("="*80)
for yr in range(2021, 2027):
    g = [d for d in DATA if d["year"] == yr]
    if not g: continue
    print(f"  {yr}: n={len(g):4d}  blue_winrate={sum(d['y'] for d in g)/len(g):.3f}  media x_side={st.mean([d['x_side'] for d in g]):+.4f}")

print()
print("="*80)
print("E) TAMANHO DE AMOSTRA DAS FEATURES no teste 2026")
print("="*80)
nz = {f: sum(1 for d in TEST if abs(d[f]) > 1e-9) for f in ("x_fit","x_side","x_syn","x_lane")}
for f, n in nz.items():
    print(f"  {f:8s} nao-nulo em {n}/{len(TEST)} jogos")

print()
print("="*80)
print("F) BOOTSTRAP: o ganho de 'Elo+todas' sobre 'Elo' e significativo?")
print("="*80)
import random
random.seed(7)
featsA = ["x_elo"]; featsB = ["x_elo","x_fit","x_side","x_syn","x_lane"]
XA = [[d[f] for f in featsA] for d in TRAIN]; XB = [[d[f] for f in featsB] for d in TRAIN]
Y = [d["y"] for d in TRAIN]
wA, bA = fit_logistic(XA, Y); wB, bB = fit_logistic(XB, Y)
PA = [sig(bA+sum(wA[j]*d[f] for j, f in enumerate(featsA))) for d in TEST]
PB = [sig(bB+sum(wB[j]*d[f] for j, f in enumerate(featsB))) for d in TEST]
diffs = []
n = len(TEST)
for _ in range(2000):
    idx = [random.randrange(n) for _ in range(n)]
    llA = -sum(math.log(max(PA[i] if Yt[i] else 1-PA[i], 1e-12)) for i in idx)/n
    llB = -sum(math.log(max(PB[i] if Yt[i] else 1-PB[i], 1e-12)) for i in idx)/n
    diffs.append(llA-llB)
diffs.sort()
lo, hi = diffs[int(.025*len(diffs))], diffs[int(.975*len(diffs))]
print(f"  ganho medio em logloss: {st.mean(diffs):+.5f}")
print(f"  IC 95%: [{lo:+.5f}, {hi:+.5f}]   -> {'SIGNIFICATIVO' if lo > 0 else 'NAO significativo (IC cruza zero)'}")
