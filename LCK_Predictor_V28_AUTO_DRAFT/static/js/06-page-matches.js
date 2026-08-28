// Páginas Matches (lista) e Match (detalhe, ao vivo, histórico)


let LIVE_RECOVERY_RUNNING_V27=false;
window.refreshLiveNowV27=async function(silent=false){
  if(LIVE_RECOVERY_RUNNING_V27)return;
  LIVE_RECOVERY_RUNNING_V27=true;
  const b=document.getElementById("liveRefreshBtnV27");
  if(b){b.disabled=true;b.textContent="Sincronizando…"}
  try{
    const r=await post("/api/v27/live/refresh",{});
    if(r.event_id){
      if(!silent)toast("Riot Live conectado");
    }else if(r.fallback){
      if(!silent)toast("Jogo detectado pelo horário; aguardando Riot Event ID");
    }
    if(MATCH_TAB==="live")await renderMatches("live",true);
    return r;
  }catch(e){
    if(!silent)toast("Riot Live indisponível; mantendo detecção pelo horário");
  }finally{
    LIVE_RECOVERY_RUNNING_V27=false;
    if(b){b.disabled=false;b.textContent="↻ Sincronizar live"}
  }
}

let MATCH_TAB="upcoming";
async function renderMatches(tab,skipLiveSync=false){
  setNav("matches");MATCH_TAB=tab||"upcoming";loading();
  const status=MATCH_TAB==="results"?"completed":MATCH_TAB==="live"?"live":"upcoming";
  let items=await api(`/api/v12/matches?status=${status}&limit=600`);
  if(status==="upcoming"&&!items.length){
    const h=await api("/api/v12/home");items=h.upcoming||[];
  }
  page(`<section class="page-head"><div><span class="eyebrow">MATCH CENTER</span><h1>${MATCH_TAB==="upcoming"?"Próximas partidas":MATCH_TAB==="live"?"Ao vivo":"Resultados"}</h1><p>${MATCH_TAB==="upcoming"?"A lista remove automaticamente partidas cujo horário já passou.":MATCH_TAB==="live"?"Riot Live quando disponível; horário oficial funciona como recuperação temporária.":"Partidas finalizadas e auditoria das previsões."}</p></div>${MATCH_TAB==="upcoming"?`<button class="soft-btn" onclick="refreshScheduleV23(this)">↻ Atualizar agenda</button>`:MATCH_TAB==="live"?`<button class="soft-btn" id="liveRefreshBtnV27" onclick="refreshLiveNowV27(false)">↻ Sincronizar live</button>`:""}</section>
    <div class="tabs">
      <button class="${MATCH_TAB==="upcoming"?"active":""}" onclick="go('matches/upcoming')">Próximas</button>
      <button class="${MATCH_TAB==="live"?"active":""}" onclick="go('matches/live')">Ao vivo</button>
      <button class="${MATCH_TAB==="results"?"active":""}" onclick="go('matches/results')">Resultados</button>
    </div>
    <section class="panel match-center-panel">
      <div class="list-head"><span>Data</span><span>Confronto</span><span>Leitura</span><span>Status</span></div>
      <div class="match-list">${items.length?(status==="upcoming"?groupedUpcomingV23(items,600):items.map(x=>matchRow(x)).join("")):`<div class="empty-panel inner"><b>Nenhuma partida nesta categoria.</b><p>${status==="upcoming"?"Clique em Atualizar agenda para consultar a Riot.":"O feed continua atualizando automaticamente."}</p></div>`}</div>
    </section>`);
  if(MATCH_TAB==="live"&&!skipLiveSync){
    setTimeout(()=>refreshLiveNowV27(true),250);
  }
}

function readHistorical(x){
  const r=x.series,p=r.pregame_elo_p_team1==null?null:Number(r.pregame_elo_p_team1);
  const fav=p==null?null:favorite(p,r.team1,r.team2),audit=x.audit;
  return `<section class="match-identity">
    <div>${teamMark(r.team1)}<b>${r.team1}</b><strong>${r.wins1}</strong></div><span>FINAL</span><div class="right"><strong>${r.wins2}</strong><b>${r.team2}</b>${teamMark(r.team2)}</div>
  </section>
  <section class="forecast-ribbon">
    <div><small>ANTES DA SÉRIE</small><strong>${fav?`${fav.team} ${pct(fav.p)}`:"Sem snapshot"}</strong><span>${fav?"baseline pré-jogo reconstruído":"—"}</span></div>
    <div><small>RESULTADO</small><strong>${r.winner} venceu</strong><span>${r.wins1}–${r.wins2}</span></div>
    <div class="${audit?.correct?"good":"bad"}"><small>AUDITORIA</small><strong>${audit?(audit.correct?"Acertou":"Errou"):"—"}</strong><span>${audit?`Brier ${Number(audit.brier).toFixed(3)}`:"sem previsão"}</span></div>
  </section>
  <section class="explain-box"><b>Sem hindsight.</b><p>O número pré-jogo usa somente o estado existente antes da série. Draft e resultado final não entram retroativamente.</p></section>
  <div class="game-grid">${(x.games||[]).map(g=>historicalGame(g)).join("")||`<section class="panel"><div class="empty-inline">Game-level stats não estão disponíveis para esta série.</div></section>`}</div>`;
}
function historicalGame(g){
  const t=g.teams||[],a=t[0]||{},b=t[1]||{};
  const players=g.players||[];
  return `<article class="panel game-card"><div class="game-title"><div><small>MAPA ${g.game_number||"—"} · PATCH ${g.patch||"—"}</small><h3>${a.team||"—"} <i>vs</i> ${b.team||"—"}</h3></div><b>${a.kills??"—"}–${b.kills??"—"}<span>kills</span></b></div>
    <div class="stat-row"><div><small>Ouro</small><b>${num(a.gold)}–${num(b.gold)}</b></div><div><small>Torres</small><b>${a.towers??"—"}–${b.towers??"—"}</b></div><div><small>Dragões</small><b>${a.dragons??"—"}–${b.dragons??"—"}</b></div><div><small>Baron</small><b>${a.barons??"—"}–${b.barons??"—"}</b></div><div><small>GD@15 blue</small><b>${signed(a.gd15||0)}</b></div></div>
    ${players.length?`<div class="draft-lines">${["blue","red"].map(side=>`<div>${players.filter(p=>String(p.side).toLowerCase()===side).map(p=>`<span><small>${String(p.position||"").toUpperCase()}</small><b>${p.playername}</b><em>${p.champion}</em></span>`).join("")}</div>`).join("")}</div>`:""}</article>`;
}

function scoreOutcomeList(s){
  if(!s?.outcomes)return "";
  return `<div class="score-outcomes">${s.outcomes.map((o,i)=>`<div class="${i===0?"top":""}"><span>${o.winner}</span><b>${o.score}</b><strong>${pct(o.probability)}</strong></div>`).join("")}</div>`;
}
function readUpcoming(x){
  const m=x.prediction,p=Number(m.probability_team_a),f=favorite(p,x.team_a,x.team_b);
  return `<section class="match-identity pre">
    <div>${teamMark(x.team_a)}<b>${x.team_a}</b><strong>${probBadge(p)}</strong></div><span>VS</span><div class="right"><strong>${probBadge(p==null?null:1-p)}</strong><b>${x.team_b}</b>${teamMark(x.team_b)}</div>
  </section>
  <section class="forecast-ribbon">
    <div><small>FAVORITO</small><strong>${f.team} ${probBadge(f.p)}</strong><span>${advantage(p)}</span></div>
    <div><small>PLACAR MAIS PROVÁVEL${m.scoreline?.best_of?` · MD${m.scoreline.best_of}`:""}</small><strong>${m.scoreline?.most_likely?`${m.scoreline.most_likely.winner} ${m.scoreline.most_likely.score}`:"—"}</strong><span>${m.scoreline?.most_likely?pct(m.scoreline.most_likely.probability):"—"}</span></div>
    <div><small>GAME ${m.scoreline?.decisive_game_number||3}</small><strong>${m.scoreline?pct(m.scoreline.game3_probability):"—"}</strong><span>chance da série ir ao último mapa</span></div>
  </section>
  <section class="panel pregame-body"><div class="section-head"><div><h2>Placares possíveis</h2><p>Distribuição condicionada à probabilidade de vencer a série.</p></div></div>${scoreOutcomeList(m.scoreline)}</section>
  <section class="panel explain-prediction"><div class="section-head"><div><h2>Por que?</h2><p>Leitura resumida antes do draft.</p></div></div>
    <div class="why-grid"><div><small>${x.team_a}</small><b>${m.analysis?.edge_a||"Força atual e forma recente."}</b></div><div><small>${x.team_b}</small><b>${m.analysis?.edge_b||"Força atual e forma recente."}</b></div></div>
    <p>${m.analysis?.key_read||"A probabilidade é atualizada novamente quando o draft real estiver disponível."}</p></section>`;
}

const ROLE_SHORT_V12={top:"TOP",jungle:"JNG",jng:"JNG",mid:"MID",middle:"MID",bottom:"BOT",bot:"BOT",adc:"BOT",support:"SUP",sup:"SUP"};
function roleShortV12(r){const k=String(r||"").toLowerCase();return ROLE_SHORT_V12[k]||String(r||"").slice(0,3).toUpperCase()}
function livePlayerRowV12(p){
  return `<div class="live-player-row"><small>${roleShortV12(p.role)}</small><b>${p.player||"—"}</b><span>${p.champion||"—"}</span><strong>${p.kills||0}/${p.deaths||0}/${p.assists||0}</strong><em>${num(p.gold)}g · ${num(p.cs)} CS</em></div>`;
}
function liveTeamV12(t){
  return `<div class="live-team-box"><div class="live-team-name"><b>${code(t.team)}</b><strong>${num(t.gold)}</strong></div>
    <div class="live-objectives"><span>${t.kills||0}<small>Kills</small></span><span>${t.towers||0}<small>Torres</small></span><span>${t.dragons||0}<small>Dragões</small></span><span>${t.barons||0}<small>Baron</small></span><span>${t.inhibitors||0}<small>Inib.</small></span></div>
    <div>${(t.participants||[]).map(livePlayerRowV12).join("")}</div></div>`;
}
function liveTimelineSvg(rows){
  rows=(rows||[]).filter(r=>r.game_time_seconds!=null);
  if(rows.length<2)return `<div class="empty-inline live-empty">Coletando snapshots para a curva do mapa…</div>`;
  const diffs=rows.map(r=>Number(r.blue_gold||0)-Number(r.red_gold||0)),max=Math.max(1000,...diffs.map(Math.abs)),W=800,H=120,pad=12;
  const pts=diffs.map((d,i)=>`${pad+(W-2*pad)*(i/(diffs.length-1))},${H/2-(d/max)*(H/2-pad)}`).join(" ");
  return `<svg class="live-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="${pad}" y1="${H/2}" x2="${W-pad}" y2="${H/2}"/><polyline points="${pts}"/></svg>
    <div class="chart-caption"><span>${clock(rows[0].game_time_seconds)}</span><b>Gold diff Blue − Red</b><span>${clock(rows[rows.length-1].game_time_seconds)}</span></div>`;
}
function liveStreamV12(streams,eventId){
  const s=(streams||[])[0],provider=String(s?.provider||"").toLowerCase(),param=s?.parameter;
  let inner=`<div class="stream-fallback"><b>Stream do evento</b><p>Os dados live independem do player de vídeo.</p></div>`;
  if(provider==="twitch"&&param){
    const parent=encodeURIComponent(location.hostname||"localhost");
    inner=`<iframe src="https://player.twitch.tv/?channel=${encodeURIComponent(param)}&parent=${parent}&autoplay=false&muted=true" allowfullscreen></iframe>`;
  }else if(provider==="youtube"&&param){
    inner=`<iframe src="https://www.youtube.com/embed/${encodeURIComponent(param)}?autoplay=0" allowfullscreen></iframe>`;
  }
  return `<div class="live-stream-v12">${inner}<div class="stream-links"><a target="_blank" rel="noopener" href="https://andydanger.github.io/live-lol-esports/#/live/${eventId}">AndyDanger ↗</a><a target="_blank" rel="noopener" href="https://hub.maisesports.com.br/lives/${eventId}">MaisEsports HUB ↗</a></div></div>`;
}

function autoDraftModuleV28(d){
  if(!d||!d.ok){
    return `<section class="panel auto-draft-v28 waiting"><div><span class="eyebrow">AUTO DRAFT</span><h2>${d?.status==="WAITING_METADATA"?"Aguardando champions…":"Procurando draft Riot…"}</h2><p>${esc(d?.note||d?.error||"Event ID → Game ID → champion metadata.")}</p></div><div class="draft-lock-count"><b>${d?.locked_count||0}/10</b><span>capturados</span></div></section>`;
  }
  const side=(x,label)=>`<div class="auto-draft-side-v28"><div class="auto-draft-team-v28">${teamMark(x?.team||label,true)}<b>${esc(x?.team||label)}</b></div><div class="auto-draft-picks-v28">${["top","jng","mid","bot","sup"].map(r=>`<div><small>${r.toUpperCase()}</small><strong>${esc(x?.picks?.[r]||"…")}</strong></div>`).join("")}</div></div>`;
  const ev=d.auto_evaluation;
  return `<section class="panel auto-draft-v28 ${d.complete?"complete":"partial"}"><div class="auto-draft-head-v28"><div><span class="eyebrow">AUTO DRAFT · RIOT</span><h2>${d.complete?"Draft capturado automaticamente":"Capturando draft…"}</h2><p>Mapa ${d.game_number||"—"} · ${d.locked_count}/10 champions</p></div><div class="draft-lock-count"><b>${d.locked_count}/10</b><span>${d.complete?"LOCKED":"capturados"}</span></div></div><div class="auto-draft-board-v28">${side(d.blue,"Blue")}<span class="draft-vs-v28">VS</span>${side(d.red,"Red")}</div>${ev?`<div class="auto-draft-model-v28"><small>PÓS-DRAFT · V8</small><strong>${ev.team_a} ${pct(ev.probability_team_a)}</strong><span>evidência ${ev.evidence_confidence??"—"}/100 · calculado automaticamente</span></div>`:""}</section>`;
}

function liveModuleV12(l){
  if(!l?.ok||!l.snapshot)return `<section class="panel live-unavailable"><b>Feed live temporariamente indisponível.</b><p>${esc(l?.error||"Usando o último estado conhecido da série.")}</p></section>`;
  const s=l.snapshot,b=s.blue,r=s.red,est=l.live_estimate,ser=l.series_analysis,d=l.draft_analysis;
  const gd=Number(b.gold||0)-Number(r.gold||0),lead=gd>=0?code(b.team):code(r.team);
  const role=est?.features?.role_gold_diff||{};
  return `<section class="live-mode-v12">
    <div class="live-now-bar"><div><span class="live-signal">● RIOT LIVE</span><h2>Mapa ${s.game_number} · ${s.game_time_approximate?"~":""}${clock(s.game_time_seconds)}</h2><p>Patch ${s.patch||"—"} · atualização automática · ${l.training_capture?.checkpoint_second?`dataset ${Math.floor(l.training_capture.checkpoint_second/60)}m ${l.training_capture.captured?"salvo":"já salvo"}`:"coletor aguardando checkpoint"}</p></div><div><small>OURO</small><strong>${num(b.gold)} × ${num(r.gold)}</strong><span>${lead} ${signed(Math.abs(gd))}</span></div></div>
    <div class="live-prob-grid"><div><small>PRÉ-SÉRIE · VALIDADO</small><b>${ser?`${ser.team_a} ${pct(ser.pregame_series_probability_team_a)}`:"—"}</b></div>
      <div><small>PÓS-DRAFT · VALIDADO</small><b>${d?`${d.team_a} ${pct(d.draft_game_probability_team_a)}`:"—"}</b></div>
      <div class="experimental"><small>LIVE · EXPERIMENTAL</small><b>${est?`${code(b.team)} ${pct(est.probability_blue)}`:"—"}</b></div>
      <div class="${ser?.uses_experimental_live?"experimental":""}"><small>SÉRIE AGORA</small><b>${ser?`${ser.team_a} ${pct(ser.probability_team_a)}`:"—"}</b></div></div>
    <div class="live-main-grid"><div class="panel live-data-panel"><div class="live-teams-v12">${liveTeamV12(b)}${liveTeamV12(r)}</div></div>${liveStreamV12(l.streams,l.event_id)}</div>
    <section class="panel live-context-v12"><div class="section-head"><div><h2>Distribuição da vantagem</h2><p>Ouro por rota para evitar resumir o mapa a um único gold diff.</p></div></div>
      <div class="role-diff-v12">${["top","jng","mid","bot","sup"].map(k=>`<div><small>${k.toUpperCase()}</small><b class="${Number(role[k]||0)>=0?"blue":"red"}">${signed(role[k]||0)}</b></div>`).join("")}</div>
      ${liveTimelineSvg(l.timeline)}</section>
    <div class="experimental-note"><b>Live ainda é experimental.</b> Os snapshots são armazenados para que essa camada possa ser treinada e calibrada futuramente. O app não apresenta essa heurística como equivalente ao modelo pré-jogo validado.</div>
  </section>`;
}
async function refreshLiveV12(eventId){
  try{
    const [l,d]=await Promise.all([
      api(`/api/riot/live?event_id=${encodeURIComponent(eventId)}&refresh=1`),
      api(`/api/v28/draft/status?event_id=${encodeURIComponent(eventId)}&refresh=1`)
    ]);
    const el=$("#liveModeV12");if(el)el.innerHTML=liveModuleV12(l);
    const de=$("#autoDraftV28");if(de)de.innerHTML=autoDraftModuleV28(d);
  }catch(e){console.warn(e)}
}

function readRiot(x,liveData=null,draftData=null){
  const ev=x.event||{},games=x.games||[],a=ev.team_a_code||code(ev.team_a),b=ev.team_b_code||code(ev.team_b);
  const live=x.phase==="live",pre=x.phase==="pre";
  const m=x.current_prediction,p=m?.probability_team_a!=null?Number(m.probability_team_a):null,f=p==null?null:favorite(p,a,b);
  return `<section class="match-identity ${live?"live":pre?"pre":""}">
    <div>${teamMark(a)}<b>${a}</b><strong>${pre?probBadge(p):(ev.score_a??0)}</strong></div><span>${live?"● LIVE":pre?"VS":"SÉRIE"}</span><div class="right"><strong>${pre?probBadge(p==null?null:1-p):(ev.score_b??0)}</strong><b>${b}</b>${teamMark(b)}</div>
  </section>
  ${pre&&m?`<section class="forecast-ribbon"><div><small>FAVORITO</small><strong>${f.team} ${probBadge(f.p)}</strong><span>${advantage(p)}</span></div>
    <div><small>PLACAR MAIS PROVÁVEL${m.scoreline?.best_of?` · MD${m.scoreline.best_of}`:""}</small><strong>${m.scoreline?.most_likely?`${m.scoreline.most_likely.winner} ${m.scoreline.most_likely.score}`:"—"}</strong><span>${m.scoreline?.most_likely?pct(m.scoreline.most_likely.probability):"—"}</span></div>
    <div><small>MODELO</small><strong>${m.mode||"pré-jogo"}</strong><span>antes do draft</span></div></section>`:""}
  ${live?`<div id="autoDraftV28">${autoDraftModuleV28(draftData)}</div><div id="liveModeV12">${liveModuleV12(liveData)}</div>`:""}
  ${games.length?`<section class="subsection-title"><h2>${live?"Mapas anteriores / cache":"Mapas da série"}</h2></section>`:""}
  <div class="game-grid">${games.map(g=>riotGame(g)).join("")||(!live&&!pre?`<section class="panel"><div class="empty-inline">Game IDs ainda não foram trazidos para o cache detalhado.</div></section>`:"")}</div>`;
}
function riotGame(g){
  const c=g.case_study,w=c?.result_winner||g.winner;
  const draft=g.draft||{},journ=g.journal||[];
  return `<article class="panel game-card"><div class="game-title"><div><small>MAPA ${g.game_number} · PATCH ${g.patch||"—"}</small><h3>${code(g.blue_team)} <i>vs</i> ${code(g.red_team)}</h3></div><span class="row-status ${String(g.state).includes("complete")?"completed":"live"}">${statusLabel(g.state)}</span></div>
    ${c?`<div class="prediction-compare"><div><small>Pré-série</small><b>${c.team_a} ${pct(c.pre_series_p_a)}</b></div><div><small>Pós-draft</small><b>${c.team_a} ${pct(c.draft_p_a)}</b></div><div><small>Resultado</small><b>${w||"—"}</b></div></div>`:""}
    <div class="stat-row"><div><small>Ouro</small><b>${num(g.blue_gold)}–${num(g.red_gold)}</b></div><div><small>Kills</small><b>${g.blue_kills??"—"}–${g.red_kills??"—"}</b></div><div><small>Torres</small><b>${g.blue_towers??"—"}–${g.red_towers??"—"}</b></div><div><small>Snapshots</small><b>${g.timeline?.length||journ.filter(j=>j.stage==="live").length}</b></div><div><small>Vencedor</small><b>${w||"—"}</b></div></div>
    ${g.participants?.length?`<div class="participant-table">${g.participants.map(p=>`<div><small>${String(p.role||"").toUpperCase()}</small><b>${p.player}</b><span>${p.champion}</span><strong>${p.kills}/${p.deaths}/${p.assists}</strong><em>${num(p.gold)}g</em></div>`).join("")}</div>`:""}</article>`;
}

window.promoteScheduleLiveV27=async function(){
  try{
    const r=await post("/api/v27/live/refresh",{});
    if(r.event_id){go(`match/${encodeURIComponent("riot:"+r.event_id)}`);return}
    toast("Riot Event ID ainda não disponível; a partida continua marcada como live pelo horário.");
  }catch(e){toast("Não consegui conectar o Riot Live agora.")}
}

async function renderMatch(id){
  setNav("matches");loading();
  const x=await api(`/api/v12/match?id=${encodeURIComponent(id)}`);
  const phase=x.phase||(x.kind==="historical"?"post":"pre");
  let teams="",date="",body="";
  if(x.kind==="historical"){teams=`${x.series.team1} vs ${x.series.team2}`;date=x.series.date;body=readHistorical(x)}
  else if(x.kind==="upcoming"){
    teams=`${x.team_a} vs ${x.team_b}`;date=x.date;
    body=(phase==="live"?`<section class="live-sync-banner-v27"><div><span>● LIVE · SINCRONIZANDO</span><b>${x.team_a} vs ${x.team_b}</b><p>O horário do matchday indica partida em andamento. Tentando conectar o Event ID e os livestats da Riot.</p></div><button onclick="promoteScheduleLiveV27()">↻ Conectar Riot Live</button></section>`:"")+readUpcoming(x)
  }
  else {
    teams=`${code(x.event.team_a)} vs ${code(x.event.team_b)}`;date=x.event.start_time;
    let liveData=null,draftData=null;
    if(phase==="live"){
      try{
        [liveData,draftData]=await Promise.all([
          api(`/api/riot/live?event_id=${encodeURIComponent(x.event.event_id)}&refresh=1`),
          api(`/api/v28/draft/status?event_id=${encodeURIComponent(x.event.event_id)}&refresh=1`)
        ]);
      }catch(e){liveData={ok:false,error:e.message}}
    }
    body=readRiot(x,liveData,draftData);
    if(phase==="live"){S.liveTimer=setInterval(()=>refreshLiveV12(x.event.event_id),10000)}
  }
  let draftRoute="draft";
  if(x.kind==="riot_event"&&x.event){
    const ta=code(x.event.team_a),tb=code(x.event.team_b);
    const gn=Math.min(3,Number(x.event.score_a||0)+Number(x.event.score_b||0)+1);
    draftRoute=`draft/${encodeURIComponent(ta)}/${encodeURIComponent(tb)}?event=${encodeURIComponent(x.event.event_id)}&game=${gn}`;
  }else if(x.kind==="upcoming"){
    draftRoute=`draft/${encodeURIComponent(x.team_a)}/${encodeURIComponent(x.team_b)}`;
  }else if(x.kind==="historical"){
    draftRoute=`draft/${encodeURIComponent(x.series.team1)}/${encodeURIComponent(x.series.team2)}`;
  }
  page(`<section class="page-head match-page-head"><div><button class="back-link" onclick="history.back()">← Matches</button><div>${phasePill(phase)}<span class="eyebrow">${dateText(date)}</span></div><h1>${esc(teams)}</h1></div><button class="soft-btn" onclick="go('${draftRoute}')">Abrir no Draft Lab →</button></section>${body}`);
}
