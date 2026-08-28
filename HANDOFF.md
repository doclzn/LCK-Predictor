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
