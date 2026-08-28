# LCK Predictor V12 — Product Rebuild

## Resumo

A V12 não é uma nova feature em cima da V11.

É a primeira reconstrução da experiência do produto em torno de cinco entidades claras:

1. **Home**
2. **Matches**
3. **Draft Lab**
4. **Explore**
5. **Model**

O backend V8–V11, o banco, o Riot collector, o Prediction Journal e os modelos foram preservados.

O frontend acumulado foi substituído por uma nova interface (`v12.js` + `v12.css`).

---

# 1. Princípio central: a partida é a entidade

Antes da V12 existiam superfícies separadas para:

- próximos jogos;
- live;
- histórico;
- análise de partida;
- auditoria.

Na V12, a URL/página de uma partida muda de estado.

## Pré-jogo

Mostra:

- probabilidade da série;
- favorito;
- intensidade da vantagem;
- scoreline 2–0 / 2–1;
- chance de Game 3;
- leitura resumida;
- acesso ao Draft Lab.

## Ao vivo

A mesma página passa a incluir:

- Riot live feed;
- mapa;
- patch;
- ouro;
- kills;
- torres;
- dragões;
- Baron;
- inibidores;
- jogadores;
- campeões;
- K/D/A;
- CS;
- gold individual;
- draft automático;
- pré-série;
- pós-draft;
- live experimental;
- série atual;
- gold diff por role;
- timeline de gold;
- stream Twitch/YouTube quando o evento fornece.

A página atualiza aproximadamente a cada 10 segundos.

## Pós-jogo

A mesma entidade passa a mostrar:

- resultado;
- o que sabíamos antes;
- acerto/erro;
- Brier;
- Log Loss;
- mapas;
- drafts;
- stats;
- forecasts arquivados quando existem;
- baseline reconstruído para histórico anterior ao Prediction Journal.

Essa mudança reduz bastante a fragmentação da interface.

---

# 2. Nova navegação

## Home

Responde rapidamente:

- existe LCK ao vivo?
- qual o próximo confronto importante?
- quem é favorito?
- quais são os próximos jogos?
- como está o ranking?
- qual o desempenho auditado do modelo?

A Home foi desenhada para priorizar decisão, não métricas técnicas.

## Matches

Três estados:

- Próximas
- Ao vivo
- Resultados

Não há mais necessidade de uma aba Histórico principal separada: resultado/histórico é um estado de Matches.

## Draft Lab

Reconstruído na V12.

Agora possui:

- Team A / Team B;
- side;
- patch;
- Fearless já usado;
- cinco picks de cada time;
- champion pool rápido por jogador;
- análise real via `/api/draft/evaluate`.

Resultado mostra:

- baseline do mapa;
- probabilidade pós-draft;
- delta em pontos percentuais;
- intervalo posterior 80%;
- cobertura dos dados;
- mastery EB lane a lane;
- H2H contextual;
- synergy;
- patch overlay experimental;
- alerta de draft ilegal no Fearless.

O motor estatístico continua sendo o V8 auditado.

## Explore

Subáreas:

- Teams
- Players
- Champions
- Patches

### Player Explorer

Exemplo: ShowMaker.

Mostra:

- time/role;
- record overall;
- prior Empirical Bayes;
- champion pool de carreira quando existe cobertura web;
- champion pool 2026;
- jogos recentes;
- KDA;
- GD@15;
- DPM.

### Champion Explorer

Exemplo: Ahri MID.

Mostra:

- WR ajustado;
- games;
- GD@15;
- especialistas;
- player×champion;
- recorte por patch.

### Team Explorer

Mostra:

- Elo;
- rank;
- last-5 / last-10;
- roster;
- séries recentes.

## Model

Substitui "Validação" como linguagem de produto.

Mostra:

- Accuracy;
- Log Loss;
- Brier;
- AUC;
- ECE;
- camadas Production / Context / Experimental;
- saúde das fontes;
- política de forecast arquivado versus reconstruído.

---

# 3. Benchmark Draft Helper

O Draft Helper continua sendo uma referência importante de amplitude.

Pontos em que ele ainda é mais maduro:

- quantidade de ferramentas prontas;
- filtros históricos mais amplos;
- champion/player explorers mais extensos;
- draft workflow amadurecido;
- H2H e lane matchup dedicados;
- alertas/bot;
- cobertura histórica maior.

A V12 começa a atacar nossa principal fraqueza anterior: **consistência de produto**.

## Onde queremos superar

O objetivo não é apenas mostrar mais estatísticas.

O diferencial pretendido é:

**partida → forecast → draft → live → resultado → auditoria**

com cada probabilidade preservada no momento em que existiu.

Isso permite responder:

- O modelo estava certo antes do jogo?
- O draft melhorou ou piorou a previsão?
- Quando a probabilidade virou?
- O live model ficou overconfident?
- Qual faixa de probabilidade é melhor calibrada?
- Qual feature mais mudou a leitura?
- Qual modelo estava ativo naquele momento?

---

# 4. Estado estatístico preservado

A V12 não altera as métricas de produção apenas por causa dos jogos de hoje.

## V8 — vencedor / pré-jogo

Produção.

Teste externo 2026 aproximadamente:

- Accuracy: 69.1%
- Log Loss: 0.592
- Brier: 0.204
- ROC-AUC: 0.739
- calibration slope: ~0.98
- ECE: ~3.2%

## V9 — scoreline BO3

Produção.

- exact score: ~53.5%
- score real no Top-2: ~78.1%

## Patch

Contexto.

Peso central: 0.

## Live

Experimental.

A V12 coleta e exibe, mas não vende o estimador heurístico como calibrado.

---

# 5. Histórico disponível na build

Arquivo atual:

- 375 séries LCK;
- 2025–2026;
- 343 séries com baseline pré-jogo reconstruível;
- 50 jogadores no roster atual;
- 149 registros champion×role do recorte 2026 na tela principal.

A interface foi preparada para histórico maior, mas a build não chama 2025–2026 de "all-time".

O próximo passo de dados é importar temporadas LCK anteriores de forma compacta, mantendo:

- results;
- game stats;
- players;
- champions;
- drafts quando disponíveis;
- sem misturar automaticamente dados antigos no modelo atual.

---

# 6. Review técnico da reconstrução

## Dívida removida

A V11 acumulava uma interface criada ao longo de várias versões.

Na V12:

- `static/app.js` removido;
- `static/app.css` removido;
- novo `static/v12.js`;
- novo `static/v12.css`;
- nova `index.html`.

Backend e modelo não foram reescritos sem necessidade.

## Runtime Windows

A correção V10.1 foi preservada:

- `server.py` inclui explicitamente `APP_DIR` no `sys.path`;
- launcher verifica `riot_feed.py`;
- runtime Python embutido continua suportado.

---

# 7. Testes finais executados

- sintaxe Python: OK
- sintaxe JavaScript: OK
- Home API: OK
- Matches API: OK
- Player Explorer: OK
- Champion Explorer: OK
- Team Explorer: OK
- historical unified match: OK
- Riot unified match: OK
- Draft Lab / evaluate: OK
- runtime portable import fix: OK

Caso real utilizado no smoke test:

HLE:
- Camille
- Lee Sin
- Ryze
- Ziggs
- Alistar

DK:
- Olaf
- Jarvan IV
- Twisted Fate
- Yunara
- Lulu

Resultado do Draft Engine:

**HLE 55.44%**
cobertura **68/100**.

---

# 8. Próximos passos que mais aumentam o valor do produto

Ordem recomendada:

1. **LCK historical expansion**
   - importar 2015–2024 / máximo disponível;
   - compactar para arquivo de produto.

2. **Draft Decision Engine**
   - escolher 1–9 picks;
   - enumerar respostas legais;
   - ranquear respostas pelo delta probabilístico;
   - respeitar Fearless;
   - separar recomendação com alta/baixa cobertura.

3. **Live Model treinado**
   - acumular snapshots;
   - rotular vencedor;
   - rolling-origin;
   - calibration;
   - só então promover para Production.

4. **H2H Explorer**
   - team H2H;
   - player lane H2H;
   - matchup champion×champion.

5. **Backend cloud**
   - PostgreSQL;
   - worker Riot separado;
   - SSE/WebSocket;
   - Prediction Journal append-only persistente.

6. **Notificações**
   - draft começou;
   - partida começou;
   - mudança relevante de probabilidade;
   - resultado + auditoria.

---

# Visão de produto

A proposta central da V12 é:

> **Veja a partida. Entenda o forecast. Analise o draft. Acompanhe ao vivo. Volte depois e audite o modelo.**

Essa é a direção em que o LCK Predictor pode deixar de ser apenas um "draft helper" e se tornar uma plataforma de inteligência competitiva.
