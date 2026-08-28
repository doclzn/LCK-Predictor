// Draft Lab: Strategy/Ban Engine, Draft/Flex Tree, Joint/Series Planner, Decision Engine

window.showStrategyTabV14=function(tab){
  $("#strategyPickPanelV14").hidden=tab!=="pick";
  $("#strategyTreePanelV15").hidden=tab!=="tree";
  $("#strategyFlexTreePanelV16").hidden=tab!=="flextree";
  $("#strategyJointPanelV17").hidden=tab!=="joint";
  $("#strategySeriesPanelV18").hidden=tab!=="series";
  $("#strategyBanPanelV14").hidden=tab!=="ban";
  $("#strategyFlexPanelV15").hidden=tab!=="flex";
  $("#strategyQuickPanelV14").hidden=tab!=="quick";
  $("#strategyTabPick").classList.toggle("active",tab==="pick");
  $("#strategyTabTree").classList.toggle("active",tab==="tree");
  $("#strategyTabFlexTree").classList.toggle("active",tab==="flextree");
  $("#strategyTabJoint").classList.toggle("active",tab==="joint");
  $("#strategyTabSeries").classList.toggle("active",tab==="series");
  $("#strategyTabBan").classList.toggle("active",tab==="ban");
  $("#strategyTabFlex").classList.toggle("active",tab==="flex");
  $("#strategyTabQuick").classList.toggle("active",tab==="quick");
  if(tab==="tree")syncTreeContextV15();
  if(tab==="flextree")syncFlexTreeContextV16();
  if(tab==="joint")syncJointContextV17();
  if(tab==="series")syncSeriesContextV18();
}
function strategyTeamForSlotV14(slot){
  const blueA=String($("#draftSideA")?.value||"Blue").toLowerCase()==="blue";
  const blue=String(slot||"").toUpperCase().startsWith("B");
  const side=(blue===blueA)?"a":"b";
  const team=side==="a"?$("#draftTeamA")?.value:$("#draftTeamB")?.value;
  return {side,team,sideName:blue?"Blue":"Red"};
}
window.syncStrategyContextV14=function(){
  const blueA=String($("#draftSideA")?.value||"Blue").toLowerCase()==="blue";
  if($("#draftSideLabelA"))$("#draftSideLabelA").textContent=`${blueA?"BLUE":"RED"} / TIME A`;
  if($("#draftSideLabelB"))$("#draftSideLabelB").textContent=`${blueA?"RED":"BLUE"} / TIME B`;
  const pickSlot=$("#strategyPickSlot")?.value||"B1",banSlot=$("#strategyBanSlot")?.value||"B1BAN";
  const pick=strategyTeamForSlotV14(pickSlot),ban=strategyTeamForSlotV14(banSlot);
  if($("#strategyPickContext"))$("#strategyPickContext").innerHTML=`<small>QUEM PICKA</small><b>${esc(pick.team||"—")}</b><span>${pick.sideName} · ${pickSlot}</span>`;
  if($("#strategyBanContext"))$("#strategyBanContext").innerHTML=`<small>QUEM BANE</small><b>${esc(ban.team||"—")}</b><span>${ban.sideName} · ${banSlot}</span>`;
  const pickOrder=["B1","R1","R2","B2","B3","R3","R4","B4","B5","R5"];
  if($("#strategyOrderV14")){
    $("#strategyOrderV14").innerHTML=`<div><small>ORDEM DE PICKS</small>${pickOrder.map(slot=>{
      const x=strategyTeamForSlotV14(slot);
      return `<span class="${slot===pickSlot?"current":""}"><b>${slot}</b><em>${esc(x.team||"—")}</em></span>`;
    }).join("")}</div><div class="series-map-context"><small>SÉRIE</small><b>Game ${$("#draftGameNumber")?.value||1}</b><span>${Number($("#draftGameNumber")?.value||1)===1?"até 2 mapas futuros":Number($("#draftGameNumber")?.value||1)===2?"até 1 mapa futuro":"último mapa potencial"}</span></div>`;
  }
}




window.syncSeriesContextV18=function(){
  const slot=$("#seriesRootSlot")?.value||"B1BAN",x=strategyTeamForSlotV14(slot),a=$("#draftTeamA")?.value||"A",b=$("#draftTeamB")?.value||"B";
  if($("#seriesContextV18"))$("#seriesContextV18").innerHTML=`<small>OBJETIVO DA SÉRIE</small><b>${esc(x.team||"—")}</b><span>${slot} · ${a} ${$("#seriesScoreA")?.value||0}–${$("#seriesScoreB")?.value||0} ${b}</span>`;
}
window.runSeriesPlannerV18=async function(){
  const box=$("#seriesResultsV18"),payload=draftPayloadV13();
  payload.root_action_slot=$("#seriesRootSlot").value;payload.series_score_a=Number($("#seriesScoreA").value||0);payload.series_score_b=Number($("#seriesScoreB").value||0);payload.best_of=Number($("#seriesBestOf").value||3);payload.depth=Number($("#seriesDepth").value||3);payload.branch_width=Number($("#seriesBranch").value||2);payload.assignment_limit=2;payload.limit=5;
  box.innerHTML=`<div class="decision-empty"><b>Otimizando para a série…</b><span>Calculando mapa robusto, pool restante e probabilidade condicional do Bo${payload.best_of}.</span></div>`;
  try{const x=await post("/api/v18/draft/series-plan",payload);renderSeriesPlannerV18(x)}catch(e){box.innerHTML=`<div class="decision-empty error"><b>Falha no Series Planner.</b><span>${esc(e.message)}</span></div>`}
}
function poolMiniV18(pool){
 if(!pool)return "—";return `${Number(pool.quality*100).toFixed(1)} · bottleneck ${Number(pool.bottleneck*100).toFixed(1)}`;
}
function renderSeriesPlannerV18(x){
 const box=$("#seriesResultsV18");if(!x.results?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhum plano para a série.</b></div>`;return}
 const mapOrder=[...x.results].sort((a,b)=>b.robust_probability_root-a.robust_probability_root).map(r=>r.root_action.champion);
 box.innerHTML=`<div class="series-summary-v18"><div><small>PLACAR</small><b>${x.team_a} ${x.score_a}–${x.score_b} ${x.team_b}</b><span>${x.best_of===3?"Bo3":"Bo5"}</span></div><div><small>SÉRIE ANTES DA AÇÃO</small><b>${pct(x.baseline_series_probability_root)}</b><span>${x.root_team}</span></div><div><small>FUTURO BASE</small><b>${pct(x.baseline_future_map_probability_team_a)}</b><span>mapa neutro experimental · ${x.team_a}</span></div><div class="experimental"><small>STATUS</small><b>Series objective</b><span>${Math.round(x.elapsed_ms)} ms</span></div></div>
 <div class="series-cards-v18">${x.results.map((r,i)=>{const mapRank=mapOrder.indexOf(r.root_action.champion)+1;return `<article class="series-card-v18 ${i===0?"best":""}"><div class="series-rank-v18"><span>${i+1}</span><div><b>${r.root_action.action_type==="BAN"?"BAN ":""}${r.root_action.champion}</b><small>rank do mapa: #${mapRank} · ${r.root_action.slot}${mapRank>i+1?` · <em class="series-up-v18">↑ ganha valor na série</em>`:""}</small></div><strong>${pct(r.series_probability_root)}<small>série · EXP</small></strong></div>
 <div class="series-metrics-v18"><div><small>MAPA ROBUSTO</small><b>${pct(r.robust_probability_root)}</b></div><div><small>MAPA FUTURO</small><b>${pct(r.future_map_probability_root)}</b></div><div><small>Δ SÉRIE</small><b class="${r.series_delta_vs_baseline_pp>=0?"positive":"negative"}">${r.series_delta_vs_baseline_pp>=0?"+":""}${Number(r.series_delta_vs_baseline_pp).toFixed(2)} pp</b></div><div><small>CONSUMO FEARLESS</small><b>${r.known_consumption_count}</b><span>champions conhecidos/modelados</span></div></div>
 <div class="pool-grid-v18"><div><small>${x.team_a} · POOL FUTURO</small><b>${poolMiniV18(r.future_pool?.pool_a)}</b></div><div><small>${x.team_b} · POOL FUTURO</small><b>${poolMiniV18(r.future_pool?.pool_b)}</b></div></div>
 <div class="principal-variation-v15"><small>LINHA MODELADA DO MAPA ATUAL</small><div>${(r.principal_variation||[]).map(a=>jointActionChipV17(a,x.root_team)).join(`<i>→</i>`)}</div></div></article>`}).join("")}</div>
 <div class="strategy-explain-v14"><b>V18:</b> a ordenação final usa o objetivo da série. “Série” é cálculo probabilístico correto dado p(map atual) e p(map futuro), mas p(map futuro) é uma extrapolação experimental do champion pool restante. Por isso esta camada não recebe status Production.</div>`;
}

const JOINT_SEQ_V17=["B1BAN","R1BAN","B2BAN","R2BAN","B3BAN","R3BAN","B1","R1","R2","B2","B3","R3","R4BAN","B4BAN","R5BAN","B5BAN","R4","B4","B5","R5"];
window.syncJointContextV17=function(){
  const slot=$("#jointRootSlot")?.value||"B1BAN",x=strategyTeamForSlotV14(slot),type=slot.endsWith("BAN")?"BAN":"PICK";
  if($("#jointContext"))$("#jointContext").innerHTML=`<small>PRÓXIMA AÇÃO</small><b>${esc(x.team||"—")}</b><span>${x.sideName} · ${slot} · ${type}</span>`;
  if($("#jointSequenceV17")){
    const idx=JOINT_SEQ_V17.indexOf(slot);
    $("#jointSequenceV17").innerHTML=JOINT_SEQ_V17.map((s,i)=>`<span class="${i===idx?"current":i<idx?"done":""}"><b>${s}</b><small>${s.endsWith("BAN")?"ban":"pick"}</small></span>`).join("");
  }
}
window.runJointPlannerV17=async function(){
  const box=$("#jointResultsV17"),payload=draftPayloadV13();
  payload.root_action_slot=$("#jointRootSlot").value;payload.depth=Number($("#jointDepth").value||3);payload.branch_width=Number($("#jointBranch").value||2);payload.assignment_limit=Number($("#jointAssignments").value||2);payload.limit=5;
  box.innerHTML=`<div class="decision-empty"><b>Planejando sequência…</b><span>Bans e picks são avaliados no mesmo minimax.</span></div>`;
  try{const x=await post("/api/v17/draft/joint-plan",payload);renderJointPlannerV17(x)}catch(e){box.innerHTML=`<div class="decision-empty error"><b>Falha no Joint Planner.</b><span>${esc(e.message)}</span></div>`}
}
function jointActionChipV17(a,rootTeam){
  const ban=a.action_type==="BAN";
  return `<span class="${a.team===rootTeam?"ours":"theirs"} ${ban?"ban":"pick"}"><b>${a.slot}</b><em>${a.team}</em><strong>${ban?"BAN ":""}${a.champion}</strong><small>${ban?(a.summary||"ban"):((a.role_options||[]).map(x=>x.role.toUpperCase()).join("/"))}</small></span>`;
}
function renderJointPlannerV17(x){
 const box=$("#jointResultsV17");if(!x.results?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhum plano legal.</b></div>`;return}
 box.innerHTML=`<div class="tree-summary-v15"><div><small>RAIZ</small><b>${x.root_team}</b><span>${x.root_action_slot} · ${x.root_action_type}</span></div><div><small>ANTES</small><b>${pct(x.current_probability_root)}</b><span>flex-aware leaf</span></div><div><small>BUSCA</small><b>${x.depth} ações · beam ${x.branch_width}</b><span>${x.model_states_evaluated} estados V8</span></div><div class="experimental"><small>STATUS</small><b>Joint minimax</b><span>${Math.round(x.elapsed_ms)} ms</span></div></div>
 <div class="tree-cards-v15">${x.results.map((r,i)=>`<article class="tree-card-v15 ${i===0?"best":""}"><div class="tree-rank-v15"><span>${i+1}</span><div><b>${r.root_action.action_type==="BAN"?"BAN ":""}${r.root_action.champion}</b><small>${r.root_action.action_type==="BAN"?(r.root_action.summary||""):`${r.root_action.role_uncertainty||1} role(s) plausíveis`}</small></div></div>
 <div class="tree-metrics-v15"><div><small>IMEDIATO</small><strong>${pct(r.immediate_probability_root)}</strong><span>${r.root_action.action_type==="BAN"?"ban não muda V8 sozinho":"após ação"}</span></div><div><small>ROBUSTO</small><strong>${pct(r.robust_probability_root)}</strong><span>após sequência mista</span></div><div class="${r.response_penalty_pp>1?"fragile":""}"><small>RESPOSTA</small><strong>${r.response_penalty_pp>=0?"−":"+"}${Math.abs(Number(r.response_penalty_pp)).toFixed(1)} pp</strong><span>efeito da continuação</span></div><div><small>Δ ATUAL</small><strong class="${r.robust_delta_vs_current_pp>=0?"positive":"negative"}">${r.robust_delta_vs_current_pp>=0?"+":""}${Number(r.robust_delta_vs_current_pp).toFixed(1)} pp</strong><span>leaf robusto</span></div></div>
 <div class="principal-variation-v15"><small>PLANO ROBUSTO</small><div>${(r.principal_variation||[]).map(a=>jointActionChipV17(a,x.root_team)).join(`<i>→</i>`)}</div></div></article>`).join("")}</div>
 <div class="strategy-explain-v14"><b>V17:</b> ban e pick agora estão na mesma árvore. O ban não recebe uma “win probability inventada”; seu valor aparece porque altera quais respostas/picks continuam legais nos nós seguintes.</div>`;
}

window.syncFlexTreeContextV16=function(){
  const slot=$("#flexTreeRootSlot")?.value||"B1",x=strategyTeamForSlotV14(slot);
  if($("#flexTreeContext"))$("#flexTreeContext").innerHTML=`<small>RAIZ FLEX</small><b>${esc(x.team||"—")}</b><span>${x.sideName} · ${slot} · role aberta</span>`;
}
window.runFlexTreeV16=async function(){
  const box=$("#flexTreeResultsV16"),payload=draftPayloadV13();
  payload.root_slot=$("#flexTreeRootSlot").value;
  payload.depth=Number($("#flexTreeDepth").value||2);
  payload.branch_width=Number($("#flexTreeBranch").value||2);
  payload.assignment_limit=Number($("#flexTreeAssignments").value||2);
  payload.limit=5;
  box.innerHTML=`<div class="decision-empty"><b>Explorando flex uncertainty…</b><span>Champions novos permanecem sem role até o leaf.</span></div>`;
  try{const x=await post("/api/v16/draft/flex-tree",payload);renderFlexTreeV16(x)}
  catch(e){box.innerHTML=`<div class="decision-empty error"><b>Falha no Flex Tree.</b><span>${esc(e.message)}</span></div>`}
}
function flexRoleBadgesV16(a){
  return (a.role_options||[]).map(r=>`<span>${String(r.role).toUpperCase()} · ${r.player}</span>`).join("");
}
function assignmentTextV16(st){
  if(!st?.picks)return "—";
  return ["top","jng","mid","bot","sup"].filter(r=>st.picks[r]).map(r=>`${r.toUpperCase()}: ${st.picks[r]}`).join(" · ");
}
function renderFlexTreeV16(x){
  const box=$("#flexTreeResultsV16");
  if(!x.results?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhum ramo flex plausível.</b></div>`;return}
  box.innerHTML=`<div class="tree-summary-v15">
    <div><small>RAIZ</small><b>${x.root_team} · ${x.root_slot}</b><span>role não fixada</span></div>
    <div><small>ANTES</small><b>${pct(x.current_probability_root)}</b><span>role-resolution minimax</span></div>
    <div><small>BUSCA</small><b>${x.depth} ações · beam ${x.branch_width}</b><span>${x.model_states_evaluated} V8 · ${x.assignment_states_evaluated} combinações</span></div>
    <div class="experimental"><small>STATUS</small><b>Flex minimax</b><span>experimental · ${Math.round(x.elapsed_ms)} ms</span></div></div>
    <div class="tree-cards-v15">${x.results.map((r,i)=>`<article class="tree-card-v15 ${i===0?"best":""}">
      <div class="tree-rank-v15"><span>${i+1}</span><div><b>${r.root_action.champion}</b><small>${r.root_action.role_uncertainty} role(s) plausíveis</small></div><button onclick="toast('Use o pick e mantenha a role aberta no planejamento')">Flex</button></div>
      <div class="flex-role-badges-v16">${flexRoleBadgesV16(r.root_action)}</div>
      <div class="tree-metrics-v15"><div><small>IMEDIATO FLEX</small><strong>${pct(r.immediate_flex_probability_root)}</strong><span>roles ainda incertas</span></div><div><small>ROBUSTO</small><strong>${pct(r.minimax_flex_probability_root)}</strong><span>resposta + roles</span></div><div class="${r.response_penalty_pp>1?"fragile":""}"><small>PENALIDADE</small><strong>${r.response_penalty_pp>=0?"−":"+"}${Math.abs(Number(r.response_penalty_pp)).toFixed(1)} pp</strong><span>melhor resposta modelada</span></div><div><small>Δ ATUAL</small><strong class="${r.robust_delta_vs_current_pp>=0?"positive":"negative"}">${r.robust_delta_vs_current_pp>=0?"+":""}${Number(r.robust_delta_vs_current_pp).toFixed(1)} pp</strong><span>leaf robusto</span></div></div>
      <div class="principal-variation-v15"><small>PRINCIPAL VARIATION</small><div>${(r.principal_variation||[]).map(a=>`<span class="${a.team===x.root_team?"ours":"theirs"}"><b>${a.slot}</b><em>${a.team}</em><strong>${a.champion}</strong><small>${(a.role_options||[]).map(z=>z.role.toUpperCase()).join("/")}</small></span>`).join(`<i>→</i>`)}</div></div>
      <div class="flex-leaf-v16"><div><small>ROLE RESOLUTION · ${x.root_team}</small><b>${assignmentTextV16(r.leaf?.root_assignment)}</b></div><div><small>PIOR RESPOSTA DE ROLES</small><b>${assignmentTextV16(r.leaf?.opponent_assignment)}</b></div></div>
    </article>`).join("")}</div>
    <div class="strategy-explain-v14"><b>V16:</b> o valor flex passa a existir dentro da árvore. O time da raiz escolhe sua melhor atribuição de roles plausível e o adversário escolhe a atribuição que mais reduz a avaliação no leaf. Continua sendo análise de robustez do V8, não nova probabilidade calibrada.</div>`;
}

window.syncTreeContextV15=function(){
  const slot=$("#treeRootSlot")?.value||"B1",x=strategyTeamForSlotV14(slot);
  if($("#treeRootContext"))$("#treeRootContext").innerHTML=`<small>RAIZ</small><b>${esc(x.team||"—")}</b><span>${x.sideName} · ${slot}</span>`;
}
window.runDraftTreeV15=async function(){
  const box=$("#draftTreeResultsV15"),payload=draftPayloadV13();
  payload.root_slot=$("#treeRootSlot").value;
  payload.root_role=$("#treeRootRole").value;
  payload.depth=Number($("#treeDepth").value||3);
  payload.branch_width=Number($("#treeBranch").value||2);
  payload.candidates_per_role=Number($("#treePerRole").value||2);
  payload.limit=6;
  box.innerHTML=`<div class="decision-empty"><b>Explorando árvore…</b><span>O custo cresce com profundidade e beam. A busca é intencionalmente limitada para continuar responsiva.</span></div>`;
  const t0=performance.now();
  try{
    const x=await post("/api/v15/draft/tree",payload);
    renderDraftTreeV15(x,performance.now()-t0);
  }catch(e){
    box.innerHTML=`<div class="decision-empty error"><b>Falha no Draft Tree.</b><span>${esc(e.message)}</span></div>`;
  }
}
function treePathV15(path,rootTeam){
  return (path||[]).map((a,i)=>{
    const cls=a.team===rootTeam?"ours":"theirs";
    return `<span class="${cls}"><b>${a.slot}</b><em>${a.team}</em><strong>${a.champion}</strong><small>${String(a.role).toUpperCase()}</small></span>`;
  }).join(`<i>→</i>`);
}
function renderDraftTreeV15(x,clientMs){
  const box=$("#draftTreeResultsV15");
  if(!x.results?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhuma linha encontrada.</b></div>`;return}
  box.innerHTML=`<div class="tree-summary-v15">
      <div><small>TIME DA RAIZ</small><b>${x.root_team}</b><span>${x.root_slot} · ${String(x.root_role).toUpperCase()}</span></div>
      <div><small>ANTES DA BUSCA</small><b>${pct(x.current_probability_root)}</b><span>V8 no estado parcial</span></div>
      <div><small>ÁRVORE</small><b>${x.depth} ações · beam ${x.branch_width}</b><span>${x.nodes_evaluated} nós · ${x.model_states_evaluated} estados V8 · ${Math.round(x.elapsed_ms)} ms</span></div>
      <div class="experimental"><small>STATUS</small><b>Experimental</b><span>minimax/beam · ${Math.round(clientMs)} ms total</span></div>
    </div>
    <div class="tree-cards-v15">
      ${x.results.map((r,i)=>`<article class="tree-card-v15 ${i===0?"best":""}">
        <div class="tree-rank-v15"><span>${i+1}</span><div><b>${r.root_action.champion}</b><small>${r.root_action.player} · ${String(r.root_action.role).toUpperCase()}</small></div>
          <button onclick="useDecisionPickV13('${r.root_action.side}','${r.root_action.role}','${String(r.root_action.champion).replaceAll("'","\\'")}')">Usar</button></div>
        <div class="tree-metrics-v15">
          <div><small>IMEDIATO</small><strong>${pct(r.immediate_probability_root)}</strong><span>após nosso pick</span></div>
          <div><small>ROBUSTO / MINIMAX</small><strong>${pct(r.minimax_probability_root)}</strong><span>após melhor resposta modelada</span></div>
          <div class="${r.response_penalty_pp>1?"fragile":""}"><small>PENALIDADE DA RESPOSTA</small><strong>${r.response_penalty_pp>=0?"−":"+"}${Math.abs(Number(r.response_penalty_pp)).toFixed(1)} pp</strong><span>${r.response_penalty_pp>2?"pick sensível à resposta":"relativamente robusto"}</span></div>
          <div><small>Δ VS ESTADO ATUAL</small><strong class="${r.robust_delta_vs_current_pp>=0?"positive":"negative"}">${r.robust_delta_vs_current_pp>=0?"+":""}${Number(r.robust_delta_vs_current_pp).toFixed(1)} pp</strong><span>no pior ramo escolhido</span></div>
        </div>
        <div class="principal-variation-v15"><small>PRINCIPAL VARIATION</small><div>${treePathV15(r.principal_variation,x.root_team)}</div></div>
      </article>`).join("")}
    </div>
    <div class="strategy-explain-v14"><b>Como ler:</b> “Robusto/minimax” é o valor do leaf V8 depois de uma sequência onde nosso lado maximiza e o adversário minimiza a chance do time da raiz, dentro do beam modelado. É uma análise de robustez, não uma nova probabilidade calibrada.</div>`;
}
window.loadFlexFromDraftV15=function(){
  const side=$("#flexTeamV15").value,roles=["top","jng","mid","bot","sup"];
  const vals=roles.map(r=>$(`#${side}_${r}`)?.value).filter(Boolean);
  $("#flexChampionsV15").value=vals.join(", ");
  if(!vals.length)toast("Nenhum pick selecionado para esse time");
}
window.resolveFlexV15=async function(){
  const box=$("#flexResultsV15"),side=$("#flexTeamV15").value;
  const team=side==="a"?$("#draftTeamA").value:$("#draftTeamB").value;
  const champions=$("#flexChampionsV15").value.split(",").map(x=>x.trim()).filter(Boolean);
  if(!champions.length){toast("Informe ao menos um champion");return}
  box.innerHTML=`<div class="decision-empty"><b>Resolvendo roles plausíveis…</b></div>`;
  try{
    const x=await post("/api/v15/draft/flex-resolve",{team,champions,limit:8});
    renderFlexV15(x);
  }catch(e){
    box.innerHTML=`<div class="decision-empty error"><b>Falha no Flex Resolver.</b><span>${esc(e.message)}</span></div>`;
  }
}
function renderFlexV15(x){
  const box=$("#flexResultsV15");
  if(!x.assignments?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhuma atribuição plausível encontrada.</b><span>Isso pode indicar que os champions não têm evidência suficiente nas roles/jogadores atuais.</span></div>`;return}
  box.innerHTML=`<div class="flex-summary-v15"><div><small>TIME</small><b>${x.team}</b><span>${x.champions.join(" · ")}</span></div><div><small>ATRIBUIÇÕES PLAUSÍVEIS</small><b>${x.assignment_count}</b><span>mostrando ${x.assignments.length}</span></div><div class="experimental"><small>STATUS</small><b>Experimental</b><span>assignment support</span></div></div>
    <div class="flex-assignment-grid-v15">${x.assignments.map((a,i)=>`<article class="${i===0?"best":""}">
      <div class="flex-assignment-head"><span>${i+1}</span><b>Score ${Number(a.score_pp_equiv).toFixed(2)} pp-eq</b><strong>Evidência ${a.evidence_confidence}/100</strong></div>
      <div class="flex-role-list-v15">${["top","jng","mid","bot","sup"].map(role=>{
        const v=a.assignment[role];if(!v)return "";
        return `<div><small>${role.toUpperCase()}</small><b>${v.champion}</b><span>${v.player}</span><em>${v.player_games}g player · ${v.meta_games}g meta</em></div>`;
      }).join("")}</div></article>`).join("")}</div>
    <div class="strategy-explain-v14"><b>Importante:</b> o Flex Resolver não escolhe a role “verdadeira”. Ele mantém alternativas plausíveis com base em uso observado. Isso é especialmente útil em picks precoces, quando atribuir uma role cedo demais destruiria justamente o valor informacional do flex.</div>`;
}

window.strategyPickV14=async function(){
  const box=$("#strategyPickResultsV14"),payload=draftPayloadV13();
  payload.pick_slot=$("#strategyPickSlot").value;
  payload.target_role=$("#strategyRole").value;
  payload.limit=Number($("#strategyLimit").value||8);
  box.innerHTML=`<div class="decision-empty"><b>Calculando estratégia…</b><span>Simulando picks legais, flex, denial e custo do pool futuro.</span></div>`;
  try{
    const x=await post("/api/v14/draft/strategy-pick",payload);
    renderStrategyPickV14(x);
  }catch(e){
    box.innerHTML=`<div class="decision-empty error"><b>Falha no Strategy Engine.</b><span>${esc(e.message)}</span></div>`;
  }
}
function renderStrategyPickV14(x){
  const box=$("#strategyPickResultsV14");
  if(!x.candidates?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhum candidato legal.</b><span>Revise picks, Fearless e role.</span></div>`;return}
  box.innerHTML=`<div class="strategy-summary-v14">
      <div><small>SLOT</small><b>${x.pick_slot}</b><span>${x.target_team} · ${x.player} · ${String(x.target_role).toUpperCase()}</span></div>
      <div><small>ESTADO ATUAL</small><b>${pct(x.current_probability_target_team)}</b><span>probabilidade do mapa antes deste pick</span></div>
      <div><small>MAPAS FUTUROS ESPERADOS</small><b>${Number(x.expected_future_maps||0).toFixed(2)}</b><span>Game 3 é ponderado pela chance de acontecer</span></div>
      <div class="experimental"><small>POLÍTICA</small><b>Experimental</b><span>não é probabilidade calibrada</span></div>
    </div>
    <div class="strategy-pick-table-v14">
      <div class="strategy-head-v14"><span>#</span><span>Pick</span><span>V8 após pick</span><span>Δ imediato</span><span>Δ estratégia</span><span>Flex</span><span>Denial</span><span>Custo futuro</span><span>Evidência</span><span></span></div>
      ${x.candidates.map((c,i)=>`<div class="strategy-row-v14 ${i===0?"best":""}">
        <span>${i+1}</span>
        <div><b>${c.champion}</b><small>${c.player_games}g do jogador · ${c.meta_games}g meta</small></div>
        <strong>${pct(c.probability_target_team)}</strong>
        <em class="${c.decision_delta_target_pp>=0?"positive":"negative"}">${c.decision_delta_target_pp>=0?"+":""}${Number(c.decision_delta_target_pp).toFixed(1)} pp</em>
        <em class="${c.strategy_delta_pp_equiv>=0?"positive":"negative"}">${c.strategy_delta_pp_equiv>=0?"+":""}${Number(c.strategy_delta_pp_equiv).toFixed(1)} pp-eq</em>
        <span title="${Object.entries(c.flex_roles||{}).map(([r,g])=>`${r}:${g}g`).join(" · ")}">${Number(c.flex_score||0).toFixed(2)} · +${Number(c.flex_bonus_pp_equiv||0).toFixed(1)}</span>
        <span>${c.denial?.player?`${c.denial.player} · +${Number(c.denial_bonus_pp_equiv||0).toFixed(1)}`:"—"}</span>
        <span class="${c.future_pool_cost_pp_equiv>0?"cost":""}">${c.future_pool_cost_pp_equiv>0?`−${Number(c.future_pool_cost_pp_equiv).toFixed(1)}`:"0.0"} pp-eq</span>
        <span>${c.evidence_confidence}/100</span>
        <button onclick="useDecisionPickV13('${x.target_side}','${x.target_role}','${String(c.champion).replaceAll("'","\\'")}')">Usar</button>
      </div>`).join("")}
    </div>
    <div class="strategy-explain-v14"><b>Δ estratégia não é uma nova win probability.</b> Ele serve apenas para ordenar decisões: começa no delta V13 e adiciona flex/denial, descontando o custo estimado de perder esse champion nos próximos mapas do Fearless.</div>`;
}
window.banStrategyV14=async function(){
  const box=$("#strategyBanResultsV14"),payload=draftPayloadV13();
  payload.ban_slot=$("#strategyBanSlot").value;
  payload.limit=10;
  box.innerHTML=`<div class="decision-empty"><b>Analisando bans…</b><span>Comfort adversário, meta, flex e escassez do pool.</span></div>`;
  try{
    const x=await post("/api/v14/draft/ban",payload);
    renderBanStrategyV14(x);
  }catch(e){
    box.innerHTML=`<div class="decision-empty error"><b>Falha no Ban Engine.</b><span>${esc(e.message)}</span></div>`;
  }
}
function renderBanStrategyV14(x){
  const box=$("#strategyBanResultsV14");
  if(!x.candidates?.length){box.innerHTML=`<div class="decision-empty"><b>Nenhum ban candidato encontrado.</b></div>`;return}
  const max=Math.max(...x.candidates.map(c=>Number(c.ban_priority_score||0)),1);
  box.innerHTML=`<div class="strategy-summary-v14">
    <div><small>BAN SLOT</small><b>${x.ban_slot}</b><span>${x.banning_team} bane</span></div>
    <div><small>ALVO</small><b>${x.opponent_team}</b><span>roles em aberto: ${x.unfilled_opponent_roles.join(", ")||"nenhuma"}</span></div>
    <div class="experimental"><small>POLÍTICA</small><b>Experimental</b><span>score relativo, não probabilidade</span></div></div>
    <div class="ban-table-v14">
      ${x.candidates.map((c,i)=>`<div class="ban-row-v14 ${i===0?"best":""}">
        <span>${i+1}</span><div><b>${c.champion}</b><small>${c.target_player||"meta"} · ${String(c.target_role||"flex").toUpperCase()}</small></div>
        <div class="ban-meter"><i style="width:${Math.max(3,(Number(c.ban_priority_score||0)/max)*100)}%"></i></div>
        <strong title="score bruto ${Number(c.ban_priority_score||0).toFixed(2)}">${Number(c.relative_priority||0).toFixed(0)}/100</strong>
        <span>${c.player_games}g · mastery ${pct(c.player_mastery)}</span>
        <span>${c.meta_games}g meta · ${pct(c.meta_wr)}</span>
        <span>${c.role_count>1?`${c.role_count} roles · flex ${Number(c.flex_score).toFixed(2)}`:"1 role"}</span>
        <span>${c.evidence_confidence}/100</span>
        <button onclick="appendBanV14('${String(c.champion).replaceAll("'","\\'")}')">Banir</button>
      </div>`).join("")}
    </div>
    <div class="strategy-explain-v14"><b>Ban Priority</b> é normalizado para 100 no melhor candidato daquela consulta e combina denial de comfort, força no meta, flex e escassez das alternativas. Não é estimativa causal do quanto o ban aumenta a chance de vitória.</div>`;
}
window.appendBanV14=function(champ){
  const input=$("#draftBans"),vals=input.value.split(",").map(x=>x.trim()).filter(Boolean);
  if(!vals.some(x=>x.toLowerCase()===champ.toLowerCase()))vals.push(champ);
  input.value=vals.join(", ");
  toast(`${champ} adicionado aos bans`);
  syncStrategyContextV14();
}

window.recommendDraftV13=async function(){
  const box=$("#decisionResultsV13"),payload=draftPayloadV13();
  if(payload.team_a===payload.team_b){toast("Escolha dois times diferentes");return}
  payload.target_side=$("#decisionSide").value;payload.target_role=$("#decisionRole").value;
  payload.limit=Number($("#decisionLimit").value||8);
  box.innerHTML=`<div class="decision-empty"><b>Simulando candidatos…</b><span>Isso roda o Draft Engine para cada opção legal.</span></div>`;
  try{
    const x=await post("/api/v13/draft/recommend",payload);
    renderDecisionV13(x);
  }catch(e){
    box.innerHTML=`<div class="decision-empty error"><b>Não consegui gerar as sugestões.</b><span>${esc(e.message)}</span></div>`;
  }
}
function renderDecisionV13(x){
  const box=$("#decisionResultsV13"),team=x.target_team,role=x.target_role;
  if(!x.candidates?.length){
    box.innerHTML=`<div class="decision-empty"><b>Nenhum candidato legal encontrado.</b><span>Verifique Fearless, picks já usados e champion pool.</span></div>`;return;
  }
  box.innerHTML=`<div class="decision-summary-v13"><div><small>TIME</small><b>${team}</b><span>${x.player} · ${String(role).toUpperCase()}</span></div>
    <div><small>ANTES DO PICK</small><b>${pct(x.current_probability_target_team)}</b><span>estado parcial do draft</span></div>
    <div><small>STATUS</small><b>Experimental</b><span>decision support</span></div></div>
    <div class="decision-table-v13">
      <div class="decision-head-v13"><span>#</span><span>Campeão</span><span>Modelo</span><span>Δ decisão</span><span>Jogador</span><span>Meta</span><span>Evidência</span><span></span></div>
      ${x.candidates.map((c,i)=>`<div class="decision-row-v13 ${i===0?"best":""}">
        <span>${i+1}</span><div><b>${c.champion}</b><small>${esc(c.reason||"")}</small></div>
        <strong>${pct(c.probability_target_team)}</strong>
        <em class="${c.decision_delta_target_pp>=0?"positive":"negative"}" title="Delta com shrinkage de evidência">${c.decision_delta_target_pp>=0?"+":""}${Number(c.decision_delta_target_pp).toFixed(1)} pp</em>
        <span>${c.player_games}g · ${c.player_eb==null?"—":pct(c.player_eb)}</span>
        <span>${c.meta_games}g · ${c.meta_wr==null?"—":pct(c.meta_wr)}</span>
        <span>${c.evidence_confidence}/100</span>
        <button onclick="useDecisionPickV13('${x.target_side}','${x.target_role}','${String(c.champion).replaceAll("'","\\'")}')">Usar</button>
      </div>`).join("")}
    </div>
    <div class="decision-warning-v13"><b>Como interpretar:</b> “Modelo” é a probabilidade bruta V8 após o pick. O ranking e o “Δ decisão” sofrem shrinkage quando há pouca experiência do jogador ou pouca amostra do campeão na role. A política de recomendação ainda é experimental.</div>`;
}
window.useDecisionPickV13=function(side,role,champ){
  const el=$(`#${side}_${role}`);if(el){el.value=champ;el.dispatchEvent(new Event("change"))}
  toast(`${champ} aplicado ao draft`);
  const all=["top","jng","mid","bot","sup"].flatMap(r=>[$(`#a_${r}`)?.value,$(`#b_${r}`)?.value]);
  if(all.every(Boolean))evaluateDraftV12();
}

function renderDraftResultV12(x){
  const p=Number(x.draft_game_probability_team_a),base=Number(x.game_baseline_probability_team_a),fav=favorite(p,x.team_a,x.team_b);
  const interval=x.posterior_interval_80||{};
  const roleRows=(x.roles||[]).map(r=>{
    const ca=r.team_a_champion||"—",cb=r.team_b_champion||"—";
    const cnt=r.counter_a_vs_b;
    return `<div class="draft-role-result"><span>${String(r.role).toUpperCase()}</span>
      <div><b>${r.team_a_player}</b><strong>${ca}</strong><small>mastery EB ${pct(r.team_a_mastery_eb)}${r.team_a_mastery?` · ${r.team_a_mastery.games}g`:""}</small></div>
      <div class="lane-edge">${cnt?`<b>${cnt.games} H2H</b><span>contexto</span>`:"<span>sem H2H suficiente</span>"}</div>
      <div class="right"><b>${r.team_b_player}</b><strong>${cb}</strong><small>mastery EB ${pct(r.team_b_mastery_eb)}${r.team_b_mastery?` · ${r.team_b_mastery.games}g`:""}</small></div>
    </div>`;
  }).join("");
  const patch=x.patch_model;
  $("#draftResultV12").innerHTML=`<section class="panel draft-result-v12">
    <div class="draft-result-hero"><div><small>ANTES DO DRAFT</small><strong>${x.team_a} ${pct(base)}</strong><span>baseline do mapa</span></div>
      <div class="main"><small>APÓS O DRAFT</small><h2>${fav.team} ${pct(fav.p)}</h2><span>${advantage(p)} · Δ ${Number(x.draft_delta_pp).toFixed(1)} pp para ${x.team_a}</span></div>
      <div><small>INTERVALO 80%</small><strong>${pct(interval.low)}–${pct(interval.high)}</strong><span>incerteza das amostras</span></div>
      <div><small>COBERTURA</small><strong>${x.evidence_confidence}/100</strong><span>${x.evidence_label}</span></div></div>
    ${x.fearless_illegal?.length?`<div class="fearless-warning"><b>Draft inválido no Fearless:</b> ${x.fearless_illegal.join(", ")}</div>`:""}
    <div class="draft-role-results">${roleRows}</div>
    <div class="draft-bottom-v12"><div><small>Sinergia</small><b>${x.team_a} ${pct(x.team_a_synergy)} · ${x.team_b} ${pct(x.team_b_synergy)}</b></div>
      <div><small>Mastery diff</small><b>${Number(x.mastery_diff||0).toFixed(3)}</b></div>
      <div><small>Patch</small><b>${patch?.active?`overlay experimental ${pct(patch.experimental_probability_team_a)}`:"sem peso preditivo"}</b></div></div>
  </section>`;
}

