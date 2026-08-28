"""LPL agrega quando o Elo sai de cena?

Testa varios conjuntos de features (com e sem elo_diff), cada um treinado
so com LCK e depois com LCK+LPL, sempre avaliado nos MESMOS jogos de
LCK 2026. Bootstrap pareado por serie.
"""
import os, sys, importlib, sqlite3
import numpy as np
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

sys.path.insert(0, r"c:\Users\pc\OneDrive\Desktop\LCK_Predictor_V28_AUTO_DRAFT (1)\LCK_Predictor_V28_AUTO_DRAFT\scripts")

SPECS = {
    "draft_puro":        ["mastery_diff", "synergy_diff"],
    "draft_pool":        ["mastery_diff", "synergy_diff", "pool_exhaustion_adv"],
    "draft_pool_flex":   ["mastery_diff", "synergy_diff", "pool_exhaustion_adv", "flex_diff"],
    "core_com_elo":      ["elo_diff", "mastery_diff", "synergy_diff"],
}

_cache = {}
def load(train_leagues):
    if train_leagues in _cache:
        return _cache[train_leagues]
    os.environ["MODEL_LEAGUES"] = train_leagues
    os.environ["EVAL_LEAGUES"] = "LCK"
    import run_validation_v19 as V
    importlib.reload(V)
    con = sqlite3.connect(V.DB); con.row_factory = sqlite3.Row
    df = V.build_dataset(con); con.close()
    _cache[train_leagues] = (V, df)
    return V, df


def run(feats, train_leagues):
    V, df = load(train_leagues)
    best, _ = V.tune_2025(df, feats)
    _, pred, met = V.fit_eval(df, feats, best["C"])
    te = df[(df.year == 2026) & V.eval_mask(df)].reset_index(drop=True)
    return te, pred, met


def boot(teA, pA, pB, n=5000):
    y = teA.y.to_numpy(); series = teA.series_key.to_numpy()
    uniq = np.unique(series); idx_by = {s: np.flatnonzero(series == s) for s in uniq}
    rng = np.random.default_rng(19); out = {"log_loss": [], "brier": [], "roc_auc": [], "accuracy": []}
    for _ in range(n):
        idx = np.concatenate([idx_by[s] for s in rng.choice(uniq, size=len(uniq), replace=True)])
        yy = y[idx]
        if len(set(yy)) < 2: continue
        a = np.clip(pA[idx], 1e-6, 1-1e-6); b = np.clip(pB[idx], 1e-6, 1-1e-6)
        out["log_loss"].append(log_loss(yy, b, labels=[0,1]) - log_loss(yy, a, labels=[0,1]))
        out["brier"].append(brier_score_loss(yy, b) - brier_score_loss(yy, a))
        out["roc_auc"].append(roc_auc_score(yy, b) - roc_auc_score(yy, a))
        out["accuracy"].append(np.mean((b >= .5) == yy) - np.mean((a >= .5) == yy))
    return out


for nome, feats in SPECS.items():
    teA, pA, mA = run(feats, "LCK")
    teB, pB, mB = run(feats, "LCK,LPL")
    assert list(teA.gameid) == list(teB.gameid)
    d = boot(teA, pA, pB)
    print(f"\n=== {nome}  [{', '.join(feats)}]")
    print(f"    {'':16s} {'LCK':>9s} {'LCK+LPL':>9s} {'delta':>9s}")
    for k in ("accuracy", "log_loss", "brier", "roc_auc", "calibration_slope"):
        print(f"    {k:16s} {mA[k]:9.4f} {mB[k]:9.4f} {mB[k]-mA[k]:+9.4f}")
    print("    bootstrap (delta = LCK+LPL menos LCK):")
    for k, menor_melhor in (("log_loss", True), ("brier", True), ("roc_auc", False), ("accuracy", False)):
        v = np.asarray(d[k]); lo, hi = np.quantile(v, [.025, .975])
        sig = "SIM" if (hi < 0 or lo > 0) else "nao"
        bom = (v.mean() < 0) if menor_melhor else (v.mean() > 0)
        print(f"      {k:9s} {v.mean():+.5f} IC95=[{lo:+.5f},{hi:+.5f}] sig={sig} "
              f"({'melhora' if bom else 'piora'})")
