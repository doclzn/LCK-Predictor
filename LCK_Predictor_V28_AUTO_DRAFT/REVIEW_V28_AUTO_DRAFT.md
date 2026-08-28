# V28 — Auto Draft

## Causa
Até V27, o draft era um subproduto do coletor live completo. Se o Event ID/Game ID
não estivesse resolvido, não havia draft automático.

## Novo fluxo
- procura Event ID continuamente;
- resolve Game ID por getEventDetails;
- consulta Window independentemente do feed Details;
- captura participantMetadata/champions;
- salva drafts parciais (1/10...10/10);
- ao atingir 10/10, roda automaticamente o V8 pós-draft;
- Match Page atualiza a seção Auto Draft junto com o live.

## Frequência
- descoberta de live: 15 s;
- watcher de draft: 5 s durante partida;
- fallback de matchday reduz o loop para 5 s enquanto procura Event ID.

## Limite
A captura ocorre assim que o Window gameMetadata da Riot publica os champions.
Isso pode ser após lock completo/início do mapa; os endpoints web da Riot são
não documentados e não garantem champion-select em tempo real.
