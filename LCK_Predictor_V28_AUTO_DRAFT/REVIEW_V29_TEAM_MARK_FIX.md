# V29 — Correção do selo de time (team-mark)

## Causa
`.team-mark em{position:absolute;...}` (v28.css) sempre renderizava a sigla do
time (`<em>GEN</em>`) por cima da `<img>` do logo, mesmo quando a imagem
carregava com sucesso. O `<em>` era pensado como fallback textual para quando
não há logo disponível, mas nunca era escondido — resultado: sigla sobreposta
ao logo em todo lugar que usa `teamMark()` (ranking de força, linhas de
partidas, hero da partida).

Confirmado comparando `docs/ui_compare/ANTES_v25.png`, `DEPOIS_v29.png` e
`V29_final.png`: o bug sobrevive às três capturas, ou seja, nenhuma rodada de
ajuste anterior da V29 chegou a mexer nisso.

## Fix
- `v28.css`: `.team-mark em{display:none}` por padrão; nova regra
  `.team-mark.broken em{display:block}`.
- `v28.js` (`teamMark`): `onerror` da `<img>` agora tem dois estágios —
  1ª falha troca para o ícone local gerado (`teamIconPath`); 2ª falha (ícone
  local também quebrado) esconde a `<img>` e marca `.team-mark.broken`, que é
  a única situação em que a sigla aparece.
- `index.html`: bump do query param de cache-busting (`V29_MINIMAL_2`) nos
  dois assets pra forçar reload em clientes com cache antigo.

## Verificação
- Servidor local (`server.py`, porta 8828) confirmado servindo o CSS/JS
  atualizados via `curl`.
- Sem Playwright/chromium-cli disponível neste ambiente para screenshot
  automático — checagem visual final pendente de confirmação manual do
  usuário em `http://localhost:8828/`.
