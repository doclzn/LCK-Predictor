# LCK Predictor V18 — Series Planner

## O problema que a V18 resolve

Até a V17, a melhor decisão era aquela que sobrevivia melhor à árvore do **mapa atual**.

Em Fearless, isso ainda é incompleto. Um pick pode ser ótimo para o Game 1 ou Game 2 e consumir um champion que teria muito mais valor no mapa seguinte.

A V18 muda a função-objetivo para a **série**.

---

## Duas camadas diferentes

### Mapa atual

Continua vindo da cadeia:

`V8 leaf → V16 flex uncertainty → V17 joint ban/pick minimax`.

É a melhor leitura robusta disponível para o mapa atual dentro do produto.

### Mapas futuros

Ainda não existe draft real dos mapas futuros. Portanto a V18 não finge conhecer uma composição que ainda não foi escolhida.

Ela estima a **resiliência do champion pool restante**.

Para cada jogador/role:

1. remove champions já usados pelo Fearless;
2. remove picks conhecidos/modelados do mapa atual;
3. calcula as melhores opções restantes com WR ajustado e suporte de amostra;
4. combina as três melhores opções da role;
5. agrega média + bottleneck das cinco roles.

O resultado é um `pool quality score`, não uma win rate observada.

---

## Como a probabilidade futura é estimada

A V18 reaproveita o próprio coeficiente de **mastery** do V8.

Em vez de inserir mastery dos cinco picks reais — que ainda não existem — usa a diferença entre os pools restantes.

Para não inventar quem terá Blue/Red no próximo mapa, calcula:

- Team A como Blue;
- Team A como Red;
- média dos dois cenários.

Essa extrapolação é explicitamente **EXPERIMENTAL**.

O modelo V8 não foi originalmente validado para `remaining-pool quality`; portanto não promovemos esse número para Production.

---

## Matemática do Bo3/Bo5

Depois que temos:

- `p_current`: probabilidade robusta do mapa atual;
- `p_future`: estimativa experimental dos mapas futuros;
- placar atual;

calcular a chance de vencer a série é um problema probabilístico exato.

Exemplo: time lidera 1–0 em Bo3.

`P(série) = p_current + (1-p_current) × p_future`

Se `p_current = p_future = 50%`, o resultado é 75%.

A implementação usa programação dinâmica e também suporta Bo5.

A matemática da série é correta **condicionada aos inputs**. O ponto experimental é `p_future`.

---

## Exemplo do regression case HLE 1–0 DK

No estado armazenado antes do G2, com os 10 champions do G1 já removidos pelo Fearless, o Series Planner mostrou um comportamento importante:

- o pick com maior probabilidade do mapa não foi necessariamente o #1 para a série;
- uma alternativa com mapa robusto ligeiramente menor ganhou valor por deixar um pool futuro melhor.

No smoke test da release, a ordenação por série e a ordenação por mapa foram diferentes.

Isso prova que a nova função-objetivo está realmente ativa — não é apenas uma etiqueta na interface.

---

## O que significa “consumo Fearless”

A V18 considera:

- champions de mapas anteriores;
- picks já preenchidos no mapa atual;
- champions flex não atribuídos;
- picks presentes na Principal Variation da busca atual.

Bans **não** são carregados como consumo permanente para o mapa seguinte.

A interface chama isso de **known/modelled consumption**, porque picks que ainda não foram simulados no restante do mapa naturalmente não podem ser conhecidos.

---

## O que não estamos afirmando

A V18 não prova que:

> “preservar Gnar vale exatamente +1.6 pp na série no mundo real”.

Ainda existem incertezas:

- drafts futuros não observados;
- side choice futura;
- bans futuros;
- adaptação estratégica;
- mudanças de role/flex;
- dependência entre mapas.

Por isso a UI usa **SÉRIE · EXP**.

---

## Review dos três ciclos automáticos

### V16 — Flex Tree

Corrigiu a hipótese de role conhecida cedo demais.

### V17 — Joint Planner

Unificou ban e pick na mesma árvore.

### V18 — Series Planner

Mudou o objetivo de `P(vencer mapa)` para uma estimativa de `P(vencer série)` levando o pool futuro em consideração.

Essa sequência foi intencional: primeiro resolver incerteza de role, depois sequência de ações, só então otimizar a série.

---

## Próximos gargalos reais

1. Treinar/calibrar um modelo específico de **pool exhaustion** em séries Fearless.
2. Aprender side selection e side preference por equipe/patch.
3. Incluir ban phase futura na estimativa do pool dos próximos mapas.
4. Modelar dependência entre mapas em vez de repetir um único `p_future`.
5. Backtest de decisões de série usando drafts históricos completos, quando cobertura histórica permitir.

Até esses pontos serem validados, Series Planner permanece uma camada de decision support experimental sobre um núcleo probabilístico auditado.
