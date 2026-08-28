# LCK Predictor V10 — Review completo

## Objetivo da V10

A V10 muda a arquitetura de dados do aplicativo.

Antes, o histórico/modelo era a fonte principal e o acompanhamento live dependia de atualização manual ou leitura visual. A partir da V10, **Riot/LoL Esports passa a ser a fonte primária de identidade da partida, agenda, mapa, patch, draft e estado live**.

A hierarquia é:

1. **Riot LoL Esports web feeds** — agenda, evento, Game ID, estado, draft e live.
2. **Oracle's Elixir / base histórica local** — treino, backtest, ratings e features históricas.
3. **Games of Legends** — carreira, contexto, conferência e preenchimento histórico.
4. **AndyDanger/live-lol-esports e MaisEsports HUB** — referências de implementação/interface; não são raspados quando o feed Riot equivalente está acessível.

Regra nova: **não inferir campeão por ícone da transmissão se o GameMetadata estruturado existir.**

---

## Integrações

### Agenda e eventos

A V10 consulta `getLive`, `getSchedule` e `getEventDetails`.

A agenda guarda:
- partidas ao vivo;
- próximas partidas;
- partidas recentes;
- placar da série;
- Game IDs;
- streams fornecidos pelo evento.

A rotina de agenda busca a página atual e uma página anterior/posterior. Isso melhora cobertura sem fazer crawling agressivo.

### Live stats

Para o mapa atual:
- `livestats/v1/window/{gameId}`
- `livestats/v1/details/{gameId}`

A V10 normaliza e salva:
- patch;
- tempo do mapa;
- side;
- jogador;
- campeão;
- role;
- nível;
- K/D/A;
- CS;
- ouro;
- HP;
- itens/runes quando presentes;
- ouro total;
- kills;
- torres;
- dragões;
- Barons;
- inibidores.

### Polling

Enquanto existe LCK ao vivo:
- descoberta do evento: ~60 s;
- snapshots live: ~10 s;
- agenda: ~5 min;
- backfill de mapas encerrados: ~30 min;
- GoL continua fallback/complemento em cadência muito menor.

A interface consulta o servidor local a cada 10 segundos.

### Twitch / YouTube

A tela Ao vivo usa os `streams` do evento Riot.

- Twitch: embed com `parent=<hostname>`.
- YouTube: iframe.
- sempre há botão para abrir externamente.
- no modo portátil localhost, o player pode sofrer restrições do provedor; os dados Riot continuam independentes do vídeo.

---

## Modelos: o que está realmente validado

### Pré-série — V8 auditado

Produção.

Holdout externo 2026:
- Accuracy: ~69.1%
- Log Loss: ~0.592
- Brier: ~0.204
- ROC-AUC: ~0.739
- calibration slope ~0.98
- ECE ~3.2%

### Draft — núcleo auditado

Produção como probabilidade pré-game após os 10 picks.

Principais sinais:
- força da equipe;
- mastery jogador×campeão com Empirical Bayes;
- sinergia.

Patch/counters permanecem contexto quando não provaram ganho fora da amostra.

### Placar BO3 — V9

Produção como camada de placar:
- placar exato: ~53.5% no teste externo;
- placar real no Top-2: ~78.1%.

### Patch

Contexto. Peso preditivo central = 0.

Motivo: a feature patch-aware parecia boa no desenvolvimento de 2025, mas não melhorou o teste externo de 2026.

### Live — V10

**Experimental. Não calibrado.**

A V10 possui um estimador heurístico para visualização, mas ele é explicitamente marcado como experimental.

O objetivo real desta versão é **coletar snapshots Riot com o vencedor final** para treinar depois um modelo live calibrado.

---

## O que o Game 1 HLE × DK ensinou

Primeiro caso real armazenado:

Patch: 16.16.805.442

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

Draft engine:
- HLE ~55.4%
- intervalo posterior de ~50.9–60.0%

Resultado:
- HLE venceu em 33:59;
- HLE 72,678 × DK 65,945 gold;
- 22 × 16 kills;
- 9 × 4 torres.

Esse único caso **não recalibra nenhuma estatística**.

Ele serviu para identificar a necessidade de features live como:
- gold diff total;
- gold diff por role;
- concentração de ouro;
- número de lanes à frente;
- torre/dragão/Baron/inibidor;
- tempo do mapa;
- composição/draft;
- itens e níveis.

Isso corrige o erro conceitual de tratar “+2k de gold” como uma quantidade universal de vantagem.

---

## Nova interface

Navegação:

- Início
- Ao vivo
- Partidas
- Draft
- Ranking
- Patches
- Validação

### Início

Foco em decisão:
- favorito;
- placar provável;
- chance de Game 3;
- banner ao vivo quando existe snapshot.

### Ao vivo

Mostra na mesma tela:
- stream;
- série/mapa/patch;
- pré-série;
- pós-draft;
- probabilidade live experimental;
- probabilidade atual da série;
- ouro/objetivos;
- jogadores;
- itens;
- draft preenchido automaticamente;
- diferença de ouro por role;
- curva de ouro;
- origem e saúde do feed.

A linguagem “validado” versus “experimental” é visível, não escondida em documentação.

### Partidas

Separação simples:
- Ao vivo
- Próximas
- Recentes

Agenda Riot e modelo probabilístico são conceitos separados.

### Validação

Explica:
- qual camada está em produção;
- qual é contexto;
- qual é experimental;
- métricas fora da amostra;
- hierarquia de fontes.

---

## Estatística: review

Nenhuma métrica histórica foi “melhorada” usando o Game 1 de hoje.

Isso seria leakage / overfitting.

A V10 preserva:
- V8 como referência auditada para vencedor;
- V9 para placar;
- patch com peso zero;
- live sem alegação de calibração.

A próxima avaliação estatística correta será feita quando houver um conjunto novo de partidas/snapshots que não participou da criação do Live Engine.

---

## Limitações técnicas

Os endpoints usados são feeds web públicos do LoL Esports, mas não constituem uma API de desenvolvedor com garantia permanente de estabilidade.

Podem mudar:
- endpoint;
- schema;
- client key pública;
- disponibilidade regional;
- atraso do feed.

Por isso:
- o app mantém cache local;
- registra saúde/erro por fonte;
- não apaga dados bons quando uma consulta falha;
- GoL permanece fallback para resultados/histórico;
- o modelo não depende da Twitch para estatísticas.

---

## Próximas etapas recomendadas

1. Acumular snapshots Riot de todas as séries LCK.
2. Fazer backfill dos mapas encerrados que o feed permitir.
3. Rotular cada snapshot pelo vencedor do mapa.
4. Criar dataset `snapshot → win/loss`.
5. Treinar modelos por janelas de tempo (5/10/15/20/25/30 min) e/ou um único modelo time-aware.
6. Validar rolling-origin por data e série.
7. Calibrar probabilidades.
8. Só então promover Live Probability de EXPERIMENTAL para PRODUCTION.
9. Depois expandir a mesma infraestrutura para LPL/LCK CL sem misturar ratings de ligas de forma ingênua.
