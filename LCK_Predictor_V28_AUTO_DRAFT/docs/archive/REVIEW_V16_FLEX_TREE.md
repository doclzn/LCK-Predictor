# LCK Predictor V16 — Flex Tree

## Objetivo

A V15 já simulava `nosso pick → melhor resposta → continuação`, mas cada campeão era imediatamente associado a uma role. Isso distorce picks flex em fases precoces.

A V16 adiciona **Flex Tree**. Novos campeões entram na árvore sem role fixa. A role é resolvida apenas no leaf entre atribuições plausíveis para o roster e o meta.

## Como o leaf é avaliado

Para cada ramo:

1. o app enumera até algumas atribuições plausíveis de role para o time da raiz;
2. enumera atribuições plausíveis do adversário;
3. avalia as combinações com o mesmo V8;
4. o time da raiz recebe sua melhor atribuição plausível;
5. o adversário escolhe a atribuição que mais reduz essa avaliação.

Isso cria um **nested minimax de roles**.

O valor continua experimental: o leaf usa V8 auditado, mas a política de atribuição/busca não é uma nova probabilidade calibrada.

## Exemplo

Em um teste T1 × GEN, picks como Jayce e Sion permaneceram associados a múltiplas roles plausíveis. A interface mostra as hypotheses e também qual atribuição foi escolhida no leaf robusto.

## Performance

Flex uncertainty é mais caro que a árvore fixa. O preset padrão foi reduzido para:

- depth 2;
- beam 2;
- 2 role assignments por lado.

A busca profunda continua disponível, mas o app limita complexidade para evitar travamento.

## Regression

O draft real HLE × DK G1 continua aproximadamente em **HLE 55,44%**, mostrando que a nova camada não altera silenciosamente o V8 de produção.

## Próximo passo

A evolução natural é fazer a árvore incluir também **ban actions** no mesmo search path, em vez de separar Ban Engine e Draft Tree. Assim a pergunta passa a ser:

`ban → melhor resposta de ban/pick → pick → resposta`.
