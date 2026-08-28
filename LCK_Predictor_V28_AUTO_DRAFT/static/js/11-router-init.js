// Draft legado, dispatcher de rotas route() e bootstrap/listeners iniciais
async function renderLegacyDraft(a,b){
  // Redirect to old frontend not possible after rebuild; expose full API-backed draft setup instead.
  setNav("draft");
  page(`<section class="page-head"><div><button class="back-link" onclick="go('draft')">← Draft Lab</button><span class="eyebrow">ANALISADOR AVANÇADO</span><h1>${a} vs ${b}</h1><p>O novo Decision Engine será construído nesta superfície. A API de draft V8/V10 permanece intacta.</p></div></section>
    <section class="panel legacy-transition"><b>Transição de interface</b><p>A V12 preservou o motor de draft, mas removeu a dependência da interface antiga. O próximo passo é reconstruir aqui a seleção pick a pick com sugestões automáticas, em vez de carregar a UI acumulada da V11.</p><button onclick="go('draft')">Voltar ao Draft Lab</button></section>`);
}

let teamAssetsPromise=null;
function ensureTeamAssets(){
  if(S.teamAssets)return Promise.resolve();
  if(!teamAssetsPromise)teamAssetsPromise=api("/api/v12/team_assets").then(d=>{S.teamAssets=d||{}}).catch(()=>{S.teamAssets={}});
  return teamAssetsPromise;
}

async function route(){
  if(S.liveTimer){clearInterval(S.liveTimer);S.liveTimer=null}
  await ensureTeamAssets();
  const raw=(location.hash||"#home").slice(1), [path,query=""]=raw.split("?");
  const h=path.split("/"),name=h[0]||"home";
  try{
    if(name==="home")return await renderHome();
    if(name==="matches")return await renderMatches(h[1]);
    if(name==="match")return await renderMatch(decodeURIComponent(h.slice(1).join("/")));
    if(name==="draft")return await renderDraft(h[1]?decodeURIComponent(h[1]):null,h[2]?decodeURIComponent(h[2]):null,query);
    if(name==="explore")return await renderExplore(h[1]||"teams",h[2]);
    if(name==="model")return await renderModel();
    if(name==="legacy-draft")return await renderLegacyDraft(h[1],h[2]);
    if(name==="legacy-patches")return await renderExplore("patches");
    if(name==="live"){
      // Unified match navigation: if an event id exists, route to the same match page.
      if(h[1])return go(`match/${encodeURIComponent("riot:"+h[1])}`);
      return await renderMatches("live");
    }
    return await renderHome();
  }catch(e){console.error(e);errorCard(e)}
}

// Tooltip global para .wr-tip: um único elemento fixo na <body>, para não
// ser cortado por containers com overflow:hidden (ex.: hero-match).
(function(){
  const tip=document.createElement("div");
  tip.id="wrTooltip";tip.setAttribute("role","tooltip");
  document.body.appendChild(tip);
  let current=null;
  function place(el){
    tip.textContent=el.dataset.tip||"";
    tip.classList.add("show");
    tip.style.visibility="hidden";tip.style.left="0px";tip.style.top="0px";
    requestAnimationFrame(()=>{
      const r=el.getBoundingClientRect(),tr=tip.getBoundingClientRect();
      let left=r.left+r.width/2-tr.width/2;
      left=Math.max(8,Math.min(left,window.innerWidth-tr.width-8));
      let top=r.top-tr.height-10,below=false;
      if(top<8){top=r.bottom+10;below=true}
      tip.style.left=left+"px";tip.style.top=top+"px";
      tip.classList.toggle("wr-tooltip-below",below);
      tip.style.setProperty("--arrow-x",(r.left+r.width/2-left)+"px");
      tip.style.visibility="visible";
    });
  }
  function hide(){tip.classList.remove("show");current=null}
  document.addEventListener("mouseover",e=>{const el=e.target.closest(".wr-tip");if(el&&el!==current){current=el;place(el)}});
  document.addEventListener("mouseout",e=>{const el=e.target.closest(".wr-tip");if(el&&!el.contains(e.relatedTarget))hide()});
  document.addEventListener("focusin",e=>{const el=e.target.closest(".wr-tip");if(el){current=el;place(el)}});
  document.addEventListener("focusout",e=>{if(e.target.closest(".wr-tip"))hide()});
  window.addEventListener("scroll",hide,true);
})();

$("#themeBtn").onclick=()=>{S.theme=S.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=S.theme;localStorage.setItem("lck-theme",S.theme)}
$("#menuBtn").onclick=()=>$("#navShell").classList.toggle("open");
window.addEventListener("hashchange",route);
verifyVersionV28().then(ok=>{if(ok)route()});


// V26: no service worker. Clear any legacy caches/registrations from older builds.
if("serviceWorker" in navigator){
  navigator.serviceWorker.getRegistrations().then(rs=>rs.forEach(r=>r.unregister())).catch(()=>{});
}
if("caches" in window){
  caches.keys().then(keys=>Promise.all(keys.map(k=>caches.delete(k)))).catch(()=>{});
}
