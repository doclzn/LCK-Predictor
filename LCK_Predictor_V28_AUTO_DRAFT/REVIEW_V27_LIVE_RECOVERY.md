# V27 — Live Recovery

## Bug
A aba Ao vivo dependia apenas de `riot_events_v10`. Se `getLive`/schedule não
tivesse sido sincronizado ainda, a aba ficava vazia embora a partida estivesse ocorrendo.

## Recuperação em 3 camadas
1. Riot `getLive`.
2. Refresh do schedule Riot + estado `inProgress`.
3. Fallback temporário por horário do matchday.

O fallback não inventa gold, kills ou Event ID. Ele apenas evita a falsa mensagem
"Nenhuma partida" e mostra `LIVE · SYNC` até a Riot responder.

## Legacy schedule
Algumas linhas antigas do banco tinham só `YYYY-MM-DD`, sem horário/event_id.
Para os dias regulares desta semana, o fallback conserva a ordem gravada no schedule
e usa os slots LCK no Brasil: 05:00 e 07:00 (UTC-3).

## Regression de 21/08/2026 07:22 BRT
- BRO × BFX: não é mais o candidato atual após o início do segundo slot.
- KT × T1: `live_candidate`.
- Próximas começa em 22/08 enquanto o segundo jogo está em andamento.
- Se Riot retorna Event ID, a interface promove para o Match Page live completo.
