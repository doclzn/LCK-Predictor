# LCK Predictor V13 — Decision Engine

## O salto da V13

A V12 reorganizou o produto.

A V13 começa a transformar o Draft Lab de uma ferramenta que **avalia o que você escolheu**
em uma ferramenta que também ajuda a responder:

> **“Qual deveria ser o próximo pick?”**

Isso é propositalmente separado em duas camadas:

### Motor de probabilidade

**V8 audited draft core**

Usado para estimar a probabilidade do mapa dado o estado do draft.

### Política de recomendação

**V13 Decision Engine — EXPERIMENTAL**

Compara vários candidatos legais e ordena as alternativas.

A segunda camada não é chamada de Production apenas porque usa um modelo de probabilidade validado.

---

# 1. Como o Decision Engine funciona

Entrada:

- Team A / Team B
- side
- patch
- picks já feitos
- champions usados no Fearless
- lado que fará o próximo pick
- role do próximo pick

Para o jogador daquela role, o Candidate Generator combina:

1. champion pool 2026 do jogador;
2. histórico local 2025–2026;
3. champions relevantes do meta 2026 naquela role.

Depois remove:

- champions já pickados;
- champions bloqueados pelo Fearless.

Cada candidato é colocado no draft atual e enviado ao **mesmo Draft Engine V8**.

O resultado contém:

- `probability_target_team`
- `delta_target_pp`
- mastery Empirical Bayes
- meta sample
- evidence score
- matchup context
- synergy context

---

# 2. Correção feita durante o review

O primeiro smoke test mostrou um risco:

> um campeão com pouca experiência do jogador podia subir demais no ranking
> por causa da probabilidade bruta de uma combinação teórica.

A V13 não altera a probabilidade V8.

Em vez disso, cria uma camada separada para **ordenar recomendações**.

## Recommendation-policy shrinkage

A mudança de probabilidade do candidato é puxada de volta para o estado atual quando há pouca evidência.

A confiança da política considera:

- número de games do jogador no champion;
- volume do champion no meta da role;
- evidence score do Draft Engine.

Conceitualmente:

`decision_delta = raw_delta × policy_confidence`

Assim, o produto consegue mostrar ao mesmo tempo:

- **Modelo:** o que o V8 estima para esse draft;
- **Δ decisão:** quanto desse ganho merece ser usado para ordenar recomendações considerando a evidência.

Isso evita esconder a probabilidade bruta e evita tratar um pick quase sem amostra como equivalente a um comfort pick.

---

# 3. Exemplo de teste

Estado parcial usado no smoke test:

HLE:
- Camille
- Lee Sin
- Ryze
- Ziggs
- Support em aberto

DK:
- Olaf
- Jarvan IV
- Twisted Fate
- Yunara
- Lulu

O Decision Engine conseguiu:

- identificar Delight como jogador da role;
- excluir Lulu porque já estava usada;
- buscar candidatos de player pool + meta;
- executar o V8 para cada candidato;
- aplicar shrinkage apenas no ranking;
- retornar uma shortlist.

O objetivo do teste NÃO foi provar qual support “teria vencido”.

Counterfactual de draft não é diretamente observável em uma partida real.

---

# 4. Por que Recommendation continua Experimental

Um modelo pós-draft pode ser validado contra resultados reais:

`draft real → vencedor real`

Uma política de recomendação é diferente.

Para provar que:

> “pick A é melhor do que pick B”

precisaríamos observar resultados sob drafts alternativos que nunca aconteceram, ou usar um desenho experimental/causal muito mais complexo.

Portanto, não vamos produzir uma falsa métrica de “accuracy das recomendações” usando o próprio modelo que gerou as recomendações.

A V13 mantém isso explícito.

---

# 5. Próximas evoluções do Decision Engine

## A. Pick order

Representar B1/R1-R2/B2-B3 etc., não apenas champions já escolhidos.

Isso permitirá distinguir:

- blind pick;
- response;
- counterpick;
- flex;
- information advantage.

## B. Ban engine

Avaliar:

- ban value;
- opponent comfort denial;
- role scarcity;
- Fearless interaction.

## C. Flex value

Um champion que pode ocupar duas roles mantém informação escondida.

Isso deve aparecer como feature estratégica separada, em vez de apenas win rate.

## D. Pool exhaustion

Em Fearless, o valor de uma escolha depende também do que ela remove dos mapas futuros.

Uma escolha ótima para o Game 1 pode ser pior para uma série inteira.

O modelo futuro deve estimar:

`value(current game) + expected value(future games)`

## E. Recommendation track record

A plataforma já grava `draft_decision_log_v13`.

Isso permitirá estudar futuramente:

- frequência das recomendações;
- cobertura média;
- quantas eram comfort picks;
- estabilidade entre patches;
- como a política muda após novas evidências.

---

# 6. Histórico all-time

A V13 adiciona:

- `lck_alltime_games_v13`
- `lck_alltime_player_games_v13`
- `lck_alltime_series_v13`
- `history_import_manifest_v13`

e o script:

`scripts/import_lck_history.py`

Mais o launcher:

`IMPORTAR_HISTORICO_LCK.bat`

## Importador

Aceita arquivos CSV estilo Oracle's Elixir obtidos localmente.

Ele:

1. filtra `league == LCK`;
2. separa team rows e player rows;
3. normaliza roles;
4. cria games;
5. preserva player/champion/KDA/gold/early stats;
6. reconstrói séries;
7. registra cobertura por arquivo/ano.

## Separação de eras

O arquivo histórico **não entra automaticamente no modelo 2026**.

Primeiro uso:

- histórico;
- Player Explorer;
- Champion Explorer;
- H2H;
- lane matchup;
- career stats.

Só depois de validação específica uma feature histórica pode entrar no modelo atual.

---

# 7. Política de fontes históricas

A build NÃO redistribui automaticamente um corpus antigo adicional.

O importador está pronto para arquivos que o usuário tenha direito de utilizar.

Isso é intencional por dois motivos:

1. arquivos históricos são grandes;
2. termos/licenças de bases de terceiros precisam ser respeitados antes de transformar o protótipo em produto público/comercial.

A base 2025–2026 que já existia no projeto continua no snapshot de desenvolvimento.

---

# 8. Testes executados

### Sintaxe

- Python: OK
- JavaScript: OK

### Draft regression

Draft real G1 HLE × DK:

- HLE Camille
- Kanavi Lee Sin
- Zeka Ryze
- Gumayusi Ziggs
- Delight Alistar
- DK Olaf / Jarvan IV / Twisted Fate / Yunara / Lulu

Resultado do Draft Engine:

**HLE 55.44%**

O valor permanece consistente após a V13.

### Decision Engine

Teste de support HLE em draft parcial:

- candidatos legais gerados;
- champion já usado removido;
- V8 executado candidato a candidato;
- evidence shrinkage aplicado;
- log persistente criado.

### Historical importer

Fixture Oracle-style 2019:

- 2 mapas;
- 20 player rows;
- reconstrução correta em uma série 2–0.

---

# 9. Direção de produto

O objetivo continua:

> **Veja a partida → entenda o forecast → construa o draft → receba apoio de decisão → acompanhe live → audite depois.**

A V13 começa a adicionar a parte que faltava:

> **“e se escolhermos outro campeão?”**

sem confundir uma simulação contrafactual com evidência causal real.
