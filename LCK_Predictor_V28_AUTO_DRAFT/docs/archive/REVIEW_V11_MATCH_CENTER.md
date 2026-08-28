# LCK Predictor V11 — Match Center & Historical Audit

## Por que esta versão existe

A V10 resolveu o presente: Riot feed, draft automático, snapshots live e stream.

A V11 resolve o **tempo inteiro da liga** dentro da plataforma:

- passado;
- presente;
- futuro.

E adiciona uma diferença importante em relação a dashboards estatísticos tradicionais: o pós-jogo não mostra apenas o resultado. Ele mostra **o que o modelo sabia antes do resultado** e compara previsão versus realidade.

## Inspiração e benchmark de produto

O Draft Helper foi usado como benchmark de amplitude, não como interface a ser copiada.

Na revisão pública de 20/08/2026 ele oferece, entre outros recursos:

- Match History;
- filtros por liga/split/time/player/role/champion;
- Draft Simulator;
- Draft Analysis;
- Head to Head;
- Team History;
- Live Game Drafts;
- Live Game Stats;
- champion win rates;
- synergy;
- lane H2H matchups;
- dragons;
- bot/alertas.

Isso deixa claro que nossa plataforma ainda precisa ganhar amplitude em algumas áreas.

A estratégia do LCK Predictor não é simplesmente reproduzir esses painéis. É combinar essa amplitude com **auditabilidade probabilística e origem dos dados**.

## O que entrou na V11

### 1. Aba Histórico

A navegação agora separa:

- **Partidas** — ao vivo e futuro;
- **Histórico** — séries encerradas e auditoria.

O arquivo local atual contém **375 séries LCK de 2025–2026**.

Dessas, **343 possuem snapshot pré-série cronológico suficiente** para reconstruir o baseline Elo.

Importante: isso ainda **não é o histórico all-time da LCK**. A arquitetura está preparada para adicionar temporadas anteriores, mas a build não finge possuir dados que ainda não foram importados.

### 2. O que sabíamos antes

Para jogos antigos existem duas categorias claramente separadas:

**Forecast arquivado**

É o número realmente salvo pela plataforma naquele momento.

**Baseline reconstruído**

Para séries anteriores ao Prediction Journal, usamos somente o Elo pré-série que já estava armazenado cronologicamente.

Resultado, draft e estatísticas futuras não entram.

A interface mostra explicitamente “reconstruído” para evitar hindsight.

### 3. Prediction Journal

Nova tabela append-only:

`prediction_journal_v11`

Ela começa a preservar:

- pré-série;
- pós-draft;
- snapshots live experimentais;
- versão do modelo;
- status de validação;
- contexto;
- origem.

Para as próximas partidas será possível abrir o pós-jogo e enxergar a sequência real:

`pré-série → draft → live → final`.

### 4. Auditoria por partida

A página de uma série encerrada mostra:

- vencedor;
- placar;
- favorito pré-jogo;
- probabilidade atribuída ao vencedor real;
- se o favorito acertou;
- Brier da previsão;
- Log Loss;
- surpresa (`-log(P do vencedor)`);
- cobertura de dados.

Quando game-level stats existem, mostra também:

- patch;
- side;
- kills;
- ouro;
- torres;
- dragões;
- Barons;
- GD@15;
- picks e jogadores.

### 5. Jogos Riot coletados

Para partidas capturadas pela V10/V11 a página pode ser mais rica:

- forecast original pré-série;
- forecast original pós-draft;
- snapshots live;
- curva de ouro;
- KDA/CS/ouro final;
- draft;
- resultado.

O Game 1 HLE × DK é o primeiro case study real.

### 6. Histórico + atual + futuro

A V11 usa duas superfícies:

**Partidas**
- ao vivo;
- próximas;
- recentes via Riot.

**Histórico**
- arquivo local;
- filtros por ano/time;
- acertos/erros;
- busca;
- detalhes pós-jogo.

O feed Riot continua expandindo a agenda e cache de eventos conforme o app roda.

## Estatísticas reavaliadas do arquivo histórico

Para o baseline Elo reconstruído, nas séries que têm snapshot pré-jogo:

- 343 séries avaliáveis;
- Accuracy: ~74.3%;
- Brier: ~0.179;
- Log Loss: ~0.537;
- Upset rate: ~25.7%.

Esses números **não substituem** o V8 auditado. São métricas de um baseline histórico de séries exibido no Match Center.

Essa distinção é importante.

## O que ainda falta para superar Draft Helper em amplitude

A V11 fica mais forte em auditoria probabilística, mas o Draft Helper ainda é mais amplo em algumas áreas.

Prioridades objetivas:

1. importar temporadas LCK anteriores a 2025 para um arquivo all-time;
2. Player Explorer e Champion Explorer unificados;
3. H2H de lane em interface dedicada;
4. páginas de times mais profundas;
5. draft history completo com bans e ordem de picks;
6. meta global LCK/LPL/LCK CL validado sem misturar ligas de forma ingênua;
7. nuvem/PWA hospedada com banco persistente;
8. alertas de draft/live;
9. modelagem live calibrada a partir dos snapshots que a V10/V11 estão acumulando.

## Diferencial que devemos preservar

A plataforma não deve virar um painel que mostra dezenas de números sem explicar confiança e origem.

A proposta de produto deve ser:

**Veja a partida → entenda a previsão → saiba quais dados sustentam a previsão → acompanhe ao vivo → volte depois e audite se o modelo estava certo.**

Esse ciclo completo é a direção central do produto.
