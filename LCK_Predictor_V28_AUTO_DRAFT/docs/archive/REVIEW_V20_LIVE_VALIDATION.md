# LCK Predictor V20 — Live Validation

## Objetivo

A V19 mostrou que a camada live não pode ser validada ainda: a build possuía praticamente nenhum histórico de snapshots em andamento.

A V20 resolve o problema correto:

> **coletar um dataset prospectivo antes de treinar.**

O app já possuía snapshots brutos Riot. A V20 acrescenta um dataset compacto e auditável, preparado especificamente para modelagem.

---

## 1. Dataset live compacto

Nova tabela:

`live_training_snapshots_v20`

Enquanto um mapa está realmente `inProgress`, o coletor cria no máximo **uma linha por minuto de jogo**.

Cada linha armazena:

- game/event ID;
- game number;
- checkpoint de tempo;
- patch;
- Blue/Red;
- probabilidade pós-draft congelada naquele mapa;
- gold diff;
- kill diff;
- tower diff;
- dragon diff;
- Baron diff;
- inhibitor diff;
- gold diff Top/Jungle/Mid/ADC/Support;
- lead breadth;
- resultado, somente depois que ele se torna conhecido.

A linha é capturada antes do resultado.

O resultado é anexado posteriormente pelo scorer.

---

## 2. Completed-state snapshots são excluídos

Uma decisão importante:

> snapshot cuja partida já está `completed` **não entra como observação live de treino**.

Isso evita criar um dataset cheio de estados terminais em que Nexus/placar final praticamente entregam a resposta.

O snapshot final continua podendo existir na base bruta Riot para pós-jogo, mas não entra em `live_training_snapshots_v20`.

O teste automatizado confirma essa regra.

---

## 3. Por que um checkpoint por minuto

O feed bruto pode ser consultado a cada ~10 segundos.

Treinar diretamente nesses pontos produziria:

- enorme autocorrelação;
- dezenas de observações quase idênticas do mesmo mapa;
- falsa sensação de tamanho de amostra.

A V20 mantém o feed bruto para timeline, mas o dataset de ML é compactado para:

`3m, 4m, 5m, 6m ...`

um registro por game-minute.

Isso não elimina a correlação dentro do mapa; por isso o futuro split de treinamento também será feito **por game/event**, nunca aleatoriamente por snapshot.

---

## 4. Readiness Gate

O app agora mostra no Model & Validation Lab quando o live dataset está realmente pronto.

Thresholds atuais:

- 120 mapas completos;
- pelo menos 8 times cobertos;
- 80 mapas com checkpoint 5m;
- 80 com 10m;
- 80 com 15m;
- 60 com 20m;
- 40 com 25m;
- 25 com 30m;
- class balance aceitável.

Até todos os critérios passarem:

`TRAINING = BLOCKED`

Não existe botão de “treinar mesmo assim”.

---

## 5. Training script preparado

Arquivo:

`scripts/train_live_model_v20.py`

Ele possui duas funções.

### Check only

`python scripts/train_live_model_v20.py --check-only`

Mostra a cobertura e não treina nada.

### Training

Sem `--check-only`, o script primeiro verifica o gate.

Se o dataset não estiver pronto:

> `TRAINING BLOCKED`

Quando estiver pronto, o desenho pré-definido é:

- split cronológico por games completos;
- nenhum mapa aparece em train e test simultaneamente;
- snapshots de um mesmo mapa permanecem no mesmo split;
- C selecionado apenas na validação intermediária;
- teste final cronológico separado;
- Log Loss, Brier, Accuracy e AUC reportados.

Mesmo um resultado bom será salvo como:

`CANDIDATE_NOT_PROMOTED`

até review/calibração.

---

## 6. Modo Live Collector

Novo launcher:

`COLETAR_LCK_LIVE.bat`

Depois que o runtime portátil já tiver sido preparado pelo launcher normal, esse modo inicia o backend **sem abrir navegador**.

Ele pode ficar rodando durante os dias de LCK.

O background updater:

- descobre eventos live;
- consulta Riot;
- salva snapshots brutos;
- salva checkpoints compactos;
- backfilla resultado final;
- rotula o dataset;
- continua alimentando o Prediction Journal V19.

Ctrl+C encerra.

O app normal também coleta enquanto estiver aberto.

---

## 7. Feedback dentro da Match Page

Durante um mapa live a interface agora informa o estado do dataset:

- `dataset 15m salvo`
- ou `dataset 15m já salvo`

Isso confirma que o coletor científico está funcionando em paralelo à visualização da partida.

---

## 8. V19 permanece dentro da V20

A V20 mantém integralmente o Validation Lab.

Resultado retrospectivo V19 relevante:

### Pool exhaustion

- core LL: 0.59735
- core + exhaustion LL: 0.59529
- core Brier: 0.20557
- core + exhaustion Brier: 0.20453

mas os CIs bootstrap cruzam zero.

Status:

`INCONCLUSIVE / FROZEN FOR PROSPECTIVE`

### Flex isolado

- LL: 0.59926
- Brier: 0.20649

com bootstrap inteiramente no lado de piora.

Status:

`RETROSPECTIVE_REJECT`

Flex continua contexto estratégico, sem peso probabilístico central.

---

## 9. Gate prospectivo de draft também continua ativo

A V19 congela as candidatas e exige:

- 100 mapas futuros;
- 40 séries;
- capture pós-draft válida;
- zero retuning.

A captura só é válida para o gate se ocorrer até 5 minutos de jogo.

Snapshots abertos tarde aparecem como `LATE_CAPTURE` e ficam fora da avaliação.

---

## 10. Correção de persistência V18 preservada

A V19 detectou que `series_plan_v18()` escrevia numa tabela ausente e engolia a exceção.

A V20 preserva a correção:

`series_strategy_runs_v18`

agora existe.

O regression test do Series Planner passou depois da correção.

---

## 11. O que a V20 não faz

Ela **não cria um live model novo**.

Isso é proposital.

Treinar agora, com 0–1 mapas prospectivos, seria produzir uma demonstração, não um modelo confiável.

Também não tenta fabricar histórico live a partir de boxscores finais: estado aos 15 minutos não pode ser reconstruído honestamente a partir de um resultado final se o dado não foi coletado.

---

## 12. Próximo gate

A partir da V20, o projeto tem duas filas de evidência prospectiva:

### Post-draft feature gate

V19:

`core vs pool exhaustion / remaining pool / flex`

### Live-model dataset gate

V20:

`Riot snapshots in-progress → compact minute checkpoints → final outcome`

Quando houver volume suficiente, o próximo salto deixa de ser “V21 com mais uma heurística”.

Será:

> **treinar o primeiro live model temporal em dados realmente coletados antes do resultado e decidir, pelas métricas, se ele merece substituir a heurística live atual.**
