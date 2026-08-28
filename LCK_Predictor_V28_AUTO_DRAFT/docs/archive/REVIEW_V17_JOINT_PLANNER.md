# LCK Predictor V17 — Joint Ban→Pick Planner

A V17 deixa de tratar Ban Engine e Draft Tree como universos separados.

Ela usa a sequência profissional completa:

`B1BAN R1BAN B2BAN R2BAN B3BAN R3BAN → B1 R1 R2 B2 B3 R3 → R4BAN B4BAN R5BAN B5BAN → R4 B4 B5 R5`

Em nós de ban, o sistema usa comfort denial, meta, flex e escassez para criar um beam de bans. O ban em si **não ganha uma win probability inventada**. Seu valor aparece apenas porque remove opções legais dos nós de pick seguintes.

Em nós de pick, a árvore usa o motor flex-aware V16: novos champions podem permanecer sem role fixa até o leaf.

O minimax continua adversarial: o lado da raiz maximiza o leaf V8; o adversário escolhe o ramo que mais reduz a avaliação.

## Regression case

No contexto HLE 1–0 DK antes do G2, a busca iniciada em `R3BAN` conseguiu atravessar `ban → B1 pick → R1 response`, respeitando os 10 champions já indisponíveis pelo Fearless.

## Limite

O score robusto continua sendo planejamento baseado em modelo. Não é uma probabilidade calibrada nova e não prova causalmente que um ban seria superior no mundo real.

## Próxima evolução

O passo seguinte é trocar a função-objetivo: em vez de ordenar decisões apenas pelo mapa atual, estimar o **valor para vencer a série**, considerando o placar atual e a profundidade restante do champion pool no Fearless.
