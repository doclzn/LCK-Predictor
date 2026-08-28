// Construção de cards/linhas de partida reutilizados em Home e Matches

function matchProbability(m){
  // Numa série em andamento o placar já é informação certa: a leitura vale
  // mais que a pré-jogo congelada. Fora disso, a pré-jogo é a única que existe.
  if(m.probability_team1_now!=null)return Number(m.probability_team1_now);
  if(m.probability_team1!=null)return Number(m.probability_team1);
  if(m.pregame_elo_p_team1!=null)return Number(m.pregame_elo_p_team1);
  return null;
}
function matchPregameProbability(m){
  const v=m.pregame_probability_team1!=null?m.pregame_probability_team1:m.probability_team1;
  return v==null?null:Number(v);
}
/** Mostra de quanto a série moveu desde a leitura pré-jogo, na ótica do favorito atual. */
function pregameShift(m,favTeam){
  const now=matchProbability(m),pre=matchPregameProbability(m);
  if(now==null||pre==null||m.probability_team1_now==null)return "";
  const preFav=favTeam===m.team1?pre:1-pre;
  const nowFav=favTeam===m.team1?now:1-now;
  if(Math.abs(nowFav-preFav)<.005)return "";
  const up=nowFav>preFav;
  return `<i class="pre-shift ${up?"up":"down"}" title="Leitura antes da série começar">${up?"↑":"↓"} era ${pct(preFav)}</i>`;
}
function matchId(m){
  if(m.id)return m.id;
  return `upcoming:${String(m.date).slice(0,10)}:${m.team1}:${m.team2}`;
}
function matchRow(m,compact=false){
  const p=matchProbability(m),fav=p==null?null:favorite(p,m.team1,m.team2);
  const score=(m.wins1!=null&&m.wins2!=null)?`${m.wins1}–${m.wins2}`:"vs";
  const state=m.status||"upcoming";
  return `<button class="match-row ${compact?"compact":""}" onclick="go('match/${encodeURIComponent(matchId(m))}')">
    <div class="match-time"><b>${String(m.date||"").includes("T")?dateText(m.date):dayText(m.date)}</b><span>${m.block_name||"LCK"}</span></div>
    <div class="match-teams">
      <div>${teamMark(m.team1,true)}<b>${esc(m.team1)}</b></div>
      <strong>${score}</strong>
      <div class="right"><b>${esc(m.team2)}</b>${teamMark(m.team2,true)}</div>
    </div>
    <div class="match-read">${fav?`<small>Favorito</small><b>${esc(fav.team)} ${pct(fav.p)}</b><span>${advantage(p)}${pregameShift(m,fav.team)}</span>`:`<small>${statusLabel(state)}</small><b>—</b>`}</div>
    <span class="row-status ${state}">${state==="live"?(m.live_confidence==="schedule_fallback"?"● LIVE · SYNC":"● LIVE"):state==="completed"?"FINAL":"VER"}</span>
  </button>`;
}


function findFeaturedGuideMatch(d){
  const all=[...(d?.live||[]),...(d?.upcoming||[])];
  return all.find(m=>["T1","KT"].includes(code(m.team1))||["T1","KT"].includes(code(m.team2))) || all[0] || null;
}
function quickStartPanel(d){
  const g=findFeaturedGuideMatch(d);
  const title=g?`${esc(g.team1)} vs ${esc(g.team2)}`:"Abrir e acompanhar a próxima partida";
  const when=g?`${dateText(g.date)} · ${g.block_name||"LCK"}`:"Use as abas abaixo para ir direto ao jogo.";
  const route=g?`match/${encodeURIComponent(matchId(g))}`:"matches/upcoming";
  return `<section class="panel quickstart-panel">
    <div class="quickstart-head">
      <div><span class="eyebrow">GUIA RÁPIDO</span><h2>Como usar no próximo jogo</h2><p>Fluxo simples para acompanhar o jogo sem se perder nas telas técnicas.</p></div>
    </div>
    <div class="quick-actions-grid">
      <button class="quick-action primary" onclick="go('${route}')"><small>ABRIR PARTIDA</small><strong>${title}</strong><span>${when}</span></button>
      <button class="quick-action" onclick="go('matches/live')"><small>AO VIVO</small><strong>Ver jogo ao vivo</strong><span>placar, draft, ouro, torres, dragões e leitura do jogo</span></button>
      <button class="quick-action" onclick="go('draft')"><small>DRAFT LAB</small><strong>Analisar picks e bans</strong><span>use antes do jogo e durante o draft</span></button>
      <button class="quick-action" onclick="go('matches/results')"><small>HISTÓRICO</small><strong>Comparar previsão x resultado</strong><span>veja como a plataforma performou</span></button>
    </div>
  </section>`;
}




function scheduleStatusV23(d){
  const s=d?.schedule_status||{};
  const last=s.last_success?dateText(s.last_success):"cache local";
  const hidden=Number(s.stale_events_hidden||0)+Number(s.stale_rows_removed||0);
  return `<div class="schedule-status-v23">
    <div><i class="${s.status==="ok"?"ok":"cache"}"></i><span><small>AGENDA RIOT</small><b>${s.status==="ok"?"atualizada":"cache local"}</b><em>${last}${hidden?` · ${hidden} item(ns) antigo(s) ocultado(s)`:""}</em></span></div>
    <button onclick="refreshScheduleV23(this)">↻ Atualizar agora</button>
  </div>`;
}
window.refreshScheduleV23=async function(btn){
  const old=btn?.textContent;
  if(btn){btn.disabled=true;btn.textContent="Atualizando…"}
  try{
    const r=await post("/api/v23/schedule/refresh",{});
    toast(r.ok?"Agenda atualizada":"Riot indisponível; usando cache limpo");
  }catch(e){
    toast("Não consegui consultar a Riot agora; cache antigo continuará oculto.");
  }finally{
    if(btn){btn.disabled=false;btn.textContent=old||"↻ Atualizar agora"}
    await route();
  }
}
function upcomingDayLabelV23(x){
  const s=String(x||"").slice(0,10);
  if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(s))return dateText(x);
  const [y,m,d]=s.split("-").map(Number);
  return `${String(d).padStart(2,"0")}/${String(m).padStart(2,"0")}`;
}
function groupedUpcomingV23(items,limit=8){
  const rows=(items||[]).slice(0,limit);
  if(!rows.length)return `<div class="empty-inline">Nenhuma partida futura no cache. Clique em “Atualizar agora”.</div>`;
  let last="",out="";
  rows.forEach(x=>{
    const day=String(x.date||"").slice(0,10);
    if(day!==last){
      out+=`<div class="match-day-divider-v23"><span>${upcomingDayLabelV23(x.date)}</span><i></i></div>`;
      last=day;
    }
    out+=matchRow(x,true);
  });
  return out;
}
