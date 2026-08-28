// Núcleo do roteador SPA: go(), setNav(), page(), loading(), errorCard()

function go(route){location.hash="#"+route}
window.go=go;
function setNav(name){$$(".primary-nav button").forEach(b=>b.classList.toggle("active",b.dataset.nav===name));$("#crumb").textContent={home:"Home",matches:"Matches",draft:"Draft Lab",explore:"Explore",model:"Model"}[name]||"LCK Predictor"}
function page(html){$("#page").innerHTML=html;window.scrollTo(0,0)}
function loading(){page(`<div class="loading"><span></span>Carregando…</div>`)}
function errorCard(e){page(`<section class="empty-panel"><b>Não consegui carregar esta tela.</b><p>${esc(e.message||e)}</p><button onclick="location.reload()">Tentar novamente</button></section>`)}
