# V28.2 — Investigação da queda de acurácia nos patches 16.15/16.16

## Pergunta
`BACKTEST_PATCH_ACCURACY_V28.json` mostrou acurácia de 30% no patch 16.15 e
60% no 16.16 (20 séries cada), bem abaixo dos 81.5% do combinado dos últimos 4
patches rotulados (16.08-16.11). Seria o modelo (Series Elo K=64) perdendo
assertividade na Summer Split 2026?

## Investigação
- Inspecionei `series_detail` das 40 séries de 16.15+16.16: **17/40 (42.5%)**
  tiveram probabilidade a menos de 8 pontos percentuais de 50% — ou seja, quase
  metade dos jogos recentes são virtualmente coinflips para o modelo (parity
  alta entre os 10 times da LCK nesse trecho da Summer Split).
- `avg_confidence` caiu de ~0.76 (patches rotulados) para 0.64/0.60 (16.15/16.16)
  — o modelo está corretamente menos confiante, não mais confiante e errado.
- **Calibração agregada (383 séries, todo o histórico) segue sólida**:
  | faixa de confiança | n | vitória observada |
  |---|---|---|
  | 50-60% | 104 | 56.7% |
  | 60-70% | 102 | 67.7% |
  | 70-80% | 86 | 75.6% |
  | 80-90% | 69 | 84.1% |
  | 90%+ | 22 | 100% |
  Quase diagonal — o modelo não está mal calibrado.

## Conclusão
A queda pontual em 16.15/16.16 é **ruído estatístico de amostra pequena** (20
séries por patch, quase metade delas coinflips) em um trecho de temporada com
alta paridade entre os times — não um sinal de degradação do modelo. Calibração
geral do Series Elo K=64 continua correta. **Nenhuma mudança de código
recomendada** a partir deste resultado isolado.

## Próximo passo (se quiser acompanhar)
Repetir o backtest a cada novo patch e olhar a métrica de calibração (não só
acurácia bruta) antes de reagir a uma amostra de ~20 séries — acurácia por
patch tem variância alta demais pra ser um sinal confiável sozinha.
