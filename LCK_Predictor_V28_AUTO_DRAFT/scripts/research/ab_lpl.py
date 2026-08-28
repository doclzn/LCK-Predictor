"""Bootstrap pareado: LPL no treino agrega na previsao de LCK?

Treina o modelo `core` nos dois cenarios e compara nos MESMOS jogos de
LCK 2026, reamostrando por serie (nao por jogo) para respeitar a
dependencia entre partidas de uma mesma serie.
"""
import os, sys, importlib, sqlite3
import numpy as np
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

ROOT = r"c:\Users\pc\OneDrive\Desktop\LCK_Predictor_V28_AUTO_DRAFT (1)\LCK_Predictor_V28_AUTO_DRAFT"
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def scenario(train_leagues):
    os.environ["MODEL_LEAGUES"] = train_leagues
    os.environ["EVAL_LEAGUES"] = "LCK"
    import run_validation_v19 as V
    importlib.reload(V)
    con = sqlite3.connect(V.DB); con.row_factory = sqlite3.Row
    df = V.build_dataset(con); con.close()
    feats = V.MODEL_SPECS["core"]
    best, _ = V.tune_2025(df, feats)
    _, pred, met = V.fit_eval(df, feats, best["C"])
    te = df[(df.year == 2026) & V.eval_mask(df)].reset_index(drop=True)
    return te, pred, met, best["C"]


teA, pA, mA, cA = scenario("LCK")
teB, pB, mB, cB = scenario("LCK,LPL")

assert list(teA.gameid) == list(teB.gameid), "conjuntos de avaliacao divergem"
y = teA.y.to_numpy()
series = teA.series_key.to_numpy()
uniq = np.unique(series)
idx_by = {s: np.flatnonzero(series == s) for s in uniq}

rng = np.random.default_rng(19)
d_ll, d_br, d_auc, d_acc = [], [], [], []
for _ in range(5000):
    samp = rng.choice(uniq, size=len(uniq), replace=True)
    idx = np.concatenate([idx_by[s] for s in samp])
    yy = y[idx]
    if len(set(yy)) < 2:
        continue
    a = np.clip(pA[idx], 1e-6, 1 - 1e-6); b = np.clip(pB[idx], 1e-6, 1 - 1e-6)
    d_ll.append(log_loss(yy, b, labels=[0, 1]) - log_loss(yy, a, labels=[0, 1]))
    d_br.append(brier_score_loss(yy, b) - brier_score_loss(yy, a))
    d_auc.append(roc_auc_score(yy, b) - roc_auc_score(yy, a))
    d_acc.append(np.mean((b >= .5) == yy) - np.mean((a >= .5) == yy))


def ci(v, nome, menor_melhor):
    v = np.asarray(v); lo, hi = np.quantile(v, [.025, .975])
    sig = "SIM" if (hi < 0 or lo > 0) else "nao"
    direcao = ("melhora" if v.mean() < 0 else "piora") if menor_melhor else \
              ("melhora" if v.mean() > 0 else "piora")
    print(f"  {nome:10s} delta={v.mean():+.5f}  IC95=[{lo:+.5f},{hi:+.5f}]  "
          f"significativo={sig}  ({direcao} com LPL)")


print(f"\njogos de avaliacao: {len(y)} | series: {len(uniq)}")
print(f"C escolhido: LCK={cA}  LCK+LPL={cB}\n")
for k in ("accuracy", "log_loss", "brier", "roc_auc", "ece", "calibration_slope"):
    print(f"  {k:18s} LCK={mA[k]:.4f}  LCK+LPL={mB[k]:.4f}  delta={mB[k]-mA[k]:+.4f}")
print("\nbootstrap pareado por serie (5000 reamostragens), delta = LCK+LPL menos LCK:")
ci(d_ll, "log_loss", True); ci(d_br, "brier", True)
ci(d_auc, "roc_auc", False); ci(d_acc, "accuracy", False)
