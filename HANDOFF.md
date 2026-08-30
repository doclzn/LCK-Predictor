# Handoff — avaliacao da LPL como amostra adicional

Ultima sessao: 2026-08-27/28. Contexto para retomar em sessao nova.

## Pergunta original

Adicionar os jogos da LPL ao banco (hoje so LCK) aumenta a amostra e
melhora a predicao?

## Resposta curta

Depende inteiramente do tipo de feature:

- Features por **jogador** (`mastery_diff`, `synergy_diff`): **nao ajuda**.
  Chovy nao joga na LPL. Adicionar LPL nao acrescenta observacoes dos
  jogadores coreanos, so puxa os coeficientes do modelo para outra
  populacao. Testado: nenhuma metrica melhora, AUC piora, calibracao
  se degrada (slope 0.92 -> 0.80).
- Features por **campeao** (campeao isolado, duplas, matchups): **ajuda**,
  pouco mas de forma consistente. Camille top e o mesmo objeto nas duas
  ligas, entao um jogo da LPL e uma observacao legitima sobre Camille.
  Testado: melhora em 8/8 comparacoes; canal de duplas passa o teste de
  significancia.

## Numeros (447 jogos de LCK 2026 como teste, bootstrap por serie)

| Modelo                              | Acuracia | Log-loss | AUC    |
|-------------------------------------|----------|----------|--------|
| core (producao hoje)                | 0.6555   | 0.6164   | 0.7036 |
| core + campeao isolado (LCK+LPL)    | 0.6711   | 0.6140   | 0.7124 |
| core + duplas (LCK+LPL)             | 0.6600   | 0.6155   | 0.7054 |
| core + matchups (LCK+LPL)           | 0.6510   | 0.6138   | 0.7126 |
| core + os tres (LCK+LPL)            | 0.6622   | 0.6114   | 0.7167 |

Alivio de escassez que a LPL traz nos 447 jogos de teste:

| Canal              | fonte LCK        | fonte LCK+LPL    |
|--------------------|------------------|------------------|
| duplas: mediana    | 18 jogos         | 29 jogos         |
| duplas <5 jogos    | 18.0%            | 10.9%            |
| matchups: mediana  | 14 jogos         | 26 jogos         |
| matchups <5 jogos  | 25.1%            | 16.9%            |

**Achado colateral, possivelmente mais importante que a LPL:** os tres
features de campeao nao existem no modelo de producao e ajudam mesmo
usando so LCK (log-loss 0.6164 -> 0.6122). A LPL e um reforco em cima
disso (-> 0.6114), nao o efeito principal.

## Estado do codigo

Blindagem por liga (o banco tem LPL, mas nada dela entra no modelo sem
ser pedido explicitamente):

- `scripts/import_oracles_elixir.py` — flag `--model-leagues` separa o que
  CARREGA (`--leagues`) do que ALIMENTA as agregacoes. Corrigido bug em
  `rebuild_current_form`, que pegava o ultimo split do banco inteiro e
  seria sequestrado pelo calendario da LPL.
- `server.py:70` — `MODEL_LEAGUES` (env var, default LCK) aplicado as 4
  consultas que liam `player_games`/`team_games` cru. Evita colisao de
  tricode/nickname entre ligas.
- `scripts/run_validation_v19.py` — `MODEL_LEAGUES` e `EVAL_LEAGUES`
  permitem treinar numa liga e avaliar noutra. Necessario para o teste
  justo (treinar com LCK+LPL, medir so em LCK).
- `runtime/` — habilitado `site-packages` (`python312._pth`, original em
  `.bak`) e instalado sklearn/scipy/pandas. O v19 nao rodava antes disso.

Banco: `player_games` tem LCK 53.530 + LPL 14.180 linhas (LPL so 2025-2026).
Agregacoes seguem LCK-only. Backup pre-importacao:
`data/lck_data_v1.backup-20260827T092915Z.sqlite`.

## Scripts de pesquisa (`scripts/research/`)

Reproduzem toda a analise. Rodar com `runtime/python.exe`.

- `diag.py` — cobertura de features por liga; revelou elo_diff 0% na LPL
- `ab_lpl.py` — A/B do core, bootstrap pareado por serie
- `ab_noelo.py` — mesmo teste sem elo_diff, varios conjuntos
- `champ_meta.py` — feature de meta de campeao, fonte LCK vs LCK+LPL
- `canais.py` — os tres canais separados + medicao de escassez

## Proximo passo decidido, nao executado

Formalizar `champ_solo_diff`, `champ_pair_diff` e `matchup_diff` como
candidatas no `MODEL_SPECS` de `run_validation_v19.py` e rodar o gate
oficial, com registro em `validation_experiments_v19`. E o que converte
os indicios acima em decisao de producao auditavel.

Observacao do usuario a considerar: a avaliacao futura da LPL usaria a
LCK pelo mesmo mecanismo, com os papeis invertidos. A infraestrutura
(`--model-leagues`, `EVAL_LEAGUES`) ja suporta isso sem mudanca de codigo.

## Ressalva honesta

Os ganhos sao pequenos e, fora o canal de duplas, nao atingem
significancia formal com 447 jogos de teste. O padrao de 8/8 metricas
melhorando e mais convincente que qualquer numero isolado, mas continua
sendo indicio, nao prova.

## Atualizacao — 2026-08-29: proximo passo executado

Formalizados `champ_solo_diff`, `champ_pair_diff` e `matchup_diff` dentro
de `build_dataset` (`scripts/run_validation_v19.py`), reaproveitando o
filtro `MODEL_LEAGUES` ja existente (nao precisou de parametro novo).
Quatro candidatos novos no `MODEL_SPECS`: `core_champ_solo`,
`core_champ_pair`, `core_champ_matchup`, `core_champ_all`.

**Bug encontrado e corrigido durante a integracao:** a funcao `smooth()`
desempacotava a tupla armazenada `(games, wins)` em variaveis nomeadas
`w,n` — invertendo os papeis na formula bayesiana `(wins+K/2)/(games+K)`.
Isso destruia o sinal das tres features (alguns candidatos chegavam a ter
correlacao NEGATIVA com a versao de referencia em
`scripts/research/canais.py`). Corrigido; apos o fix os numeros batem
exatamente com o `canais.py` (core+os tres, fonte LCK: log_loss 0.6164 ->
0.6122, AUC 0.7036 -> 0.7120).

Gate oficial rodado com `MODEL_LEAGUES=LCK EVAL_LEAGUES=LCK` (config de
producao). Resultado gravado em `validation_experiments_v19` e
`validation_freeze_v19`:

| Candidato            | Veredito              | log_loss | Δ vs core |
|-----------------------|------------------------|----------|-----------|
| core_champ_solo       | INCONCLUSIVE           | 0.6146   | -0.0018   |
| core_champ_pair       | RETROSPECTIVE_REJECT   | 0.6167   | +0.0002   |
| core_champ_matchup    | INCONCLUSIVE           | 0.6148   | -0.0016   |
| core_champ_all        | RETROSPECTIVE_SUPPORT  | 0.6122   | -0.0042   |

Os quatro ficaram `FROZEN_AWAITING_PROSPECTIVE` em `validation_freeze_v19`
(precisam de >=100 mapas e >=40 series futuras antes de promocao, regra
ja existente no gate). Nenhum entrou em producao ainda — isso e
decisao separada, pendente de validacao prospectiva.

Ambiente: `.venv/` criado em `LCK_Predictor_V28_AUTO_DRAFT/` via
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
(o `runtime/` do handoff anterior era especifico do Windows e nao veio
no upload para este Mac).

Backup pre-run: `/tmp/lck_data_v1.sqlite.pre_champ_features.bak`.

### Proximo passo sugerido (nao executado)

Nenhuma acao de codigo pendente imediata. Deixar `core_champ_all`
acumular jogos/series futuras da LCK ate bater o minimo do gate
prospectivo (100 mapas / 40 series) e so entao revisar promocao.

## Atualizacao — 2026-08-29: teste com LCK+LPL no gate oficial

Rodado `MODEL_LEAGUES=LCK,LPL EVAL_LEAGUES=LCK` no gate oficial (ele
retreina TODAS as features, nao so as de campeao, com a liga extra —
diferente do `scripts/research/canais.py`, que mantinha elo/mastery/
synergy fixos em LCK e so trocava a fonte dos tres canais de campeao).

Resultado: como esperado pelo achado original, o `core` baseline piora
com LPL misturada (log_loss 0.6164 -> 0.6185, calibration_slope 0.92 ->
0.80 — mastery/synergy sao features por jogador e a LPL nao acrescenta
observacao dos jogadores da LCK). O `core_champ_all` final ficou em
log_loss 0.6127 (pior que 0.6122 so-LCK) mas com AUC 0.7187 (melhor que
0.7120) e acuracia 0.6734 (melhor que 0.6667) — sinal misto, nao uma
vitoria clara sobre a baseline LCK-only.

**Conclusao prática:** manter a config de producao (`MODEL_LEAGUES=LCK`,
o default) e correta. Para de fato capturar o beneficio da LPL nos
canais de campeao sem contaminar mastery/synergy, seria preciso separar
a fonte por feature (uma env var so para os tres canais de campeao,
tipo `CHAMP_LEAGUES`, independente de `MODEL_LEAGUES`) — e o que
`canais.py` ja faz de forma isolada, mas `build_dataset` hoje usa uma
unica fonte para tudo. Nao implementado; e trabalho de escopo maior,
nao decidido como prioridade.

O banco foi restaurado ao estado oficial (`MODEL_LEAGUES=LCK`) apos o
teste — os numeros em `validation_experiments_v19`/`validation_freeze_v19`
sao os mesmos da rodada anterior (log_loss 0.6122 para `core_champ_all`).
