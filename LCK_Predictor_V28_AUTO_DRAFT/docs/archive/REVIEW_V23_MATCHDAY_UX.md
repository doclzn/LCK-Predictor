# V23 — Matchday UX

## Bug corrigido

A V22 podia manter partidas antigas em "Próximas" por dois motivos:

1. `upcoming_matches` preservava linhas já vencidas no tempo.
2. Um `riot_events_v10` antigo podia continuar marcado `inProgress`.
3. Datas sem horário (`YYYY-MM-DD`) podiam sofrer deslocamento de fuso no JavaScript ao serem convertidas diretamente com `new Date()`.

A V23 corrige os três.

## Regras novas

- Linha antiga de agenda é removida/ocultada.
- Evento Riot `inProgress/unstarted` que está muitas horas além do horário é tratado como cache obsoleto, nunca como live.
- Datas sem horário são formatadas como data local, sem conversão UTC.
- A Home combina Riot Events + `upcoming_matches` limpo.
- A lista é agrupada por dia.
- Existe botão `Atualizar agora`.
- O estado da agenda mostra se veio da Riot ou do cache local.
- Se o payload Riot possuir logo oficial do time, o app usa automaticamente; caso contrário utiliza o badge local.

## Regression case desta release

No banco recebido da V22 existiam:

- DK × HLE — 20/08
- NS × KRX — 20/08

ainda em `upcoming_matches`, além de HLE × DK em `riot_events_v10` marcado `inProgress`.

Após a rotina V23:

- 20/08 não aparece em Próximas.
- HLE × DK antigo não aparece como Ao vivo.
- 21/08 aparece primeiro:
  - BRO × BFX
  - KT × T1
- 22/08 e 23/08 permanecem na agenda.

## Objetivo de UX

A Home deve responder imediatamente:
1. há jogo ao vivo?
2. qual é o próximo confronto relevante?
3. quando são os próximos jogos?
4. como atualizo a agenda se o feed estiver atrasado?
