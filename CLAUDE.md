# Estado provisório — refatoração de CSS em andamento

As regras de eficiência de token deste arquivo foram **suspensas em 2026-08-29**
para permitir o achatamento das camadas de design (08–16). Elas eram a causa
direta do empilhamento: "menor edição direcionada" somado a "não verifique o
resultado" torna acrescentar um override no fim da cascata a ação mais barata, e
corrigir a regra de origem a mais cara. O original está em `git show HEAD:CLAUDE.md`.

Restaurar quando a refatoração terminar — mas sem as regras marcadas como CAUSA.

# Arquitetura de CSS (regra permanente, não suspender)

- `:root` existe em **um único arquivo**: `static/css/00-tokens.css`. Nenhum
  outro arquivo define variável de tema.
- Mudança de aparência se faz **no arquivo do componente**. É proibido criar
  arquivo de versão nova (`17-...`) ou apender override no fim da cascata.
- Se uma regra precisa de `!important` para vencer, a concorrente está no
  arquivo errado — mova a regra, não escale a especificidade.
- Uma direção de design de cada vez. Não pode existir "sistema de design ATUAL"
  em dois arquivos ao mesmo tempo.

# Idioma

- Responder sempre em português do Brasil. Código, comandos, caminhos,
  identificadores e nomes técnicos ficam no idioma original.

# Escopo

- A aplicação está em `LCK_Predictor_V28_AUTO_DRAFT/` e roda em
  `http://127.0.0.1:8828/`.
- Buscar apenas dentro de `LCK_Predictor_V28_AUTO_DRAFT/`. Nunca varrer a raiz
  do workspace nem ler arquivos grandes/minificados por inteiro.

# Regras suspensas (restaurar ao fim da refatoração)

- Usar low effort por padrão; nunca elevar sem pedido explícito.
- Agrupar edições relacionadas no mínimo de chamadas praticável.
- Não repetir abordagens que já falharam. Após cinco tool calls sem solução
  clara, parar e perguntar.
- Se o contexto ficar grande, recomendar sessão nova com handoff conciso.

# Regras removidas — CAUSA do layer-cake, não restaurar

- ~~"Para mudanças rotineiras de UI ou CSS, faça a menor edição direcionada."~~
- ~~"Não invoque skills, subagentes, navegadores, screenshots ou automação visual."~~
- ~~"Não releia um arquivo após uma edição e não verifique o servidor local."~~
- ~~"Para UI de home e topo, inspecionar `05-page-home.js`, `15-topnav-modern.css`,
  `01-base-shell.css` antes de procurar em outro lugar."~~ — apontava para a
  camada mais recente, ensinando a empilhar mais uma.
