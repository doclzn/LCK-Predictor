# -*- coding: utf-8 -*-
"""
Compara o peso de maestria do modelo EM PRODUCAO (draft_model_config_v8) com o
peso calibrado no backtest v3 independente.
Como o modelo de producao usa features padronizadas, a comparacao justa e por
CONTRIBUICAO POR DESVIO-PADRAO: coef * dp(feature).
"""
import os, sys, json, math, sqlite3
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

src = open(os.path.join(HERE, "backtest3.py"), encoding="utf-8").read()
exec(src.split('print("\\n" + "="*100)')[0])

D = run(30)
TR = [d for d in D if d["warm"] and 2024 <= d["year"] <= 2025]
TE = [d for d in D if d["warm"] and d["year"] == 2026]
FE = ["x_elo", "x_fit", "x_syn", "x_lane"]
w = fit_np([[d[f] for f in FE] for d in TR], [d["y"] for d in TR])

print("="*78)
print("MEU BACKTEST v3 (independente, calibrado em 3.610 jogos)")
print("="*78)
contrib = {}
for i, f in enumerate(FE):
    dp = float(np.std([d[f] for d in TR]))
    c = float(w[i+1])
    contrib[f] = abs(c*dp)
    print(f"  {f:8s} coef={c:+.4f}  dp={dp:.4f}  contribuicao(|coef*dp|)={abs(c*dp):.4f}")
r_mine = contrib["x_fit"]/contrib["x_elo"]
print(f"\n  razao maestria/elo = {r_mine:.3f}")

print()
print("="*78)
print("MODELO EM PRODUCAO (draft_model_config_v8)")
print("="*78)
DBP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "data", "lck_data_v1.sqlite")
con2 = sqlite3.connect(DBP); con2.row_factory = sqlite3.Row
cfg = con2.execute("SELECT * FROM draft_model_config_v8").fetchone()
feats = json.loads(cfg["features_json"]); coefs = json.loads(cfg["coef_json"])
print("  (features ja padronizadas -> coef e a propria contribuicao por dp)")
for f, c in zip(feats, coefs):
    print(f"  {f:20s} coef={c:+.4f}")
r_prod = abs(coefs[1])/abs(coefs[0])
print(f"\n  razao maestria/elo = {r_prod:.3f}")

print()
print("="*78)
print("VEREDITO")
print("="*78)
print(f"  producao pesa maestria {r_prod:.2f}x o elo")
print(f"  backtest v3 diz que deveria ser {r_mine:.2f}x o elo")
print(f"  -> maestria esta ~{r_prod/r_mine:.1f}x SOBRE-PONDERADA em producao")
print()
print("  Ressalva: as features nao sao identicas (mastery_eb_diff usa shrinkage")
print("  Beta-Binomial strength=32 sobre carreira; x_fit usa janela movel de 30")
print("  jogos com delta relativo a baseline do jogador). A comparacao e")
print("  indicativa da ORDEM DE GRANDEZA, nao um numero para copiar direto.")
