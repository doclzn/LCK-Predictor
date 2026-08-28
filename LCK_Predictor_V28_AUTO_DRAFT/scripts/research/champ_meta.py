"""A LPL melhora a estimativa de forca de CAMPEAO (unica quantidade
comparavel entre ligas)?

Constroi champ_meta_diff: para cada jogo, a soma do winrate suavizado dos
5 campeoes de cada lado (por role), estimado SO com jogos anteriores aquela
data (expanding, sem leakage). A fonte desse prior varia: so LCK, ou
LCK+LPL. O resto do modelo e identico e a avaliacao e sempre em LCK 2026.
"""
import os, sys, sqlite3, importlib
import numpy as np
from collections import defaultdict
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

sys.path.insert(0, r"c:\Users\pc\OneDrive\Desktop\LCK_Predictor_V28_AUTO_DRAFT (1)\LCK_Predictor_V28_AUTO_DRAFT\scripts")
os.environ["MODEL_LEAGUES"] = "LCK"; os.environ["EVAL_LEAGUES"] = "LCK"
import run_validation_v19 as V

DB = V.DB
PRIOR_N = 10.0   # forca da suavizacao para 0.5, igual ao (w+5)/(n+10) do app


def champ_history(leagues):
    """Jogos (data, role, champion, result) das ligas dadas, em ordem."""
    con = sqlite3.connect(DB)
    q = ("SELECT date, position AS role, champion, result FROM player_games "
         "WHERE position IN ('top','jng','mid','bot','sup') AND champion IS NOT NULL "
         "AND result IS NOT NULL AND league IN (" + ",".join("?"*len(leagues)) + ") "
         "ORDER BY date")
    rows = con.execute(q, tuple(leagues)).fetchall()
    con.close()
    return rows


def build_feature(df, leagues):
    """champ_meta_diff por jogo, usando so o passado como fonte do prior."""
    hist = champ_history(leagues)
    # eventos ordenados por data; vamos avancar um ponteiro conforme os jogos
    ev_date = [h[0] for h in hist]
    stat = defaultdict(lambda: [0.0, 0.0])   # (role,champ) -> [wins, games]
    ptr = 0

    con = sqlite3.connect(DB)
    comp = {}
    for gid, side, role, champ in con.execute(
        "SELECT gameid, side, position, champion FROM player_games "
        "WHERE position IN ('top','jng','mid','bot','sup') AND champion IS NOT NULL"):
        comp.setdefault(str(gid), []).append((str(side).lower(), role, champ))
    con.close()

    out = np.full(len(df), np.nan)
    order = df.sort_values(["date", "gameid"]).index
    for i in order:
        d = df.at[i, "date"]
        while ptr < len(hist) and ev_date[ptr] < d:      # so o passado estrito
            _, role, champ, res = hist[ptr]
            s = stat[(role, champ)]
            s[1] += 1; s[0] += 1 if res else 0
            ptr += 1
        parts = comp.get(str(df.at[i, "gameid"]))
        if not parts:
            continue
        tot = {"blue": 0.0, "red": 0.0}
        for side, role, champ in parts:
            if side not in tot:
                continue
            w, n = stat[(role, champ)]
            tot[side] += (w + PRIOR_N/2) / (n + PRIOR_N)   # suavizado para 0.5
        out[i] = tot["blue"] - tot["red"]
    return out


con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
df = V.build_dataset(con); con.close()      # dataset SEMPRE so LCK
print(f"dataset LCK: {len(df)} jogos | avaliacao 2026: {int((df.year==2026).sum())}")

df["cm_lck"] = build_feature(df, ["LCK"])
df["cm_both"] = build_feature(df, ["LCK", "LPL"])
print("cobertura cm_lck=%.3f cm_both=%.3f  correlacao=%.4f" % (
    df.cm_lck.notna().mean(), df.cm_both.notna().mean(),
    df[["cm_lck", "cm_both"]].corr().iloc[0, 1]))


def evaluate(feats):
    best, _ = V.tune_2025(df, feats)
    _, pred, met = V.fit_eval(df, feats, best["C"])
    return pred, met

te = df[df.year == 2026].reset_index(drop=True)
BASE = ["elo_diff", "mastery_diff", "synergy_diff"]
runs = {
    "core (sem meta de campeao)": BASE,
    "core + meta de campeao  [fonte: LCK]":      BASE + ["cm_lck"],
    "core + meta de campeao  [fonte: LCK+LPL]":  BASE + ["cm_both"],
    "so meta de campeao      [fonte: LCK]":      ["cm_lck"],
    "so meta de campeao      [fonte: LCK+LPL]":  ["cm_both"],
}
res = {}
for nome, f in runs.items():
    res[nome] = evaluate(f)
    m = res[nome][1]
    print(f"\n{nome}")
    print(f"   acc={m['accuracy']:.4f}  ll={m['log_loss']:.4f}  brier={m['brier']:.4f}  auc={m['roc_auc']:.4f}")

# bootstrap: fonte LCK+LPL contra fonte LCK, dentro do core
y = te.y.to_numpy(); series = te.series_key.to_numpy()
uniq = np.unique(series); idx_by = {s: np.flatnonzero(series == s) for s in uniq}
pA = res["core + meta de campeao  [fonte: LCK]"][0]
pB = res["core + meta de campeao  [fonte: LCK+LPL]"][0]
rng = np.random.default_rng(19); acc = defaultdict(list)
for _ in range(5000):
    idx = np.concatenate([idx_by[s] for s in rng.choice(uniq, size=len(uniq), replace=True)])
    yy = y[idx]
    if len(set(yy)) < 2: continue
    a = np.clip(pA[idx], 1e-6, 1-1e-6); b = np.clip(pB[idx], 1e-6, 1-1e-6)
    acc["log_loss"].append(log_loss(yy, b, labels=[0,1]) - log_loss(yy, a, labels=[0,1]))
    acc["brier"].append(brier_score_loss(yy, b) - brier_score_loss(yy, a))
    acc["roc_auc"].append(roc_auc_score(yy, b) - roc_auc_score(yy, a))
    acc["accuracy"].append(np.mean((b >= .5) == yy) - np.mean((a >= .5) == yy))
print("\nbootstrap  (delta = fonte LCK+LPL menos fonte LCK, mesmo modelo):")
for k, menor in (("log_loss", True), ("brier", True), ("roc_auc", False), ("accuracy", False)):
    v = np.asarray(acc[k]); lo, hi = np.quantile(v, [.025, .975])
    sig = "SIM" if (hi < 0 or lo > 0) else "nao"
    bom = (v.mean() < 0) if menor else (v.mean() > 0)
    print(f"   {k:9s} {v.mean():+.5f} IC95=[{lo:+.5f},{hi:+.5f}] sig={sig} ({'melhora' if bom else 'piora'})")
