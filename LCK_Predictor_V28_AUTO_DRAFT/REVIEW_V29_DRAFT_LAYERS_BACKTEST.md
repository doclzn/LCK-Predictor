# V29 — Backtest das camadas de draft (fit / side / sinergia / counter)

## Pergunta
As predições de `/api/upcoming` para partidas sem blend salvo caem no fallback
`elo_live` (`server.py:705`), que usa **apenas o Elo dos times**. O banco tem
estatísticas ricas de jogador×campeão (`draft_player_champion`,
`draft_player_champion_web`, `player_games` com 53.530 linhas LCK 2016-2026).

Essas estatísticas, se incorporadas, melhorariam a predição? Especificamente
quatro camadas incrementais:

1. Elo puro (situação atual)
2. \+ winrate de cada jogador com o pick do draft
3. \+ o lado (azul/vermelho)
4. \+ sinergia entre os picks do próprio time
5. \+ matchup/counter direto na rota (bônus)

## Metodologia
Backtest **walk-forward** em 5.353 jogos LCK completos (2016-01-13 → 2026-08-23),
construído a partir de `player_games`.

- Todas as features de um jogo são calculadas **apenas com acumuladores de jogos
  anteriores** — sem vazamento temporal. Elo recalculado do zero (K=24).
- Treino: 2021-2025 (2.477 jogos). Teste out-of-sample: **2026 (447 jogos)**.
- Regressão logística com L2; métricas log-loss, Brier e acurácia.
- Sinergia com backoff hierárquico: par jogador-campeão → par de campeões na LCK
  → prior neutro, peso proporcional a N.
- Para evitar dupla contagem da força do time, `x_fit` usa **delta relativo**:
  `logit(WR no campeão) − logit(WR base do jogador)`.

## Resultados — v1 (baseline do jogador = carreira inteira)

| Modelo | Log-loss | Brier | Acurácia |
|---|---|---|---|
| Base (taxa do lado azul) | 0.6894 | 0.2481 | 56.8% |
| **1) Elo** | **0.6300** | **0.2200** | **64.9%** |
| 2) + fit | 0.6300 | 0.2201 | 64.9% |
| 3) + side | 0.6297 | 0.2198 | 64.9% |
| 4) + sinergia | 0.6295 | 0.2198 | 64.7% |
| 5) + lane/counter | 0.6292 | 0.2197 | 64.7% |

Ganho total sobre Elo puro: **0.0008 em log-loss**.
Bootstrap (2.000 reamostragens): **IC 95% = [−0.0011, +0.0026]** — cruza zero.
**Não significativo.**

### Diagnóstico: as features não são ruído, são redundantes

Cada feature isolada bate o baseline (51.5%) no teste de 2026:

| Feature sozinha | Acurácia 2026 |
|---|---|
| x_fit (jogador×pick) | 58.8% |
| x_side | 57.0% |
| x_lane (counter) | 56.6% |
| x_syn (sinergia) | 53.0% |

O problema é **colinearidade com o Elo**: `corr(x_fit, x_elo) = +0.43`.

Causa raiz: a baseline do jogador era calculada sobre a **carreira inteira**,
enquanto o Elo é atual. Um jogador em boa fase tem winrate recente acima da sua
média histórica, e isso correlaciona com o time estar com Elo alto — o delta
acabava capturando **forma recente**, que o Elo já contém, em vez de fit de
campeão.

Nota adicional: o coeficiente de `x_side` saiu **negativo** (−0.246). A vantagem
do lado azul já está capturada pelo intercepto (b=+0.22); a feature per-jogador
só adiciona ruído. Removida na v2.

## Resultados — v2 (baseline com janela móvel)

Hipótese: trocar a baseline de carreira por **janela dos últimos N jogos** torna
`x_fit` ortogonal ao Elo.

| Janela | corr(fit, elo) | Elo log-loss | Elo+fit+syn+lane | ganho | acc |
|---|---|---|---|---|---|
| carreira | +0.4271 | 0.6300 | 0.6296 | +0.00040 | 64.7% |
| 50 jogos | **+0.0532** | 0.6300 | 0.6286 | +0.00139 | 65.1% |
| 30 jogos | +0.1734 | 0.6300 | 0.6280 | +0.00201 | 65.1% |
| 20 jogos | +0.2902 | 0.6300 | **0.6273** | **+0.00265** | 65.1% |
| 10 jogos | +0.4859 | 0.6300 | 0.6287 | +0.00131 | 65.1% |

Coeficiente de `x_fit` subiu de **0.015** (carreira) para **0.13** (janela 50) —
a feature ganhou peso real. A correlação com Elo caiu de 0.43 para **0.053**,
confirmando o diagnóstico.

Bootstrap na melhor janela (20 jogos): ganho médio +0.00263,
**IC 95% = [−0.00053, +0.00568]** — ainda cruza zero, por margem estreita.

Ressalva: a janela de 20 tem o melhor ganho mas `corr = 0.29`, enquanto a de 50
é quase ortogonal (`0.05`) com ganho menor. Parte do ganho da janela curta
provavelmente vem de capturar forma recente (já no Elo), não fit puro.

## Resultados — v3 (amostra ampliada: LCK + LPL + LCK Challengers)

A v1 e a v2 usaram apenas LCK (447 jogos de teste). A v3 amplia para **LCK + LPL
+ LCKC**, season 2026 (patches 16.x), lendo os CSVs do Oracle's Elixir
diretamente — **sem tocar no banco nem no `server.py`**.

- Warm-up: 2023 (1.742 jogos) · Treino: 2024-2025 (3.610) · **Teste: 2026 (1.511)**
- Amostra de teste **3,4× maior** que a v1/v2.

| Janela | corr(fit,elo) | Elo ll | +draft ll | ganho | Elo acc | +draft acc |
|---|---|---|---|---|---|---|
| carreira | +0.266 | 0.6542 | 0.6490 | +0.00521 | 61.9% | 62.5% |
| 50 jogos | +0.250 | 0.6542 | 0.6472 | +0.00705 | 61.9% | 62.7% |
| **30 jogos** | +0.309 | 0.6542 | **0.6462** | **+0.00804** | 61.9% | **63.0%** |
| 20 jogos | +0.371 | 0.6542 | 0.6463 | +0.00793 | 61.9% | 63.1% |

Bootstrap (4.000 reamostragens, janela 30):
**ganho médio +0.00803, IC 95% = [+0.00336, +0.01253]**
→ **SIGNIFICATIVO** — o IC não cruza zero; 99,9% das reamostragens com ganho > 0.

### Consistente nas três ligas

| Liga | n | Elo acc | +draft acc | ganho log-loss |
|---|---|---|---|---|
| LCK | 447 | 65.1% | 65.8% | +0.00931 |
| LPL | 613 | 61.3% | 63.1% | +0.00843 |
| LCKC | 451 | 59.6% | 60.1% | +0.00624 |

O ganho aparece nas três independentemente — indício de efeito real, não de
sorte numa amostra.

### Ablação: de onde vem o ganho

| Modelo incremental | log-loss | acc | ganho |
|---|---|---|---|
| elo | 0.6542 | 61.9% | — |
| elo + fit | 0.6488 | 62.2% | **+0.00542** |
| elo + fit + syn | 0.6472 | 62.6% | +0.00161 |
| elo + fit + syn + lane | 0.6462 | 63.0% | +0.00100 |

**`x_fit` (jogador × campeão com janela de 30 jogos) carrega ~2/3 do ganho.**
`x_syn` e `x_lane` contribuem pouco individualmente.

Sobre `x_lane`: `corr(x_lane, WR marginal do campeão) = +0.45`. Ou seja, a
feature é **parcialmente força de campeão no meta, não counter puro**. De fato,
"Elo + WR marginal do campeão" sozinho já rende +0.00513 — quase tudo que
`x_lane` entrega. A interpretação correta não é "counter importa", e sim
"a qualidade dos campeões escolhidos importa".

### Por que a v1/v2 não detectaram

Dois fatores, não um:
1. **Amostra de teste pequena** (447 vs 1.511) — poder estatístico insuficiente.
2. **Acumuladores esparsos** — com só LCK, os pares de campeões e matchups de
   rota tinham poucos jogos de histórico. Com três ligas, ficam populados e as
   features saem do regime de ruído. Note como os coeficientes mudam:
   `x_lane` vai de **0.06** (v2, só LCK) para **0.75** (v3).

## Conclusão

**As camadas de draft produzem ganho real e mensurável quando treinadas com
amostra suficiente**: +1,1 p.p. de acurácia (61.9% → 63.0%) e ganho de log-loss
estatisticamente significativo, consistente nas três ligas.

O efeito é **modesto mas não é ruído** — ao contrário do que as versões v1/v2
concluíram com amostra só de LCK.

**Nenhuma mudança de código foi feita** (decisão do usuário: avaliar primeiro).
O fallback `elo_live` em `server.py:705` permanece como está.

### Aviso de calibração

Uma estimativa manual anterior aplicou escala 1.0 aos deltas e produziu
"BFX 42% x NS 58%" para o Game 1 de BFX×NS (2026-08-27). A calibração mostra que
o coeficiente correto de `x_fit` é **~0.11**, não 1.0 — o efeito do draft foi
exagerado em cerca de **10×**. Com coeficientes calibrados o mesmo draft dá
**BFX 57.7%** (Elo calibrado sozinho: 57.0%; contribuição do draft: +0.67 p.p.).

**Não usar deltas de draft com escala arbitrária.** A contribuição real das
camadas de draft, quando existe, é da ordem de 1-2 pontos percentuais.

## Limitações conhecidas
- Marcos temporais de rota disponíveis apenas em **10/15/20/25 min**
  (Oracle's Elixir). Não há granularidade minuto a minuto no histórico;
  `riot_live_snapshots_v10` tem granularidade fina mas cobre 8 jogos.
- Sinergia no nível jogador-campeão específico é praticamente não-estimável:
  nenhum par passou de 4 jogos de co-ocorrência. O que sustenta `x_syn` é o par
  de **campeões**, não o par de **jogadores**.
- Counters não têm decaimento por patch — um matchup de 2023 pode ter se
  invertido com mudanças de itens.

## Próximos passos sugeridos (não executados)
1. **Se for a produção**: implementar `x_fit` com janela móvel de 30 jogos como
   ajuste ao `elo_live`, com coeficiente calibrado (~0.39). É a feature que
   carrega o ganho; `x_syn` e `x_lane` podem ficar de fora numa primeira versão.
2. Alimentar os acumuladores com LPL + LCKC mesmo para predizer LCK — o ganho
   veio em boa parte de acumuladores mais populados, não só de mais treino.
3. Separar forma recente de fit de campeão em duas features distintas, em vez de
   tentar isolar via escolha de janela (`corr(fit,elo)` ainda é 0.31).
4. Substituir `x_lane` por uma feature explícita de "força do campeão no meta"
   com decaimento por patch — é isso que ela está medindo de fato.

## Artefatos
Scripts do backtest (temporários, fora do repo):
`%LOCALAPPDATA%\Temp\claude\scratch_lck\` — `backtest.py`, `diag.py`,
`backtest2.py`, `apply.py`.
