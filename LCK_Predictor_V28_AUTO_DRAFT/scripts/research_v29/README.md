# research_v29 — backtest das camadas de draft

Scripts da investigação documentada em
[`REVIEW_V29_DRAFT_LAYERS_BACKTEST.md`](../../REVIEW_V29_DRAFT_LAYERS_BACKTEST.md).

**Estes scripts são de pesquisa. Não fazem parte do app e não são importados por
`server.py`.** Nenhuma mudança foi feita no modelo de produção.

## Pré-requisitos

- `runtime\python.exe` (o runtime portátil do projeto) — tem `numpy` instalado.
- Banco `data/lck_data_v1.sqlite` (usado por `backtest.py`, `diag.py`,
  `backtest2.py`, `g2.py`, `apply.py`).
- CSVs do Oracle's Elixir em `data/oracles_elixir/` (usados por `backtest3.py`
  e `ablacao.py`). Anos necessários: **2023, 2024, 2025, 2026**.
  Para apontar para outra pasta: `set OE_DIR=C:\caminho\para\csvs`

Os caminhos são resolvidos a partir da localização do próprio script — não há
caminhos absolutos. Rode de qualquer diretório.

## Ordem de execução

| # | Script | O que faz | Fonte |
|---|---|---|---|
| 1 | `backtest.py` | Backtest v1 walk-forward, só LCK. Baseline = carreira. | sqlite |
| 2 | `diag.py` | Diagnóstico da v1: colinearidade com Elo, features isoladas, bootstrap. | sqlite |
| 3 | `backtest2.py` | Backtest v2: baseline com janela móvel, várias janelas. | sqlite |
| 4 | `backtest3.py` | **Backtest v3 (principal)**: LCK+LPL+LCKC, season 2026. | CSVs |
| 5 | `ablacao.py` | Ablação da v3: qual feature carrega o ganho. | CSVs |
| 6 | `apply.py` | Aplica coeficientes calibrados aos drafts reais de BFX×NS. | sqlite |
| 7 | `g2.py` | Análise por camadas de um draft específico (Game 2 BFX×NS). | sqlite |

Exemplo:

```
runtime\python.exe scripts\research_v29\backtest3.py
```

`backtest3.py` leva ~2-3 min (lê ~300 MB de CSV e roda 4 janelas).

## Resultado principal (v3)

Teste out-of-sample em 1.511 jogos de 2026:

| | log-loss | acurácia |
|---|---|---|
| Só Elo | 0.6542 | 61.9% |
| Elo + draft (janela 30) | 0.6462 | **63.0%** |

Ganho +0.00803, IC 95% [+0.00336, +0.01253] — **significativo**.
Consistente em LCK, LPL e LCKC separadamente.

`x_fit` (jogador × campeão) carrega ~2/3 do ganho.

## Aviso importante

`x_lane` **não mede counter**. Correlaciona +0.45 com a winrate marginal do
campeão — está capturando força de campeão no meta. Ver seção C da ablação.

Não use deltas de draft com escala arbitrária: o coeficiente calibrado de
`x_fit` é ~0.39, e uma estimativa manual anterior com escala 1.0 exagerou o
efeito em ~10×.
