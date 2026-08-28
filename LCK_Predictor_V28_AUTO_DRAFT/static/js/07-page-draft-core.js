// Página Draft Lab: config do board, avaliação, live game drafts

async function renderDraft(prefA=null,prefB=null,query=""){
  setNav("draft");loading();
  const boot=await api("/api/draft/bootstrap");
  const teams=[...new Set((boot.rosters||[]).map(r=>r.team))];
  const champs=boot.champions||[];
  const params=new URLSearchParams(query||"");
  let defaultA=prefA&&teams.includes(prefA)?prefA:(teams.includes("DK")?"DK":teams[0]);
  let defaultB=prefB&&teams.includes(prefB)?prefB:(teams.includes("HLE")?"HLE":teams[1]);
  let seriesCtx=null;
  const eventId=params.get("event");
  const requestedGame=params.get("game");
  if(eventId){
    try{
      seriesCtx=await api(`/api/v14/series-context?event_id=${encodeURIComponent(eventId)}${requestedGame?`&game_number=${encodeURIComponent(requestedGame)}`:""}`);
      if(seriesCtx.team_a&&teams.includes(seriesCtx.team_a))defaultA=seriesCtx.team_a;
      if(seriesCtx.team_b&&teams.includes(seriesCtx.team_b))defaultB=seriesCtx.team_b;
    }catch(e){console.warn("series context",e)}
  }
  const opts=champs.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");
  const roleNames={top:"TOP",jng:"JUNGLE",mid:"MID",bot:"ADC",sup:"SUP"};
  const picker=(side,team)=>`<div class="draft-side-v12 ${side}">
    <div class="draft-side-head"><span id="draftSideLabel${side.toUpperCase()}">${side==="a"?"TIME A":"TIME B"}</span><b id="draftName${side.toUpperCase()}">${team}</b></div>
    ${Object.entries(roleNames).map(([role,label])=>`<div class="draft-role-v12"><small>${label}</small><div class="draft-player-label" id="${side}_${role}_player">—</div><select id="${side}_${role}"><option value="">Selecionar campeão</option>${opts}</select><div class="pool-suggestions" id="${side}_${role}_pool"></div></div>`).join("")}
  </div>`;
  const seriesBanner=seriesCtx?`<section class="series-context-banner-v14"><div><span class="eyebrow">CONTEXTO RIOT DA SÉRIE</span><b>${seriesCtx.team_a} ${seriesCtx.score_a??0}–${seriesCtx.score_b??0} ${seriesCtx.team_b}</b><small>Preparando Game ${seriesCtx.game_number} · ${seriesCtx.fearless_used.length} campeões bloqueados pelo Fearless</small></div><div>${seriesCtx.previous_games.map(g=>`<span>G${g.game_number} · ${g.winner||"—"}</span>`).join("")||"<span>Game 1</span>"}</div></section>`:"";
  page(`<section class="page-head"><div><span class="eyebrow">DRAFT LAB</span><h1>Construa o draft e veja o impacto.</h1><p>Probabilidade, proficiência jogador×campeão, sinergia, counters, Fearless e cobertura dos dados.</p></div><button class="soft-btn live-drafts-btn-v28" id="liveDraftsBtnV28" onclick="loadLiveDraftsV28()">📡 LIVE GAME DRAFTS</button></section>
    <div id="liveDraftsPanelV28"></div>
    ${seriesBanner}
    <section class="panel draft-config-v12">
      <div><label>Time A</label><select id="draftTeamA" onchange="syncDraftRosters();syncStrategyContextV14()">${teams.map(t=>`<option ${t===defaultA?"selected":""}>${t}</option>`).join("")}</select></div>
      <div><label>Time B</label><select id="draftTeamB" onchange="syncDraftRosters();syncStrategyContextV14()">${teams.map(t=>`<option ${t===defaultB?"selected":""}>${t}</option>`).join("")}</select></div>
      <div><label>Side do Time A</label><select id="draftSideA" onchange="syncStrategyContextV14()"><option>Blue</option><option>Red</option></select></div>
      <div><label>Patch</label><input id="draftPatch" value="16.16" placeholder="16.16"></div>
      <div><label>Mapa da série</label><select id="draftGameNumber" onchange="syncStrategyContextV14()"><option value="1">Game 1</option><option value="2">Game 2</option><option value="3">Game 3</option></select></div>
      <div class="fearless-config"><label>Fearless já usados</label><input id="draftFearless" placeholder="Camille, Ryze, Olaf…" oninput="syncStrategyContextV14()"></div>
      <div class="fearless-config"><label>Bans já feitos</label><input id="draftBans" placeholder="Azir, Vi, Rakan…" oninput="syncStrategyContextV14()"></div>
      <button onclick="evaluateDraftV12()">Analisar draft</button>
    </section>
    <div class="draft-board-v12">${picker("a",defaultA)}<div class="draft-center-v12"><span>VS</span><small>10 picks</small></div>${picker("b",defaultB)}</div>
    <section class="panel strategy-engine-v14">
      <div class="section-head"><div><span class="eyebrow">DRAFT INTELLIGENCE · V18</span><h2>Do próximo pick à melhor resposta adversária.</h2><p>Strategy Pick, Draft Tree, bans, flex uncertainty e Fearless usam o mesmo núcleo de probabilidade, mas permanecem separados por status de validação.</p></div></div>
      <div class="strategy-order-v14" id="strategyOrderV14"></div>
      <div class="strategy-tabs-v14">
        <button class="active" id="strategyTabPick" onclick="showStrategyTabV14('pick')">Próximo pick</button>
        <button id="strategyTabTree" onclick="showStrategyTabV14('tree')">Draft Tree</button><button id="strategyTabFlexTree" onclick="showStrategyTabV14('flextree')">Flex Tree</button><button id="strategyTabJoint" onclick="showStrategyTabV14('joint')">Ban→Pick Planner</button><button id="strategyTabSeries" onclick="showStrategyTabV14('series')">Series Planner</button>
        <button id="strategyTabBan" onclick="showStrategyTabV14('ban')">Ban Engine</button>
        <button id="strategyTabFlex" onclick="showStrategyTabV14('flex')">Flex Resolver</button>
        <button id="strategyTabQuick" onclick="showStrategyTabV14('quick')">Comparação rápida</button>
      </div>
      <div id="strategyPickPanelV14">
        <div class="strategy-controls-v14">
          <div><label>Slot real</label><select id="strategyPickSlot" onchange="syncStrategyContextV14()">
            <option>B1</option><option>R1</option><option>R2</option><option>B2</option><option>B3</option><option>R3</option>
            <option>R4</option><option>B4</option><option>B5</option><option>R5</option></select></div>
          <div><label>Role a preencher</label><select id="strategyRole"><option value="top">Top</option><option value="jng">Jungle</option><option value="mid">Mid</option><option value="bot">ADC</option><option value="sup">Support</option></select></div>
          <div><label>Mostrar</label><select id="strategyLimit"><option>5</option><option selected>8</option><option>10</option></select></div>
          <div class="strategy-context-card" id="strategyPickContext"><small>QUEM PICKA</small><b>—</b><span>—</span></div>
          <button onclick="strategyPickV14()">Ranquear picks →</button>
        </div>
        <div id="strategyPickResultsV14" class="strategy-results-v14"><div class="decision-empty">Monte o draft até este ponto e escolha a role. O ranking considera o mapa atual e o custo de gastar o champion para os mapas seguintes.</div></div>
      </div>
      <div id="strategyTreePanelV15" hidden>
        <div class="tree-controls-v15">
          <div><label>Primeiro slot</label><select id="treeRootSlot" onchange="syncTreeContextV15()">
            <option>B1</option><option>R1</option><option>R2</option><option>B2</option><option>B3</option><option>R3</option>
            <option>R4</option><option>B4</option><option>B5</option><option>R5</option></select></div>
          <div><label>Role do primeiro pick</label><select id="treeRootRole"><option value="top">Top</option><option value="jng">Jungle</option><option value="mid">Mid</option><option value="bot">ADC</option><option value="sup">Support</option></select></div>
          <div><label>Lookahead</label><select id="treeDepth"><option value="2" selected>2 ações · rápido</option><option value="3">3 ações · profundo</option><option value="4">4 ações</option></select></div>
          <div><label>Beam</label><select id="treeBranch"><option value="2" selected>2 · rápido</option><option value="3">3 · amplo</option><option value="4">4 · pesado</option></select></div>
          <div><label>Candidatos/role</label><select id="treePerRole"><option value="1">1</option><option value="2" selected>2</option><option value="3">3</option></select></div>
          <div class="strategy-context-card" id="treeRootContext"><small>RAIZ</small><b>—</b><span>—</span></div>
          <button onclick="runDraftTreeV15()">Buscar melhor linha →</button>
        </div>
        <div id="draftTreeResultsV15" class="tree-results-v15"><div class="decision-empty">O Draft Tree não olha só o ganho imediato: ele procura a melhor resposta do adversário e reavalia a escolha pelo pior cenário modelado.</div></div>
      </div>
      <div id="strategyFlexTreePanelV16" hidden>
        <div class="tree-controls-v15 flex-tree-controls-v16">
          <div><label>Primeiro slot</label><select id="flexTreeRootSlot" onchange="syncFlexTreeContextV16()">
            <option>B1</option><option>R1</option><option>R2</option><option>B2</option><option>B3</option><option>R3</option><option>R4</option><option>B4</option><option>B5</option><option>R5</option></select></div>
          <div><label>Lookahead</label><select id="flexTreeDepth"><option value="2">2 ações</option><option value="3" selected>3 ações</option></select></div>
          <div><label>Beam</label><select id="flexTreeBranch"><option value="2" selected>2 · rápido</option><option value="3">3 · amplo</option></select></div>
          <div><label>Role hypotheses</label><select id="flexTreeAssignments"><option value="2" selected>2 · rápido</option><option value="3">3 · amplo</option><option value="4">4 · pesado</option></select></div>
          <div class="strategy-context-card" id="flexTreeContext"><small>RAIZ FLEX</small><b>—</b><span>—</span></div>
          <button onclick="runFlexTreeV16()">Buscar sem fixar role →</button>
        </div>
        <div class="flex-tree-note-v16"><b>Diferença para Draft Tree:</b> novos champions entram como picks <em>não atribuídos</em>. A role só é resolvida no leaf entre as combinações plausíveis do elenco e do meta.</div>
        <div id="flexTreeResultsV16" class="tree-results-v15"><div class="decision-empty">Ideal para B1/R1/R2 e champions flex. O sistema preserva TOP/JNG/MID/SUP possíveis em vez de decidir cedo demais.</div></div>
      </div>
      <div id="strategyJointPanelV17" hidden>
        <div class="joint-controls-v17">
          <div><label>Próxima ação real</label><select id="jointRootSlot" onchange="syncJointContextV17()">
            <optgroup label="Ban phase 1"><option>B1BAN</option><option>R1BAN</option><option>B2BAN</option><option>R2BAN</option><option>B3BAN</option><option>R3BAN</option></optgroup>
            <optgroup label="Pick phase 1"><option>B1</option><option>R1</option><option>R2</option><option>B2</option><option>B3</option><option>R3</option></optgroup>
            <optgroup label="Ban phase 2"><option>R4BAN</option><option>B4BAN</option><option>R5BAN</option><option>B5BAN</option></optgroup>
            <optgroup label="Pick phase 2"><option>R4</option><option>B4</option><option>B5</option><option>R5</option></optgroup>
          </select></div>
          <div><label>Lookahead</label><select id="jointDepth"><option value="2">2 ações</option><option value="3" selected>3 ações</option><option value="4">4 ações · pesado</option></select></div>
          <div><label>Beam</label><select id="jointBranch"><option value="2" selected>2</option><option value="3">3</option></select></div>
          <div><label>Role hypotheses</label><select id="jointAssignments"><option value="2" selected>2</option><option value="3">3</option></select></div>
          <div class="strategy-context-card" id="jointContext"><small>PRÓXIMA AÇÃO</small><b>—</b><span>—</span></div>
          <button onclick="runJointPlannerV17()">Planejar ban + pick →</button>
        </div>
        <div class="joint-sequence-v17" id="jointSequenceV17"></div>
        <div id="jointResultsV17" class="tree-results-v15"><div class="decision-empty">A busca percorre a sequência oficial: bans alteram o pool legal dos picks seguintes e picks flex continuam sem role fixa até o leaf.</div></div>
      </div>
      <div id="strategySeriesPanelV18" hidden>
        <div class="series-controls-v18">
          <div><label>Próxima ação</label><select id="seriesRootSlot" onchange="syncSeriesContextV18()">
            <optgroup label="Ban phase 1"><option>B1BAN</option><option>R1BAN</option><option>B2BAN</option><option>R2BAN</option><option>B3BAN</option><option>R3BAN</option></optgroup>
            <optgroup label="Pick phase 1"><option>B1</option><option>R1</option><option>R2</option><option>B2</option><option>B3</option><option>R3</option></optgroup>
            <optgroup label="Ban phase 2"><option>R4BAN</option><option>B4BAN</option><option>R5BAN</option><option>B5BAN</option></optgroup>
            <optgroup label="Pick phase 2"><option>R4</option><option>B4</option><option>B5</option><option>R5</option></optgroup>
          </select></div>
          <div><label>Placar Time A</label><select id="seriesScoreA"><option>0</option><option>1</option><option>2</option></select></div>
          <div><label>Placar Time B</label><select id="seriesScoreB"><option>0</option><option>1</option><option>2</option></select></div>
          <div><label>Formato</label><select id="seriesBestOf"><option value="3" selected>Bo3</option><option value="5">Bo5</option></select></div>
          <div><label>Lookahead</label><select id="seriesDepth"><option value="2">2 ações</option><option value="3" selected>3 ações</option></select></div>
          <div><label>Beam</label><select id="seriesBranch"><option value="2" selected>2</option><option value="3">3</option></select></div>
          <div class="strategy-context-card" id="seriesContextV18"><small>OBJETIVO</small><b>—</b><span>—</span></div>
          <button onclick="runSeriesPlannerV18()">Maximizar série →</button>
        </div>
        <div class="series-model-note-v18"><b>Dois níveis:</b> o mapa atual usa o leaf robusto V8. Mapas futuros usam um proxy de <em>remaining champion pool</em> aplicado conservadoramente ao coeficiente de mastery do V8 e side neutro. A matemática do Bo3/Bo5 é exata dado esses inputs; o input futuro continua experimental.</div>
        <div id="seriesResultsV18" class="tree-results-v15"><div class="decision-empty">Uma decisão pode perder alguns décimos no mapa atual e ainda ser melhor para a série se preservar champions importantes para os mapas seguintes.</div></div>
      </div>
      <div id="strategyBanPanelV14" hidden>
        <div class="strategy-controls-v14 ban">
          <div><label>Slot de ban</label><select id="strategyBanSlot" onchange="syncStrategyContextV14()">
            <option>B1BAN</option><option>R1BAN</option><option>B2BAN</option><option>R2BAN</option><option>B3BAN</option><option>R3BAN</option>
            <option>R4BAN</option><option>B4BAN</option><option>R5BAN</option><option>B5BAN</option></select></div>
          <div class="strategy-context-card" id="strategyBanContext"><small>QUEM BANE</small><b>—</b><span>—</span></div>
          <button onclick="banStrategyV14()">Sugerir bans →</button>
        </div>
        <div id="strategyBanResultsV14" class="strategy-results-v14"><div class="decision-empty">O Ban Engine prioriza comfort denial, força no meta, flex e escassez do pool adversário. O score é estratégico, não uma probabilidade.</div></div>
      </div>
      <div id="strategyFlexPanelV15" hidden>
        <div class="flex-controls-v15">
          <div><label>Time</label><select id="flexTeamV15"><option value="a">Time A</option><option value="b">Time B</option></select></div>
          <div class="flex-champs-input"><label>Champions selecionados</label><input id="flexChampionsV15" placeholder="Aurora, Poppy, Smolder…" /></div>
          <button onclick="loadFlexFromDraftV15()">Usar picks atuais</button>
          <button class="primary" onclick="resolveFlexV15()">Resolver roles →</button>
        </div>
        <div id="flexResultsV15" class="flex-results-v15"><div class="decision-empty">O Flex Resolver enumera atribuições plausíveis de role usando histórico do jogador e uso do campeão no meta. Ele não assume que a role já foi revelada.</div></div>
      </div>
      <div id="strategyQuickPanelV14" hidden>
        <div class="decision-controls-v13">
          <div><label>Quem vai pickar?</label><select id="decisionSide"><option value="a">Time A</option><option value="b">Time B</option></select></div>
          <div><label>Role</label><select id="decisionRole"><option value="top">Top</option><option value="jng">Jungle</option><option value="mid">Mid</option><option value="bot">ADC</option><option value="sup">Support</option></select></div>
          <div><label>Mostrar</label><select id="decisionLimit"><option>5</option><option selected>8</option><option>10</option></select></div>
          <button onclick="recommendDraftV13()">Comparar agora →</button>
        </div>
        <div id="decisionResultsV13" class="decision-results-v13"><div class="decision-empty">Modo V13: compara candidatos para o mapa atual sem valor estratégico da ordem ou dos mapas futuros.</div></div>
      </div>
      <div class="strategy-legend-v14"><span><i class="validated"></i><b>Probabilidade V8</b> · motor pós-draft auditado</span><span><i class="experimental"></i><b>Strategy score</b> · política experimental</span><span><i class="context"></i><b>Flex / denial / future cost</b> · componentes estratégicos</span></div>
    </section>
    <section id="draftResultV12" class="draft-result-shell"><div class="panel draft-placeholder"><b>Monte o draft.</b><p>Você pode usar as sugestões do champion pool do jogador ou escolher qualquer campeão da base.</p></div></section>
    <section class="panel draft-method-v12"><div class="section-head"><div><h2>O que entra no score</h2><p>Separação explícita entre produção e contexto.</p></div></div><div class="feature-grid">
      <article class="feature-card"><span>PRODUÇÃO</span><h3>Força + mastery EB</h3><p>Elo e proficiência jogador×campeão com shrinkage para evitar 100% WR em amostras pequenas.</p></article>
      <article class="feature-card"><span>PRODUÇÃO</span><h3>Sinergia</h3><p>Combinações do draft recebem prior e cobertura antes de influenciar a probabilidade.</p></article>
      <article class="feature-card"><span>CONTEXTO</span><h3>Counter / patch</h3><p>Continuam visíveis, mas não recebem peso central enquanto não melhorarem validação externa.</p></article>
      <article class="feature-card"><span>SÉRIE</span><h3>Fearless + pool cost</h3><p>Além de bloquear picks usados, o Strategy Engine estima quanto gastar um comfort agora pode enfraquecer mapas futuros.</p></article>
    </div></section>`);
  window.DRAFT_BOOT=boot;
  window.DRAFT_SERIES_CONTEXT=seriesCtx||null;
  if(seriesCtx){
    if($("#draftGameNumber"))$("#draftGameNumber").value=String(Math.min(3,Math.max(1,seriesCtx.game_number||1)));
    if($("#draftFearless"))$("#draftFearless").value=(seriesCtx.fearless_used||[]).join(", ");
    if(seriesCtx.side_a&&$("#draftSideA"))$("#draftSideA").value=seriesCtx.side_a;
    if($("#seriesScoreA"))$("#seriesScoreA").value=String(seriesCtx.score_a??0);
    if($("#seriesScoreB"))$("#seriesScoreB").value=String(seriesCtx.score_b??0);
  }
  syncDraftRosters();
  syncStrategyContextV14();
  syncTreeContextV15();
  syncFlexTreeContextV16();
  syncJointContextV17();
  syncSeriesContextV18();
}
function rosterMap(team){
  const out={};(window.DRAFT_BOOT?.rosters||[]).filter(r=>r.team===team).forEach(r=>out[r.role]=r.player);return out;
}
window.syncDraftRosters=function(){
  const ta=$("#draftTeamA")?.value,tb=$("#draftTeamB")?.value;if(!ta||!tb)return;
  $("#draftNameA").textContent=ta;$("#draftNameB").textContent=tb;
  [["a",ta],["b",tb]].forEach(([side,team])=>{
    const rm=rosterMap(team);
    ["top","jng","mid","bot","sup"].forEach(role=>{
      const player=rm[role]||"—",el=$(`#${side}_${role}_player`);if(el)el.textContent=player;
      const pool=(window.DRAFT_BOOT?.pools||{})[player]||[];
      const box=$(`#${side}_${role}_pool`);
      if(box)box.innerHTML=pool.slice(0,4).map(p=>`<button title="${p.games} games · ${pct(p.smoothed_winrate)} WR ajustado" onclick="pickPool('${side}','${role}','${String(p.champion).replaceAll("'","\\'")}')">${esc(p.champion)}</button>`).join("");
    });
  });
}
window.pickPool=function(side,role,champ){const el=$(`#${side}_${role}`);if(el)el.value=champ}
window.evaluateDraftV12=async function(){
  const payload=draftPayloadV13(),a=payload.team_a,b=payload.team_b;
  if(a===b){toast("Escolha dois times diferentes");return}
  if([...Object.values(payload.picks_a),...Object.values(payload.picks_b)].some(x=>!x)){toast("Preencha os 10 picks para a análise completa");}
  const box=$("#draftResultV12");box.innerHTML=`<div class="panel draft-placeholder"><b>Analisando…</b></div>`;
  try{
    const x=await post("/api/draft/evaluate",payload);renderDraftResultV12(x);
  }catch(e){box.innerHTML=`<div class="panel draft-placeholder"><b>Não foi possível avaliar.</b><p>${esc(e.message)}</p></div>`}
}

function draftPayloadV13(){
  const roles=["top","jng","mid","bot","sup"],pa={},pb={};
  roles.forEach(r=>{pa[r]=$(`#a_${r}`)?.value||"";pb[r]=$(`#b_${r}`)?.value||""});
  return {team_a:$("#draftTeamA").value,team_b:$("#draftTeamB").value,side_a:$("#draftSideA").value,
    patch:$("#draftPatch").value,game_number:Number($("#draftGameNumber")?.value||1),picks_a:pa,picks_b:pb,
    fearless_used:$("#draftFearless").value.split(",").map(x=>x.trim()).filter(Boolean),
    bans:($("#draftBans")?.value||"").split(",").map(x=>x.trim()).filter(Boolean),
    series_score_a:window.DRAFT_SERIES_CONTEXT?.score_a,
    series_score_b:window.DRAFT_SERIES_CONTEXT?.score_b};
}

window.LIVE_GAMES_V28=[];
window.loadLiveDraftsV28=async function(){
  const btn=$("#liveDraftsBtnV28"),panel=$("#liveDraftsPanelV28");
  if(btn){btn.disabled=true;btn.textContent="📡 Procurando jogos…"}
  if(panel)panel.innerHTML=`<section class="panel live-games-list-v28"><b>Procurando jogos ao vivo…</b></section>`;
  try{
    const r=await api("/api/live-games");
    window.LIVE_GAMES_V28=r.games||[];
    if(!r.ok||!window.LIVE_GAMES_V28.length){
      if(panel)panel.innerHTML=`<section class="panel live-games-list-v28"><b>Nenhum jogo ao vivo detectado agora.</b><p>${esc(r.error||"Tente novamente durante uma partida LCK / LPL / CBLOL.")}</p></section>`;
    }else{
      if(panel)panel.innerHTML=liveGamesListV28(window.LIVE_GAMES_V28);
      if(window.LIVE_GAMES_V28.length===1)applyLiveDraftV28(0);
    }
  }catch(e){
    if(panel)panel.innerHTML=`<section class="panel live-games-list-v28"><b>Falha ao buscar jogos.</b><p>${esc(e.message)}</p></section>`;
  }
  if(btn){btn.disabled=false;btn.textContent="📡 LIVE GAME DRAFTS"}
};
function liveGamesListV28(games){
  return `<section class="panel live-games-list-v28"><div class="section-head"><div><h2>Jogos ao vivo</h2><p>Clique em um jogo para carregar o draft atual no board (um fetch falho não apaga o draft montado).</p></div></div>${games.map((g,i)=>`<button class="soft-btn live-game-row-v28" onclick="applyLiveDraftV28(${i})"><b>${esc(g.blueTeam||g.blueCode||"—")} <span>vs</span> ${esc(g.redTeam||g.redCode||"—")}</b><span>Game ${g.gameNum||"—"} · ${esc(g.league||"—")}</span></button>`).join("")}</section>`;
}
window.applyLiveDraftV28=async function(idx){
  const g=(window.LIVE_GAMES_V28||[])[idx];if(!g)return;
  const panel=$("#liveDraftsPanelV28");
  if(panel)panel.innerHTML=`<section class="panel live-games-list-v28"><b>Carregando draft…</b></section>`;
  try{
    const d=await fetchLiveDraftV28(g.gameId);
    fillDraftFromLiveV28(g,d);
    if(panel)panel.innerHTML=liveDraftLoadedV28(g,d);
    toast("Draft ao vivo carregado no board");
  }catch(e){
    toast(e.message==="DRAFT_NOT_READY"?"Draft ainda não publicado pela Riot":"Não consegui carregar o draft");
    if(panel)panel.innerHTML=`<section class="panel live-games-list-v28"><b>Draft indisponível.</b><p>${esc(e.message==="DRAFT_NOT_READY"?"A Riot ainda não publicou os champions deste jogo.":e.message)}</p></section>`;
  }
};
async function fetchLiveDraftV28(gameId){
  const r=await fetch(`/api/live-draft?gameId=${encodeURIComponent(gameId)}`,{cache:"no-store"});
  let body=null;try{body=await r.json()}catch(e){}
  if(!r.ok||!body?.ok)throw new Error(body?.error==="DRAFT_NOT_READY"?"DRAFT_NOT_READY":(body?.detail||body?.error||`HTTP ${r.status}`));
  return body;
}
function shortPatchV28(p){if(!p)return "16.16";const s=String(p).split(".");return s.length>=2?s.slice(0,2).join("."):p}
function setLiveTeamV28(side,localName,liveName){
  const sel=$(`#draftTeam${side.toUpperCase()}`),label=$(`#draftName${side.toUpperCase()}`);
  if(localName){
    if(sel)sel.value=localName;
    if(label)label.textContent=localName;
    return;
  }
  if(sel){
    let option=sel.querySelector("option[data-live-team]");
    if(!option){
      option=document.createElement("option");
      option.dataset.liveTeam="true";
      sel.insertBefore(option,sel.firstChild);
    }
    option.value="";option.textContent=`${liveName||"Time desconhecido"} (sem stats)`;sel.value="";
  }
  if(label)label.textContent=liveName||"Time desconhecido";
}
function fillDraftFromLiveV28(g,d){
  const teams=[...new Set((window.DRAFT_BOOT?.rosters||[]).map(r=>r.team))];
  const a=g.blueLocal||null,b=g.redLocal||null;
  setLiveTeamV28("a",a&&teams.includes(a)?a:null,g.blueTeam||g.blueCode);
  setLiveTeamV28("b",b&&teams.includes(b)?b:null,g.redTeam||g.redCode);
  if($("#draftSideA"))$("#draftSideA").value="Blue";
  if($("#draftPatch")&&d.patch)$("#draftPatch").value=shortPatchV28(d.patch);
  if($("#draftGameNumber")&&g.gameNum)$("#draftGameNumber").value=String(g.gameNum);
  fillLiveSideV28("a",d.blue);fillLiveSideV28("b",d.red);
  syncDraftRosters();
  fillLiveSideV28("a",d.blue);fillLiveSideV28("b",d.red);
  syncStrategyContextV14();
}
function fillLiveSideV28(side,picks){
  const roles=["top","jng","mid","bot","sup"],by={};
  (picks||[]).forEach(p=>{if(p.role&&roles.includes(p.role)&&p.champion)by[p.role]=p;});
  roles.forEach(role=>{
    const sel=$(`#${side}_${role}`),p=by[role],champ=p?.champion;
    if(sel&&champ){
      if(![...sel.options].some(o=>o.value===champ))sel.insertAdjacentHTML("beforeend",`<option>${esc(champ)}</option>`);
      sel.value=champ;
    }
    const lbl=$(`#${side}_${role}_player`);if(lbl)lbl.textContent=p?.player||"—";
  });
}
function liveDraftLoadedV28(g,d){
  const side=(x)=>`<div class="live-draft-side-v28"><b>${esc(x.team||"—")}</b>${["top","jng","mid","bot","sup"].map(r=>{const p=(x.picks||[]).find(q=>q.role===r);return `<div><small>${r.toUpperCase()}</small><strong>${esc(p?.champion||"—")}</strong><span>${esc(p?.player||"—")}</span></div>`}).join("")}</div>`;
  return `<section class="panel live-games-list-v28"><div class="section-head"><div><h2>Draft ao vivo carregado</h2><p>${esc(g.blueTeam||"—")} vs ${esc(g.redTeam||"—")} · Game ${g.gameNum||"—"} · Patch ${esc(shortPatchV28(d.patch))}</p></div></div><div class="live-draft-board-v28">${side({team:g.blueTeam||g.blueLocal||"Blue",picks:d.blue})}<span>VS</span>${side({team:g.redTeam||g.redLocal||"Red",picks:d.red})}</div></section>`;
}
