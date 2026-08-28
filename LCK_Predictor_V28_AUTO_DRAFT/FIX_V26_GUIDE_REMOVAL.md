# V26 — remoção definitiva do Guia

A V25.2 realmente não continha mais o código do Guia no ZIP. O motivo de ele continuar
aparecendo era operacional: V25, V25.1 e V25.2 usavam a mesma porta 8825. Se a instância
V25 antiga continuasse aberta, o navegador permanecia conectado a ela.

A V26 resolve isso com:
- porta exclusiva 8826;
- APP_VERSION V26_CLEAN_UI;
- novos assets v26.js/v26.css;
- assets antigos removidos do pacote;
- sem registro de service worker;
- caches antigos apagados no carregamento;
- CSS defensivo que torna qualquer coach/guide invisível;
- prova visual no topo: `V26 • PORTA 8826 • SEM GUIA`.
