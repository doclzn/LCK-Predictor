// Página Model: métricas, governança, saúde das fontes
function shortHash(x){return x?String(x).slice(0,10)+"…":"—"}
function govDecisionLabel(x){return ({COLLECTING:"Coletando",REFERENCE:"Referência",ELIGIBLE_FOR_REVIEW:"Elegível para review",REJECTED_PROSPECTIVE:"Rejeitado",INCONCLUSIVE_CONTINUE:"Inconclusivo · continuar",BLOCKED_INTEGRITY:"Bloqueado · integridade"})[x]||x||"—"}
function govDecisionClass(x){x=String(x||"").toLowerCase();if(x.includes("eligible")||x==="reference")return "good";if(x.includes("reject")||x.includes("blocked")||x.includes("drift"))return "bad";return "warn"}
function v19CandidateName(x){return ({core:"Core surrogate",core_pool_exhaustion:"Core + Fearless exhaustion",core_pool_remaining:"Core + remaining pool",core_flex:"Core + flex",core_pool_flex:"Core + exhaustion + flex"})[x]||x}
function v19Verdict(x){return ({REFERENCE:"Referência",INCONCLUSIVE:"Inconclusivo",RETROSPECTIVE_REJECT:"Rejeitado retrospectivamente",RETROSPECTIVE_SUPPORT:"Suporte retrospectivo"})[x]||x}
function v19StatusClass(x){x=String(x||"").toLowerCase();if(x.includes("reject")||x.includes("fail")||x.includes("blocked"))return "bad";if(x.includes("support")||x.includes("pass")||x.includes("reference"))return "good";return "warn"}
function v19Delta(x,d=4){if(x==null)return "—";x=Number(x);return `${x>0?"+":""}${x.toFixed(d)}`}
function v19CI(b,key){if(!b)return "—";const lo=b[`${key}_lo`],hi=b[`${key}_hi`];return `[${Number(lo).toFixed(4)}, ${Number(hi).toFixed(4)}]`}
async function renderModel(){
  setNav("model");loading();
  const [audit,models,sources,val,liveLab,gov]=await Promise.all([api("/api/statistics/audit"),api("/api/riot/models"),api("/api/riot/source-health"),api("/api/v19/validation"),api("/api/v20/live-readiness"),api("/api/v21/governance")]);
  const prod=audit.audit.find(x=>x.stage==="V8 Production")||{};
  const ex=val.experiments||[],pool=ex.find(x=>x.candidate==="core_pool_exhaustion"),flex=ex.find(x=>x.candidate==="core_flex"),core=ex.find(x=>x.candidate==="core");
  const subgroup=(candidate,name)=>(val.subgroups||[]).find(x=>x.candidate===candidate&&x.subgroup===name)||{};
  page(`<section class="page-head"><div><span class="eyebrow">MODEL · VALIDATION · GOVERNANCE</span><h1>Uma métrica não pode mudar depois de ver a resposta.</h1><p>A V21 adiciona um lockbox prospectivo: modelos, thresholds e protocolo live recebem hashes antes do teste futuro. Qualquer drift bloqueia a revisão.</p></div></section>
    <section class="model-hero"><div><small>V8 ACCURACY</small><strong>${pct(prod.accuracy)}</strong><span>produção auditada</span></div><div><small>V8 LOG LOSS</small><strong>${Number(prod.log_loss||0).toFixed(3)}</strong><span>menor é melhor</span></div><div><small>V8 BRIER</small><strong>${Number(prod.brier||0).toFixed(3)}</strong><span>qualidade probabilística</span></div><div><small>V8 AUC</small><strong>${Number(prod.roc_auc||0).toFixed(3)}</strong><span>discriminação</span></div><div><small>V8 ECE</small><strong>${pct(audit.calibration?.ece)}</strong><span>calibração</span></div></section>

    <section class="governance-hero-v21 ${gov.integrity?.ok?"ok":"bad"}">
      <div><span class="eyebrow">PROSPECTIVE LOCKBOX</span><h2>${gov.integrity?.ok?"Integridade verificada":"Drift detectado"}</h2><p>${gov.integrity?.ok?"As definições congeladas conferem com o lock da release.":"Algum arquivo/modelo congelado não confere com o hash esperado. Promoção fica bloqueada."}</p></div>
      <div><small>CANDIDATAS CONGELADAS</small><strong>${gov.experiments?.length||0}</strong><span>cada mudança exige novo epoch</span></div>
      <div><small>CAPTURAS LEDGER</small><strong>${gov.ledger?.captures||0}</strong><span>prediction + feature hash</span></div>
      <div><small>LIVE PROTOCOL</small><strong>${gov.live_protocol?.hash_ok?"LOCKED":"DRIFT"}</strong><span>${shortHash(gov.live_protocol?.hash)}</span></div>
    </section>

    <section class="panel governance-policy-v21"><div class="section-head"><div><span class="eyebrow">GATE PRÉ-REGISTRADO</span><h2>Passar o gate não promove automaticamente.</h2><p>O máximo que a automação pode fazer é marcar uma candidata como elegível para review.</p></div><span class="governance-hash-v21">policy ${shortHash(gov.promotion_policy?.policy_hash)}</span></div>
      <div class="governance-review-grid-v21">${(gov.promotion_reviews||[]).map(r=>`<article class="${govDecisionClass(r.decision)}"><div><b>${v19CandidateName(r.candidate)}</b><span>${govDecisionLabel(r.decision)}</span></div><small>${r.games||0}/100 mapas · ${r.series_count||0}/40 séries</small><div class="governance-checks-v21"><i class="${r.sample_pass?"pass":""}">amostra</i><i class="${r.practical_pass?"pass":""}">efeito</i><i class="${r.uncertainty_pass?"pass":""}">IC95%</i><i class="${r.calibration_pass?"pass":""}">calibração</i></div>${r.reasons?.length?`<p>${esc(r.reasons.join(" · "))}</p>`:""}</article>`).join("")}</div>
      <div class="governance-rule-v21"><b>Anti-retuning:</b> ${esc(gov.promotion_policy?.anti_retuning||"")}</div>
    </section>

    <section class="panel live-protocol-v21"><div class="section-head"><div><span class="eyebrow">LIVE MODEL · PRÉ-REGISTRADO</span><h2>O test set continua fechado.</h2><p>O pipeline de treino já está especificado antes da amostra existir: split cronológico por mapa, famílias fixas, grid fixo e avaliação por checkpoints.</p></div><span class="live-ready-status ${gov.live_protocol?.readiness?.ready?"good":"warn"}">${gov.live_protocol?.readiness?.ready?"READY":"LOCKED"}</span></div>
      <div class="live-protocol-grid-v21"><div><small>PROTOCOLO</small><b>${gov.live_protocol?.protocol_id||"—"}</b><span>${shortHash(gov.live_protocol?.hash)}</span></div><div><small>SPLIT</small><b>65 / 15 / 20</b><span>mapas inteiros · ordem cronológica</span></div><div><small>SELEÇÃO</small><b>Validation only</b><span>família + C antes de abrir o test</span></div><div><small>TEST RUNS</small><b>${gov.live_protocol?.runs?.length||0}</b><span>mesmo protocol ID só pode abrir uma vez</span></div></div>
      <div class="prospective-rule-v19"><b>Primary evaluation:</b> ${esc(gov.live_protocol?.primary_evaluation||"")}</div>
    </section>

    <section class="validation-warning-v19"><div><span class="eyebrow">STATUS DO EXPERIMENTO</span><b>2026 não é mais um holdout cego do projeto.</b><p>${esc(val.status?.message||"")}</p></div><div><small>DATASET V19</small><strong>${val.dataset?.games||0}</strong><span>${val.dataset?.games_2025||0} mapas 2025 · ${val.dataset?.games_2026||0} mapas 2026 · ${val.dataset?.series||0} séries</span></div></section>

    <section class="panel validation-finding-v19"><div class="section-head"><div><span class="eyebrow">RESULTADO PRINCIPAL</span><h2>Fearless merece continuar sendo testado. Flex isolado, por enquanto, não.</h2></div></div>
      <div class="finding-grid-v19"><article class="${v19StatusClass(pool?.retrospective_verdict)}"><small>POOL EXHAUSTION</small><h3>${v19Verdict(pool?.retrospective_verdict)}</h3><p>LL ${Number(pool?.eval2026_log_loss||0).toFixed(4)} vs ${Number(core?.eval2026_log_loss||0).toFixed(4)} core · Δ ${v19Delta(pool?.delta_log_loss_vs_core)}</p><span>95% bootstrap ΔLL ${v19CI(pool?.bootstrap,"ll_delta")}. O intervalo ainda cruza zero.</span></article>
      <article class="${v19StatusClass(flex?.retrospective_verdict)}"><small>FLEX VALUE ISOLADO</small><h3>${v19Verdict(flex?.retrospective_verdict)}</h3><p>LL ${Number(flex?.eval2026_log_loss||0).toFixed(4)} · Brier ${Number(flex?.eval2026_brier||0).toFixed(4)}</p><span>O bootstrap ficou inteiramente do lado de piora para LL/Brier. Flex continua útil como contexto estratégico, mas não ganha peso preditivo central.</span></article></div>
    </section>

    <section class="panel validation-table-panel-v19"><div class="section-head"><div><h2>Auditoria retrospectiva das candidatas</h2><p>Hyperparâmetros escolhidos apenas em rolling-origin 2025. A coluna 2026 é retrospectiva, não “pristine external test”.</p></div></div>
      <div class="validation-table-v19"><div class="v19-head"><span>Candidata</span><span>Acc</span><span>Log Loss</span><span>Brier</span><span>Δ LL</span><span>Δ Brier</span><span>ECE</span><span>Veredito</span></div>
      ${ex.map(r=>`<div class="v19-row ${v19StatusClass(r.retrospective_verdict)}"><b>${v19CandidateName(r.candidate)}</b><span>${pct(r.eval2026_accuracy)}</span><span>${Number(r.eval2026_log_loss).toFixed(4)}</span><span>${Number(r.eval2026_brier).toFixed(4)}</span><span>${v19Delta(r.delta_log_loss_vs_core)}</span><span>${v19Delta(r.delta_brier_vs_core)}</span><span>${pct(r.eval2026_ece)}</span><strong>${v19Verdict(r.retrospective_verdict)}</strong></div>`).join("")}</div>
    </section>

    <section class="panel"><div class="section-head"><div><h2>Fearless: diagnóstico por game number</h2><p>Subgrupo secundário; não é usado para promover a feature.</p></div></div>
      <div class="subgroup-grid-v19">${["G1","G2+","G3+"].map(g=>{const a=subgroup("core",g),b=subgroup("core_pool_exhaustion",g);return `<div><small>${g} · ${b.n_games||0} MAPAS</small><b>Core LL ${Number(a.log_loss||0).toFixed(4)}</b><strong>+Exhaustion ${Number(b.log_loss||0).toFixed(4)}</strong><span>Acc ${pct(a.accuracy)} → ${pct(b.accuracy)}</span></div>`}).join("")}</div>
    </section>

    <section class="panel prospective-gate-v19"><div class="section-head"><div><span class="eyebrow">VERDADEIRO TESTE</span><h2>Prospective Gate</h2><p>Modelos congelados. Nenhum retuning até atingir o mínimo de jogos futuros.</p></div></div>
      <div class="gate-grid-v19">${(val.prospective_gate||[]).map(g=>{const gp=Math.min(100,(Number(g.games||0)/100)*100),sp=Math.min(100,(Number(g.series_count||0)/40)*100);return `<article><div><b>${v19CandidateName(g.candidate)}</b><span class="gate-status ${v19StatusClass(g.gate_status)}">${g.gate_status}</span></div><small>${g.games||0}/100 mapas · ${g.series_count||0}/40 séries</small><div class="gate-progress"><i style="width:${gp}%"></i></div><div class="gate-progress series"><i style="width:${sp}%"></i></div>${g.delta_log_loss_vs_core!=null?`<p>ΔLL ${v19Delta(g.delta_log_loss_vs_core)} · ΔBrier ${v19Delta(g.delta_brier_vs_core)}</p>`:"<p>Aguardando partidas futuras capturadas cedo.</p>"}</article>`}).join("")}</div>
      <div class="prospective-rule-v19"><b>Gate de promoção:</b> ${esc(val.promotion_rule||"")}</div>
    </section>

    <section class="panel live-readiness-v20"><div class="section-head"><div><span class="eyebrow">LIVE MODEL DATASET</span><h2>Coletar primeiro. Treinar depois.</h2><p>Uma linha compacta por minuto de jogo, somente enquanto o mapa está em andamento. Snapshots finais são excluídos do treino.</p></div><span class="live-ready-status ${liveLab.readiness?.ready?"good":"warn"}">${liveLab.readiness?.status||"EMPTY"}</span></div>
      <div class="live-readiness-summary-v20"><div><small>MAPAS ROTULADOS</small><b>${liveLab.readiness?.completed_maps||0}<em>/ ${liveLab.readiness?.thresholds?.maps||120}</em></b><span>${liveLab.readiness?.labeled_snapshots||0} checkpoints rotulados</span></div><div><small>TIMES COBERTOS</small><b>${liveLab.readiness?.teams||0}<em>/ ${liveLab.readiness?.thresholds?.teams||8}</em></b><span>evita treinar em poucos confrontos</span></div><div><small>SNAPSHOTS BRUTOS</small><b>${liveLab.readiness?.raw_snapshots||0}</b><span>${liveLab.readiness?.unlabeled_snapshots||0} compactos aguardando resultado</span></div><div><small>TRAINING</small><b>${liveLab.readiness?.ready?"Liberado":"Bloqueado"}</b><span>gate científico automático</span></div></div>
      <div class="checkpoint-grid-v20">${[5,10,15,20,25,30].map(m=>{const n=liveLab.readiness?.checkpoints?.[m]||0,t=liveLab.readiness?.thresholds?.[`m${m}`]||0,p=t?Math.min(100,n/t*100):0;return `<div><span>${m} min</span><b>${n}/${t}</b><div><i style="width:${p}%"></i></div></div>`}).join("")}</div>
      <div class="prospective-rule-v19"><b>Regra:</b> ${esc(liveLab.training_rule||"")}</div>
    </section>

    <section class="panel"><div class="section-head"><div><h2>O que conseguimos validar agora?</h2><p>Não fabricar evidência é parte do produto.</p></div></div><div class="layer-evidence-v19">${(val.layers||[]).map(l=>`<div class="${v19StatusClass(l.decision)}"><span>${l.decision}</span><b>${l.layer}</b><small>${l.current_evidence}</small><p>${l.note}</p></div>`).join("")}</div></section>

    <section class="panel"><div class="section-head"><div><h2>Camadas do produto</h2><p>Registro de produção, contexto, experimental e candidatas congeladas.</p></div></div><div class="model-layer-grid">${models.map(m=>`<div class="${String(m.status).toLowerCase()}"><span>${m.status}</span><b>${m.layer}</b><strong>${m.version}</strong><p>${m.note}</p></div>`).join("")}</div></section>
    <section class="panel"><div class="section-head"><div><h2>Fontes</h2><p>Partida e modelagem são responsabilidades diferentes.</p></div></div><div class="source-health">${sources.map(x=>`<div><i class="${x.status}"></i><b>${x.source}</b><span>${x.status}</span><small>${x.last_success?dateText(x.last_success):"sem consulta registrada"}</small></div>`).join("")||`<div class="empty-inline">Saúde das fontes será preenchida quando o coletor rodar.</div>`}</div></section>
    <section class="panel trust-manifesto"><h2>Regra central</h2><p><b>V8 Production</b> permanece separado. <b>V19 candidates</b> têm definição congelada por hash. <b>Pool exhaustion</b> só pode chegar a review após o verdadeiro gate prospectivo. <b>Flex preditivo</b> segue rejeitado retrospectivamente. <b>Live V1</b> tem protocolo pré-registrado e o test set não pode ser reaberto para retuning.</p></section>`);
}

