# LCK Predictor V21 — Model Governance

## Por que esta versão existe

Até a V20, o projeto já tinha duas estruturas importantes:

- um conjunto V19 de candidatas congeladas para futura validação;
- um dataset live V20 que só permite treino depois de um gate mínimo.

Mas ainda faltava uma garantia operacional:

> **como provar que o modelo e a regra de promoção não foram alterados depois de começarmos a olhar os próximos resultados?**

A V21 adiciona essa camada.

Ela não altera o V8 Production e não promove nenhuma feature nova.

---

# 1. Lockbox dos modelos V19

As cinco definições congeladas do V19 foram exportadas para:

`governance/V19_FROZEN_CANDIDATES.json`

Cada candidata possui um SHA-256 sobre:

- candidate ID;
- frozen timestamp;
- feature list;
- imputação;
- standardization;
- coeficientes;
- intercepto;
- hiperparâmetro C.

O arquivo `GOVERNANCE_LOCK_V21.json` guarda os hashes esperados.

Antes de uma nova previsão prospectiva ser capturada, a V21 recalcula o hash da definição existente no SQLite.

Se houver qualquer divergência:

`FROZEN_MODEL_DRIFT`

é gravado no governance log e a candidata é excluída daquela captura.

Portanto alterar discretamente um coeficiente e continuar usando o mesmo holdout deixa de ser possível sem o app detectar.

---

# 2. Prediction provenance ledger

A tabela nova:

`prospective_capture_ledger_v21`

liga cada previsão prospectiva a:

- game ID;
- candidate;
- prediction row original;
- timestamp;
- experiment ID;
- model definition hash;
- feature hash;
- capture status.

O resultado não participa do hash de features.

A intenção é poder provar posteriormente:

> este vetor de informação + esta versão de modelo produziram esta previsão antes do resultado.

---

# 3. Promotion policy congelada antes do holdout

Arquivo:

`governance/PROMOTION_POLICY_V21.json`

O gate prospectivo exige no mínimo:

- **100 mapas futuros**;
- **40 séries futuras**;
- previsão capturada até **5 minutos**;
- candidata e core congelados;
- melhora simultânea em Log Loss e Brier;
- efeito prático mínimo;
- calibração aceitável;
- incerteza por bootstrap clusterizado pela série.

## Efeito mínimo

- Δ Log Loss ≤ **−0.005**
- Δ Brier ≤ **−0.002**

## Incerteza

A V21 tornou a regra explicitamente mais rígida:

**o upper bound de 95% deve ser ≤ 0 para os dois deltas**, Log Loss **e** Brier.

A implementação antiga do resumo V19 usava uma condição menos rígida (`um ou outro`). Isso foi corrigido para corresponder à política escrita.

## Calibração

ECE da candidata pode ser, no máximo:

`ECE(core) + 0.01`

## Resultado possível

Mesmo se todos os critérios forem satisfeitos:

`ELIGIBLE_FOR_REVIEW`

Não existe alteração automática de `model_registry_v10` para Production.

Isso exige uma nova decisão explícita após a revisão.

---

# 4. Estados de governança

A V21 utiliza estados mais conservadores:

### COLLECTING
Amostra futura mínima ainda não atingida.

### ELIGIBLE_FOR_REVIEW
Todos os gates pré-registrados passaram.

Isso **não** significa Production.

### INCONCLUSIVE_CONTINUE
Há amostra mínima, mas o sinal não satisfaz simultaneamente efeito, incerteza e calibração.

### REJECTED_PROSPECTIVE
A candidata fica pior nos dois primary metrics e a incerteza sustenta a piora.

### BLOCKED_INTEGRITY
A definição do modelo não corresponde mais ao hash congelado.

---

# 5. Live Model V1 pré-registrado

A V20 havia definido quando o dataset estaria grande o suficiente.

A V21 congela **como o primeiro treino será feito antes de o test set existir em quantidade suficiente**.

Arquivo:

`governance/LIVE_TRAINING_PROTOCOL_V21.json`

## Readiness

- 120 mapas completos;
- 8 times;
- 80 mapas com checkpoint 5 min;
- 80 com 10 min;
- 80 com 15 min;
- 60 com 20 min;
- 40 com 25 min;
- 25 com 30 min;
- blue win rate entre 35% e 65%.

## Split

Por **mapa inteiro**, em ordem cronológica:

- train: 65%
- validation: 15%
- test: 20%

Snapshots do mesmo mapa nunca podem atravessar splits.

## Weighting

O dataset mantém uma linha por minuto, mas mapas mais longos não devem dominar o loss apenas por terem mais snapshots.

Portanto, durante o treino:

> todos os snapshots de um mesmo mapa, juntos, recebem peso total 1.

## Candidate families congeladas

### live_objectives

- draft probability;
- game time;
- gold diff;
- kill diff;
- tower diff;
- dragon diff;
- Baron diff;
- inhibitor diff.

### live_role_distribution

Todos os anteriores +:

- TOP gold diff;
- JNG gold diff;
- MID gold diff;
- BOT gold diff;
- SUP gold diff;
- lead breadth.

Isso incorpora diretamente o aprendizado do primeiro HLE × DK: uma vantagem concentrada em um carry não é igual a uma vantagem espalhada pelas cinco posições.

---

# 6. Hiperparâmetros live também estão congelados

Estimator:

**weighted standardization + L2 logistic regression**.

Grid:

`C = [0.01, 0.03, 0.1, 0.3, 1.0]`

Implementação portátil:

- Python standard library;
- IRLS/Newton determinístico;
- intercepto sem penalização;
- L2 `lambda = 1/C`;
- máximo de 45 iterações.

Família e C são escolhidos exclusivamente no validation set.

Depois disso, train+validation são ajustados novamente e o test set é aberto uma vez.

---

# 7. Primary evaluation do live

Não vamos chamar 3.000 snapshots de “3.000 observações independentes”.

A avaliação principal usa checkpoints canônicos:

`5 · 10 · 15 · 20 · 25 · 30 min`

O primary score é a média macro entre checkpoints disponíveis.

Assim um jogo de 40 minutos não recebe várias vezes o peso de um jogo de 24 minutos simplesmente por durar mais.

Baseline:

> a probabilidade pós-draft carregada para frente.

A pergunta é portanto:

> **o estado live acrescenta informação probabilística útil além do que já sabíamos no draft?**

---

# 8. Test set live: one-shot

A V21 adiciona um bloqueio explícito.

Se já existir um run em:

`live_model_experiments_v21`

para o mesmo `protocol_id`, executar novamente o trainer retorna recusa.

Motivo:

> depois de vermos as métricas do test set, qualquer novo tuning precisa de um novo protocolo e de um novo epoch futuro.

Não é permitido rodar C=0.1, olhar o test, trocar feature, rodar de novo e continuar chamando aquele conjunto de “test”.

---

# 9. Critério de review live

Para o futuro live candidate ser sequer marcado como elegível para revisão:

- test macro Log Loss melhor que draft baseline;
- test macro Brier melhor que draft baseline;
- IC95% cluster bootstrap com upper bound ≤ 0 para ambos;
- ECE no máximo 0.02 pior que baseline;
- melhora de Log Loss em pelo menos 3 checkpoints entre 5/10/15/20 quando houver cobertura adequada.

Novamente:

`ELIGIBLE_FOR_REVIEW ≠ PRODUCTION`

---

# 10. Teste sintético do protocolo

Como a build distribuída corretamente possui **zero mapas live prospectivos suficientes**, não é possível testar o aprendizado real ainda.

Para testar a engenharia do pipeline sem fingir evidência real, foi criado um banco temporário com:

- 120 mapas sintéticos;
- 10 times;
- checkpoints completos de 5 a 30 min;
- sinal live conhecido;
- draft baseline neutro.

O teste confirmou:

1. readiness desbloqueia;
2. split é feito por mapa;
3. candidate selection usa validation;
4. test é aberto;
5. um run é persistido;
6. segunda execução com o mesmo protocol ID é **recusada**.

O artifact sintético é removido após o teste e não integra a release.

---

# 11. Tamper test

Também foi testado um caso em que um único coeficiente de `core_pool_exhaustion` é alterado em uma cópia temporária do banco.

Resultado esperado e observado:

- o hash deixa de conferir;
- a candidata some de `v21_verified_v19_freezes()`;
- um evento `FROZEN_MODEL_DRIFT` é gravado;
- o gate passa para `BLOCKED_INTEGRITY`.

---

# 12. Estado real desta release

Na base distribuída:

- prospective valid maps: **0**;
- prospective series: **0**;
- live training completed maps: **0**;
- live test runs: **0**.

Logo:

- nenhum modelo V19 foi promovido;
- nenhum live model foi treinado;
- o test set live continua fechado.

Esse “zero” é um resultado correto, não uma deficiência a esconder.

---

# 13. Ferramentas novas

## Verificar governança

`VERIFICAR_GOVERNANCA.bat`

Exibe:

- integridade dos arquivos;
- candidate hashes;
- gates;
- live protocol;
- eventos recentes.

## Tentar treino live

`TREINAR_LIVE_QUANDO_PRONTO.bat`

Se readiness não tiver passado:

`TRAINING BLOCKED`

Nenhum modelo é ajustado.

Se o protocolo já abriu o test set:

`TRAINING REFUSED`

Um novo protocolo/epoch será necessário.

---

# 14. O que a V21 muda na filosofia do produto

Até aqui, grande parte do projeto respondia:

> “qual feature/modelo parece funcionar melhor?”

A V21 adiciona a pergunta:

> **“conseguimos provar que decidimos as regras antes de ver o resultado?”**

Essa distinção é essencial se o objetivo é construir uma plataforma que possa dizer seriamente que um modelo melhorou fora da amostra.

---

# Próximo passo

Agora não faz sentido criar V22 apenas com outra feature.

A próxima evolução de maior valor é automatizar a **observabilidade do experimento**:

- detectar partidas que deveriam ter sido capturadas e não foram;
- medir coverage/missingness por checkpoint;
- detectar mudanças de schema do Riot feed;
- controlar drift de distribuição de features;
- comparar patches/rosters sem tocar nos coeficientes congelados.

Isso melhora a qualidade do futuro holdout sem gastar o holdout.
