# V28.1 — Feed de Tempo Real (investigação + implementação)

## Pergunta original
> "Precisamos de uma API mais atualizada ou de um método de conseguir dados mais
> próximos do tempo real da LCK. Sites como draft-helper.com, pandascore,
> andydanger/live-lol-esports, hub.maisesports, oddsmatrix, grid.gg conseguem."

Para responder, foi feita uma investigação controlada (sondas reais contra a
infraestrutura da Riot) e, em seguida, implementado o que é possível com as
fontes públicas + o caminho para o draft realmente em tempo real.

---

## 1. O que as sondas revelaram (ambiente controlado)

### 1.1 Não existe endpoint público de draft em tempo real
- O gateway `esports-api.lolesports.com/persisted/gw` expõe apenas operações de
  metadados. Sondamos `getLiveDrafts`, `getLiveGames`, `getDraft`, `getLiveDraft`:
  todos retornam **400 "Invalid request parameters"**.
- Controle decisivo: uma operação inventada (`getTotallyFakeOp123`) retorna o
  **mesmo 400**. Ou seja, o 400 é genérico para operação inexistente — esses
  endpoints de draft simplesmente **não existem** no gateway público.
- O catálogo OpenAPI não-oficial (`vickz84259/lolesports-api-docs`, o mesmo usado
  pelo `andydanger/live-lol-esports` citado) confirma: as únicas fontes vivas são
  `window` e `details`; **não há endpoint de picks/bans/champ-select**.

### 1.2 O feed vivo é só `window` + `details`
- `feed.lolesports.com/livestats/v1/window/{gameId}` → estado do jogo (ouro,
  kills, torres, dragões, barões, inibidores, participantes).
- `feed.lolesports.com/livestats/v1/details/{gameId}` → estatísticas granulares
  por participante (itens, runas, dano, wards, ordem de habilidades).
- Qualquer outro subpath (`/drafts`, `/picks`, `/bans`, `/champselect`, ...) →
  **404 SERVER_ENDPOINT_NOT_FOUND**.

### 1.3 Draft só aparece DEPOIS do lock (limite já conhecido da V28)
- Os frames de `window` só trazem `gameState` `in_game`/`finished`. **Não existe
  frame de champ-select** no feed público.
- Os champions aparecem em `gameMetadata.participantMetadata` apenas quando a
  Riot publica — na prática após o lock/início do mapa. É exatamente o limite que
  o `REVIEW_V28_AUTO_DRAFT.md` já documentava. **Não há como contornar isso pela
  fonte pública.**

### 1.4 Sem `startingTime` a resposta vem do INÍCIO do jogo (não do frame atual)
- Validado contra a API real: para um mesmo jogo, consultar `window` **sem**
  `startingTime` retornou um trecho mais antigo, enquanto `startingTime=agora-60s`
  retornou o trecho mais recente. A spec OpenAPI diz o mesmo: "se `startingTime`
  não for fornecido, a resposta começa do início do jogo".
- **Consequência:** consumo em tempo real deve SEMPRE usar `startingTime` explícito.
  (Uma primeira versão desta mudança usava "sem startingTime"; foi corrigida por
  ser risco de dado velho.)

### 1.5 O "delay de 60s" legado era janela de lookback, não latência
- `fetch_event_live(delay_seconds=60)` pede `startingTime = agora-60s` e fica com o
  **último** frame retornado = o frame mais fresco publicado pela Riot. O 60 é uma
  margem para garantir frames existentes, não um atraso adicionado. O estado
  in-game, portanto, **já era próximo do tempo real**; o gargalo real nunca foi esse.

### 1.6 O feed vivo é efêmero
- Para um jogo concluído há 2 dias resta apenas um trecho curto/fragmentado.
  Captura completa precisa acontecer **durante** a partida (daí o coletor
  incremental abaixo).

---

## 2. Conclusão honesta
- **Estado do jogo ao vivo (ouro/kills/etc.):** já chegava perto do tempo real.
  A V28.1 torna o consumo mais eficiente e observável (item 3), mas o teto de
  frescura é o atraso intrínseco do feed da Riot + o delay de transmissão.
- **Draft (picks/bans) em tempo real de verdade:** **não existe na fonte pública.**
  Quem mostra isso (draft-helper, hubs de odds) consome feed de parceiro oficial.
  O caminho é a **GRID** (parceira oficial de dados da Riot), item 4.

---

## 3. O que mudou na V28.1

### 3.1 `riot_feed.py`
- `RealtimeCursor` — cursor de paginação por `game_id` (guarda o último
  `rfc460Timestamp` visto).
- `fetch_incremental(game_id, cursor, lookback_seconds=90)` — pede só frames novos
  desde o cursor; na primeira chamada semeia com lookback curto; em HTTP 400
  (cursor fora da janela retida) **re-semeia com lookback fresco** — nunca consulta
  sem `startingTime`.
- `fetch_event_live_incremental(event_id, cursor)` — resolve evento→game e devolve
  o snapshot normalizado a partir do frame mais fresco, com a mesma assinatura
  prática do caminho legado.

### 3.2 `server.py`
- `_LIVE_CURSOR` em nível de módulo.
- `live_response_v10` passa a usar `fetch_event_live_incremental`; em qualquer erro
  faz fallback para o legado `fetch_event_live(event_id, 60)` e reseta o cursor.
  Benefício: mesma frescura, sem re-buscar a janela de 60s inteira a cada poll de 5s.
- Novo campo `frame_lag_seconds` na resposta = idade do frame mais recente em
  relação ao relógio (observabilidade da latência real).

### 3.3 `scripts/capture_riot_live.py`
- Flag `--incremental`: usa o cursor para capturar apenas frames novos por poll
  (menos duplicatas nos JSONL de replay).

### 3.4 Testes
- `tests/test_realtime_feed_v28_1.py`: cursor, seed/avanço, fallback 400 (re-semeia,
  nunca sem `startingTime`), `fetch_event_live_incremental`, fallback legado no
  `live_response_v10`.

---

## 4. Posicionamento: GRID/draft-helper são REFERÊNCIAS de produto, não fontes

Esclarecimento do usuário: **GRID e draft-helper foram citados como exemplos da
plataforma que queremos ser parecidos** (experiência de dados live), **não como
fontes de dados a integrar**. Não haverá chave de terceiro.

Consequência: o "meio próprio" é a nossa pipeline sobre os **feeds públicos da
Riot** (seção 1/3), que já entrega paridade com esses sites (seção 8). O scaffold
`grid_feed.py`/`probe_grid.py` (que tratava GRID como fonte) foi **removido** por
ser leitura equivocada.

### Fontes consideradas e por que não são o caminho
- **GRID / PandaScore / Bayes** — parceiros comerciais; exigiriam chave paga. Não é
  o modelo desejado (queremos meio próprio).
- **Riot Developer Portal (API oficial de esports)** — acesso por aplicação; pode
  ser avaliado no futuro como fonte oficial, mas hoje os feeds públicos bastam.
- **`leaguepedia_parser`** — histórico/rosters, não tempo real; útil p/ base
  histórica, não para live.
- **OCR da transmissão** — único pré-lock sem parceiro, mas frágil/ToS; descartado.

---

## 5. Governança
- Apenas artefatos imutáveis em `governance/*.json` bloqueiam o experimento
  prospectivo (política V24). Esta mudança não toca nesses arquivos nem em
  definições de modelo; as capturas V19/V21 seguem válidas.
- `RELEASE_MANIFEST_V21.json` registra hashes de release/histórico (escopo
  `release_history`, não crítico) — evoluem sem invalidar o lockbox científico.

---

## 6. Verificação feita
- Sondas reais contra a API (gateway, livestats, operação fake de controle).
- `tests/test_realtime_feed_v28_1.py`: OK.
- Cluster live/riot/V28: `test_auto_draft_v28`, `test_live_games_v28`,
  `test_riot_v10`, `test_live_protocol_v21`, `test_live_validation_v20`: OK.
- E2E contra a API real (`scripts/validate_realtime_e2e.py`): o caminho incremental
  devolve o **mesmo frame mais fresco** do legado e o cursor avança corretamente.

## 7. Próximo passo (depende de partida ao vivo)
Durante o próximo jogo (ex.: 26/08 05:00 BRT), rodar
```
runtime\python.exe scripts\capture_riot_live.py --incremental --interval 5
```
e, opcionalmente, `scripts\probe_window_history.py <gameId> <ISO antes do draft>`
para re-confirmar ao vivo a ausência de frames de champ-select e medir a latência
real do frame (`frame_lag_seconds`).

---

## 8. Reavaliação — paridade com dashboards públicos (GRID desnecessário)

Após teste ao vivo (KRX × BFX, LCK CL Play-In, 25/08/2026) e comparação com o
dashboard `andydanger.github.io/live-lol-esports` (que usa os **mesmos** feeds
públicos Riot), conclui-se:

- Nossa captura incremental (`fetch_event_live_incremental`) entrega **os mesmos
  dados ao vivo** (ouro/kills/torres/dragões/barões/inibidores por time e
  CS/KDA/ouro/nível/itens por jogador) com delay < 1 min — paridade com o site.
- O draft é capturado 10/10 no instante da publicação (pós-lock), como o próprio
  draft-helper faz (ele também só lê "locked drafts").
- **Portanto o esforço GRID / OCR / pré-lock é DESNECESSÁRIO** para o objetivo da
  plataforma: já temos, com fonte pública e sem chave, o mesmo que os sites de
  referência. (GRID era referência de produto, não fonte — ver seção 4.)

Ferramentas de conferência adicionadas:
- `scripts/compare_live_parity.py <eventId>` — imprime o snapshot ao vivo p/
  comparar lado a lado com qualquer dashboard público.
- `scripts/poll_live_draft.py`, `scripts/save_live_capture.py`,
  `scripts/test_live_draft_now.py` — captura/registro do draft ao vivo.
