# LCK Predictor V15 — Draft Tree

## O que mudou

A V14 ranqueava o próximo pick.

A V15 pergunta:

> **Se eu escolher este campeão, qual é a melhor resposta modelada do adversário — e o pick continua bom depois dela?**

A nova aba **Draft Tree** executa uma busca beam/minimax sobre a ordem real de picks.

## Minimax

Para o time da raiz:

- nossos nós maximizam a avaliação;
- nós adversários minimizam;
- o leaf é avaliado pelo mesmo V8 pós-draft.

A interface separa:

**Imediato**
probabilidade V8 logo após o primeiro pick.

**Robusto / minimax**
valor V8 no leaf escolhido pela sequência de melhores respostas dentro do beam.

**Penalidade da resposta**
quanto o pick perdeu entre a leitura imediata e o leaf robusto.

Isso ajuda a detectar picks aparentemente fortes, mas fáceis de responder.

## Principal Variation

Cada candidato mostra a linha que determinou o valor minimax.

Exemplo conceitual:

`B1 Jayce → R1 Karma → R2 Ahri`

Não significa que essa linha acontecerá.
Significa que, entre os ramos explorados, ela foi a resposta que mais pressionou a escolha da raiz.

## Performance

A primeira implementação avaliava V8 em quase todos os candidatos intermediários e levou mais de 30 s.

Foi refeita.

Agora:

1. player mastery + meta + flex fazem uma shortlist barata;
2. estados intermediários usam a shortlist para beam ordering;
3. V8 roda na raiz e nos leaves;
4. estados repetidos são cacheados.

Preset padrão:

- depth 3;
- beam 2;
- 1 candidato por role na shortlist final.

No regression test, ficou em aproximadamente 5–6 s e ~17 estados V8.

Há um complexity guard: árvores estimadas acima de 80 leaves são recusadas.

## Flex Resolver

A V15 também adiciona role uncertainty.

Dado um time e champions como:

`Poppy · Aurora · Smolder`

o resolver enumera atribuições plausíveis usando:

- uso do champion na role;
- experiência do jogador;
- meta da role.

No teste com T1, foram encontradas múltiplas atribuições plausíveis, incluindo Poppy jungle e support.

O score do Flex Resolver é suporte relativo da atribuição, não win probability.

## Limite metodológico

V15 continua experimental.

O V8 de leaf é validado contra drafts reais, mas:

- a shortlist;
- o beam;
- a escolha minimax;
- a política de “melhor resposta”

não possuem validação causal própria.

Portanto “robusto/minimax” deve ser lido como análise de sensibilidade do modelo, não como uma nova probabilidade calibrada.

## Próximo passo natural

O salto seguinte seria unir árvore + flex uncertainty:

em vez de uma árvore em que cada champion já ocupa uma role fixa, manter vários estados possíveis de role durante picks precoces e colapsá-los conforme o draft revela informação.

Depois disso, a evolução seria otimização conjunta:

`ban → pick → best response → future Fearless pool`

com objetivo final de maximizar **P(vencer a série)**, e não apenas P(vencer o mapa.
