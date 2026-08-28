# V25.1 — Modal Fix

## Causa
O HTML usava o atributo `hidden`, mas a regra CSS:

`.coach-modal-backdrop { display:flex; }`

tinha precedência sobre o estilo padrão do navegador para `[hidden]`.

Assim, o JavaScript fazia `hidden=true`, porém o overlay continuava renderizado.

## Correção
- `.coach-modal-backdrop[hidden] { display:none !important; }`
- fechamento também define `style.display="none"`
- `Esc` fecha o modal
- clique fora continua fechando
- X continua fechando
- body recupera scroll após o fechamento

Foi adicionado um teste de regressão específico.
