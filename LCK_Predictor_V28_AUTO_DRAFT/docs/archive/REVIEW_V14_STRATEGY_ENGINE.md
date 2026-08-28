# LCK Predictor V14 — Strategy Engine

## Objetivo

A V13 começou a responder:

> “Qual é o melhor próximo pick segundo várias simulações do Draft Engine?”

A V14 acrescenta uma pergunta mais difícil:

> **“Qual é a melhor decisão considerando a ordem real do draft e a série?”**

Isso exige separar três coisas.

### 1. Probabilidade do mapa

Vem do **V8 audited draft core**.

### 2. Ranking de candidatos

V13, experimental.

### 3. Estratégia de draft

V14, experimental.

A camada V14 não é apresentada como uma nova probabilidade calibrada.

---

# Ordem do draft

A V14 representa a sequência padrão de picks:

`B1 → R1 → R2 → B2 → B3 → R3 → R4 → B4 → B5 → R5`

E a ordem correspondente de bans:

`B1BAN → R1BAN → B2BAN → R2BAN → B3BAN → R3BAN → R4BAN → B4BAN → R5BAN → B5BAN`

O sistema resolve automaticamente qual equipe controla Blue/Red.

Isso permite atribuir valor diferente a:

- blind pick;
- early flex;
- late counterpick;
- R5;
- second-ban phase.

---

# Strategy Pick

Cada candidato passa primeiro pelo motor V13/V8.

Depois são adicionados componentes estratégicos **apenas para ordenar decisões**.

## Immediate component

`V13 evidence-adjusted delta`

Já incorpora shrinkage de evidência para não premiar excessivamente amostras pequenas.

## Flex value

A V14 cria `champion_flex_profile_v14`.

O perfil usa a distribuição de jogos do campeão entre roles em 2026.

Flex recebe mais valor em picks precoces.

Por exemplo:

- B1: peso alto;
- R1/R2: alto;
- middle picks: médio;
- B5/R5: quase nenhum valor de informação escondida.

Isso evita premiar flex igualmente quando ele já não esconde informação.

## Denial value

Pickar um champion do adversário pode removê-lo do draft.

Mas o primeiro teste da V14 mostrou um erro potencial:

> o sistema poderia valorizar muito “roubar” um comfort adversário mesmo quando nosso jogador quase não tinha experiência no champion.

Foi corrigido.

Denial agora é multiplicado pela **familiaridade própria**.

Assim:

- comfort adversário alto + nosso jogador experiente = denial relevante;
- comfort adversário alto + nosso jogador sem amostra = denial fortemente reduzido.

## Future pool cost

Fearless cria um custo intertemporal.

Se um jogador possui:

- Champion A muito forte;
- alternativas claramente inferiores;

gastar A agora remove essa opção dos próximos mapas.

A V14 estima um `future_pool_cost_pp_equiv`.

Ele é um componente de ranking, não uma estimativa causal observada.

---

# Correção do número de mapas futuros

Durante o review foi identificado outro problema.

A versão inicial tratava:

Game 1 → “até 2 mapas futuros”

como se significasse:

Game 1 → “2 mapas futuros garantidos”.

Isso superestimaria o custo Fearless.

A release final usa **mapas futuros esperados**.

## Durante Game 1

Game 2 é garantido.

Game 3 só ocorre se os dois primeiros mapas forem divididos.

Com probabilidade de mapa `q`:

`E[futuros após G1] = 1 + 2q(1-q)`

Portanto o valor fica entre 1 e 1.5.

## Durante Game 2

Se o placar é 1–0:

Game 3 ocorre apenas se quem está atrás vencer Game 2.

O app usa o placar da série + probabilidade atual do mapa.

## Durante Game 3

`E[futuros] = 0`

Logo não existe penalidade por preservar champion pool depois da série.

---

# Ban Engine

A V14 adiciona uma política separada de bans.

Ela considera:

## Comfort denial

Player×champion do adversário com suporte de amostra.

## Meta strength

Volume e força ajustada do champion na role em 2026.

## Flex

Champions realmente usados em múltiplas roles recebem valor estratégico adicional.

## Pool scarcity

Se o jogador possui poucas alternativas razoáveis e disponíveis, retirar um comfort vale mais.

O resultado é `Ban Priority`.

A interface normaliza o melhor candidato de cada consulta para:

`100 / 100`

Isso é apenas um score relativo.

Não significa:

> “este ban adiciona X% de chance de vitória”.

---

# Contexto automático da série

Ao abrir o Draft Lab a partir de uma Match Page Riot, a V14 passa:

- Event ID;
- Team A / Team B;
- placar atual;
- número do Game;
- side do Team A quando conhecido;
- champions dos mapas anteriores.

O backend constrói o contexto Fearless a partir de `riot_games_v10`.

O usuário não precisa redigitar manualmente os dez champions usados no G1 para analisar o G2.

---

# Primeiro caso real no banco

O evento HLE × DK continua sendo usado como regression case.

Game 1:

HLE
- Camille
- Lee Sin
- Ryze
- Ziggs
- Alistar

DK
- Olaf
- Jarvan IV
- Twisted Fate
- Yunara
- Lulu

O contexto para Game 2 recupera automaticamente os **10 champions usados**.

O Draft Engine completo continua retornando aproximadamente:

**HLE 55.44%**

para o draft real do G1.

A V14 não alterou esse modelo de produção.

---

# Teste do Strategy Engine

No smoke test de Game 2:

- 10 champions do G1 foram removidos pelo Fearless;
- a ordem Blue/Red foi resolvida;
- candidatos proibidos não apareceram;
- flex foi aplicado principalmente nos primeiros slots;
- denial exigiu familiaridade própria;
- future-pool cost foi ativado quando o candidato era um comfort sem alternativa equivalente;
- Ban Engine removeu champions já indisponíveis.

Também foi encontrado um caso real no dataset em que o custo de pool futuro foi diferente de zero, confirmando que a feature não é apenas decorativa.

---

# Limites metodológicos

A V14 não resolve causalidade de draft.

Não observamos o mundo alternativo em que:

- o time escolheu Jax em vez de Gnar;
- o adversário respondeu de outra maneira;
- e a partida foi jogada.

Portanto:

- V8 probability: modelo validado contra drafts reais;
- V13 recommendation: experimental;
- V14 strategy policy: experimental;
- Ban Engine: experimental.

Essa separação permanece visível na interface.

---

# Próximos passos

## 1. Draft tree / minimax

Hoje cada recomendação testa a ação seguinte.

A evolução natural é pesquisar:

`nosso pick → melhor resposta adversária → nossa resposta`

Isso aproxima o problema de uma árvore de jogo.

## 2. Role uncertainty real

Flex value usa histórico de roles.

O próximo passo é manter múltiplas atribuições possíveis do draft e eliminar hipóteses conforme os picks aparecem.

## 3. Ban + pick joint optimization

Em vez de avaliar bans isoladamente:

`ban phase → opponent remaining pool → pick phase`

## 4. Série como problema dinâmico

O valor ótimo deveria maximizar:

`P(vencer a série)`

e não apenas:

`P(vencer o mapa atual)`

sob champion pools que se esgotam.

## 5. Validação da política

Precisamos de uma metodologia própria para avaliar recommendation/strategy sem usar o próprio modelo como “ground truth”.

Até isso existir, a camada continua Experimental.

---

# Estado do produto após V14

O fluxo é:

**Match → Draft Lab → ordem real → pick/ban strategy → live → resultado → audit**

A diferença entre o produto e um simples dashboard de win rates fica cada vez mais clara:

a plataforma não apenas descreve o draft; ela começa a estruturar **decisões sequenciais sob incerteza**, mantendo explícito o limite entre previsão validada e estratégia simulada.
