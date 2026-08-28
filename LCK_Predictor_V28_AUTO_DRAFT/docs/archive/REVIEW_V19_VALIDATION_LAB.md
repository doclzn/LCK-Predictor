# LCK Predictor V19 — Validation Lab

## Objetivo

A V18 tornou o produto mais sofisticado estrategicamente. A V19 muda a pergunta:

> **essa sofisticação melhora previsão fora da amostra ou apenas parece inteligente?**

A regra da V19 é simples: nenhuma feature experimental sobe para Production porque faz sentido narrativamente.

---

## 1. Correção metodológica importante

O projeto já analisou resultados de 2026 em versões anteriores. Portanto 2026 **não é mais um holdout cego do projeto**.

Nesta versão:

- hiperparâmetros das candidatas foram escolhidos somente com rolling-origin 2025;
- 2026 foi usado em uma auditoria retrospectiva única desta família de features;
- o resultado é rotulado `RETROSPECTIVE_NOT_PRISTINE`;
- nenhuma candidata é promovida por esse resultado;
- os modelos foram congelados para um gate prospectivo com partidas realmente futuras.

Esse detalhe evita uma afirmação estatística mais forte do que os dados permitem.

---

## 2. Dataset cronológico V19

Foram reconstruídos **900 mapas** com features calculadas antes de cada mapa:

- 551 mapas de 2025;
- 349 mapas de 2026;
- 343 séries.

A reconstrução é online/cronológica:

1. calcula a feature do mapa;
2. registra a previsão/linha do dataset;
3. somente depois atualiza player/champion/synergy state com o resultado daquele mapa.

Para mapas 2+ da mesma série, champions utilizados anteriormente entram no estado Fearless porque essa informação já era conhecida naquele momento.

---

## 3. Core surrogate

A V19 não substitui o V8 oficial.

Foi criado um **surrogate experimental comparável** para testar incrementos de feature com a mesma família:

- Elo pré-série;
- player×champion mastery Empirical Bayes;
- champion-pair synergy.

Resultado retrospectivo 2026:

- Accuracy: **68.19%**
- Log Loss: **0.59735**
- Brier: **0.20557**
- AUC: **0.73508**
- ECE: **3.34%**

O V8 Production continua com suas métricas próprias/auditadas. O surrogate existe apenas para comparar as novas features sob o mesmo experimento.

---

## 4. Fearless pool exhaustion

Feature:

`pool_exhaustion_adv = pool_loss_red - pool_loss_blue`

O pool de cada jogador é calculado apenas com dados anteriores e os champions consumidos antes do mapa atual são removidos.

### 2026 retrospectivo

Core:

- Accuracy 68.19%
- Log Loss 0.59735
- Brier 0.20557

Core + Pool Exhaustion:

- Accuracy **68.77%**
- Log Loss **0.59529**
- Brier **0.20453**
- AUC **0.73642**
- calibration slope **0.974**

Diferença:

- Δ Log Loss: aproximadamente **−0.00207**
- Δ Brier: aproximadamente **−0.00103**

Bootstrap clusterizado por série, 95%:

- Δ Log Loss: **[−0.00621, +0.00165]**
- Δ Brier: **[−0.00272, +0.00051]**

### Decisão

**INCONCLUSIVE**.

A direção é interessante, mas o intervalo cruza zero. A feature não é promovida.

Ela foi congelada para teste prospectivo.

---

## 5. Remaining pool resilience

A V18 usa a profundidade/qualidade do champion pool restante para estimar mapas futuros.

A V19 testa a premissa subjacente em nível de mapa.

Resultado 2026:

- Accuracy 68.48%
- Log Loss 0.59624
- Brier 0.20513

Bootstrap vs core também cruza zero.

### Decisão

**INCONCLUSIVE**.

Permanece experimental e congelada para prospectivo.

---

## 6. Flex value

A flex feature usa apenas a distribuição histórica de uso do campeão por role antes daquele mapa.

Resultado 2026:

- Accuracy 68.19%
- Log Loss **0.59926**
- Brier **0.20649**
- AUC 0.73183

Bootstrap 95% vs core:

- Δ Log Loss: **[+0.00004, +0.00383]**
- Δ Brier: **[+0.00010, +0.00176]**

Os dois intervalos ficaram inteiramente do lado de piora.

### Decisão

**RETROSPECTIVE_REJECT**.

Isso não significa que flex seja irrelevante para estratégia de draft.

Significa que **esta representação simples de flex não merece peso no núcleo preditivo** com a evidência disponível.

O Flex Resolver/Tree pode continuar como ferramenta estratégica contextual; não recebe promoção probabilística.

---

## 7. Exhaustion + Flex

Combinar as duas features produziu:

- Accuracy 67.91%
- Log Loss 0.59709
- Brier 0.20540
- ECE 2.20%

A calibração aparente melhorou, mas LL/Brier não apresentaram ganho robusto e o bootstrap cruza zero.

### Decisão

**INCONCLUSIVE**.

Não promover.

---

## 8. Diagnóstico Fearless por game number

Análise secundária — não usada para promoção.

### G2+ — 214 mapas de 2026

Core:

- Accuracy 66.36%
- LL 0.61101
- Brier 0.21222

Core + exhaustion:

- Accuracy **67.29%**
- LL **0.61045**
- Brier **0.21166**

O ganho é pequeno.

### G3+ — 79 mapas

A feature não melhora LL/Brier.

Isso reforça a decisão de não promover com base em um agregado favorável.

---

## 9. O que não pode ser validado retrospectivamente hoje

### Ban Engine

O corpus local atual não possui sequência histórica de bans adequada.

Status:

`DATA_BLOCKED`

Não vamos inferir “valor causal de ban” a partir de picks/resultados.

### Minimax / recommendation policy

O mundo contrafactual não foi jogado.

Não observamos simultaneamente:

- pick A + melhor resposta;
- pick B + melhor resposta;
- mesmo contexto e mesmos jogadores.

Status:

`PROSPECTIVE_OBSERVATIONAL_ONLY`

### Live model

A build possuía apenas um snapshot Riot armazenado no momento da auditoria.

Status:

`INSUFFICIENT_DATA`

A solução é coletar prospectivamente, não inventar um backtest.

---

## 10. Prospective Gate

Cinco modelos foram congelados:

- core;
- core + pool exhaustion;
- core + remaining pool;
- core + flex;
- core + exhaustion + flex.

Cada modelo guarda:

- features;
- imputação;
- média/escala;
- coeficientes;
- intercept;
- C escolhido em 2025;
- timestamp de freeze.

### Captura válida

Uma previsão prospectiva de draft só entra no gate quando o primeiro snapshot com draft completo é capturado até **5 minutos de jogo**.

Capturas posteriores ficam como:

`LATE_CAPTURE`

E são excluídas do gate.

Isso impede que abrir o app somente quando o mapa já está praticamente decidido contamine o experimento.

### Gate mínimo

Antes de qualquer decisão:

- **100 mapas futuros**;
- **40 séries futuras**;
- modelos congelados;
- zero retuning.

Para uma candidata passar para revisão de promoção:

- melhorar Log Loss e Brier vs core;
- alvo prático ΔLL ≤ −0.005;
- alvo prático ΔBrier ≤ −0.002;
- sem piora material de calibração;
- incerteza bootstrap reportada.

Mesmo `PASS_CANDIDATE` significa “pode ser revisado para promoção”, não promoção automática.

---

## 11. Bug da V18 encontrado durante a auditoria

A função `series_plan_v18()` tentava inserir em:

`series_strategy_runs_v18`

mas essa tabela não existia na build examinada.

Como o insert estava dentro de `try/except`, a falha era silenciosa.

A V19 cria a tabela corretamente.

O Series Planner continuava calculando e exibindo respostas; o problema afetava a **persistência do histórico de runs**, não a matemática exibida.

O regression test da V18 foi executado novamente depois da correção e passou.

---

## 12. Resultado prático da V19

A V19 fez exatamente o que uma camada de validação deveria fazer:

- encontrou uma hipótese promissora, mas não forte o suficiente: **pool exhaustion**;
- encontrou uma hipótese que piora o modelo: **flex preditivo simples**;
- recusou promoção de ambas;
- congelou candidatas;
- iniciou infraestrutura para um teste realmente futuro.

A conclusão não é “o Strategy Engine estava certo”.

A conclusão é:

> **Fearless pool exhaustion tem sinal suficiente para merecer coleta prospectiva. Flex simples não merece peso preditivo central neste formato.**

Isso torna o projeto estatisticamente mais forte, mesmo reduzindo o número de features que podemos chamar de preditivas.
