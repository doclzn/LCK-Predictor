# LCK Predictor V24 — Full QA Review

## Por que esta versão existe

A V23 corrigiu o cache de partidas, mas a revisão completa mostrou que havia problemas de processo que permitiam erros básicos reaparecerem. A V24 é uma versão de **qualidade e confiabilidade**, não uma versão de novas heurísticas.

## 1. Legibilidade: a crítica do usuário estava correta

Na V23 existiam **294 declarações explícitas de `font-size` abaixo de 12 px**. Alterar apenas `html { font-size: 18px }` não resolvia isso porque valores em `px` não herdam a escala do elemento raiz.

### Correção V24

- nenhuma declaração explícita em px abaixo de **14 px**;
- `html` padrão em **18 px**;
- textos principais em 16–20+ px;
- linhas de partidas maiores;
- navegação maior;
- botões maiores;
- labels e métricas técnicas maiores;
- controle `Aa` no topo com três modos:
  - Grande;
  - Maior;
  - Máxima.

Esse requisito agora faz parte do teste automatizado. Se alguém reintroduzir fonte microscópica, `test_core_invariants_v24.py` falha.

---

## 2. Estado de partidas: havia regras duplicadas

Antes, diferentes partes do app decidiam separadamente se uma partida era:

- futura;
- ao vivo;
- finalizada;
- cache velho.

Isso é uma fonte clássica de inconsistência.

### V24

Foi criada uma única função canônica:

`v24_match_state(...)`

Ela retorna apenas:

- `completed`;
- `live`;
- `upcoming`;
- `pending`;
- `unknown`.

### Regra importante

Se o horário da partida já passou e não há estado live/final confiável, ela vira **pending**.

Ela NÃO pode mais aparecer como:

- Próxima;
- Ao vivo.

Isso é mais honesto do que fingir que o cache ainda representa o estado real.

---

## 3. Datas e fuso horário

Foi confirmado o bug de datas no frontend.

`new Date("2026-08-21")` é interpretado pelo JavaScript como UTC. Em UTC−3, isso pode renderizar visualmente como 20/08.

A V24 preserva a correção V23:

- data `YYYY-MM-DD` é tratada como calendário local;
- timestamps com timezone continuam sendo convertidos normalmente.

O teste de frontend verifica que essa proteção continua no código.

---

## 4. Resultados de 20/08

A build anterior ainda não possuía os resultados finais de 20/08 no arquivo histórico.

Durante a revisão, foram verificados publicamente e adicionados:

- **HLE 2–0 DK**;
- **NS 2–0 KRX**.

Consequentemente:

- Resultados agora começa em 20/08;
- o Elo atual foi recalculado;
- o cache antigo HLE × DK foi marcado como finalizado;
- não existe mais evento falso “ao vivo” dessa série.

Nenhuma métrica pré-jogo histórica foi inventada para esses resultados: os campos de forecast permanecem vazios quando não havia snapshot arquivado confiável.

---

## 5. Um problema mais sutil encontrado: regression test temporal

Depois que os resultados de 20/08 foram adicionados, alguns testes antigos do draft mudaram.

Isso revelou um erro metodológico no próprio teste:

> o teste de um draft histórico de HLE × DK estava usando o **Elo atual**, não o Elo que existia antes daquela partida.

Portanto o teste estava temporalmente mal definido.

### Correção

`evaluate_draft()` agora aceita `rating_override` para regressões históricas.

O caso do G1 HLE × DK usa explicitamente o snapshot pré-série:

- HLE: 1679.34;
- DK: 1734.14.

Assim, atualizar resultados futuros não altera retroativamente o regression case.

---

## 6. Governança V21: falso alarme de drift

A V21 havia colocado arquivos como:

- `server.py`;
- CSS;
- JS;
- `index.html`;

no mesmo mecanismo de integridade usado para congelar o experimento científico.

Ao melhorar a interface na V22/V23, o sistema passou corretamente a notar que esses arquivos mudaram — mas erroneamente chamava isso de **model drift**.

### Correção V24

Agora separamos duas coisas:

### Scientific lock

Pode bloquear o experimento:

- frozen candidate definitions;
- promotion policy;
- live training protocol;
- arquivos JSON de governança congelados.

### Release integrity

Verifica se o ZIP da V24 foi alterado/corrompido, mas não confunde uma mudança legítima de UI com alteração do experimento científico.

Novo arquivo:

`RELEASE_MANIFEST_V24.json`

Novo verificador:

`VERIFICAR_RELEASE_V24.bat`

---

## 7. Testes executados

Passaram:

1. Riot V10 fixture;
2. Strategy V14;
3. Draft Tree V15;
4. Flex Tree V16;
5. Joint Planner V17;
6. Series Planner V18;
7. Validation Lab V19;
8. Live Validation V20;
9. Model Governance V21;
10. Live Protocol V21;
11. Core Invariants V24.

### Invariantes V24

O teste falha se:

- partida passada aparecer como upcoming;
- cache antigo aparecer como live;
- 20/08 sumir dos resultados atuais desta build;
- KT × T1 não aparecer na agenda de 21/08;
- houver duplicidade de confronto/dia;
- scientific lock estiver quebrado;
- CSS possuir font-size px abaixo de 14;
- frontend voltar a usar assets de versão errada.

---

## 8. Estado atual das partidas na release

### Resultados mais recentes

- 20/08 — HLE 2–0 DK
- 20/08 — NS 2–0 KRX
- 19/08 — BRO 2–0 DNS
- 19/08 — GEN 2–1 KT

### Próximas

21/08:
- BRO × BFX
- KT × T1

22/08:
- DK × GEN
- DNS × KRX

23/08:
- BFX × NS
- HLE × T1

---

## 9. Nova regra de processo

A partir da V24, uma release não deve ser empacotada apenas porque “abre”.

Ela precisa passar por quatro gates:

### Data gate
Estados e datas coerentes.

### Model gate
Regressões V14–V21.

### UI gate
Versão correta + legibilidade mínima.

### Integrity gate
Scientific lock + release manifest.

Esse é o principal ganho desta revisão: transformar erros básicos em **condições que impedem a release**, em vez de depender de inspeção manual posterior.
