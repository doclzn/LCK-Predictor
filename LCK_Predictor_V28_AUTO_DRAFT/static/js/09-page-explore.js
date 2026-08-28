// Página Explore: times, jogadores, campeões

let EXPLORE_TAB="teams";
async function renderExplore(tab,id){
  setNav("explore");EXPLORE_TAB=tab||"teams";loading();
  if(tab==="player"&&id)return renderPlayer(decodeURIComponent(id));
  if(tab==="champion"&&id)return renderChampion(decodeURIComponent(id));
  if(tab==="team"&&id)return renderTeam(decodeURIComponent(id));
  const head=`<section class="page-head"><div><span class="eyebrow">EXPLORE</span><h1>Times, jogadores e campeões.</h1><p>Do panorama geral ao detalhe individual sem sair da mesma área.</p></div></section>
    <div class="tabs explore-tabs"><button class="${EXPLORE_TAB==="teams"?"active":""}" onclick="go('explore/teams')">Times</button><button class="${EXPLORE_TAB==="players"?"active":""}" onclick="go('explore/players')">Jogadores</button><button class="${EXPLORE_TAB==="champions"?"active":""}" onclick="go('explore/champions')">Campeões</button><button class="${EXPLORE_TAB==="history"?"active":""}" onclick="go('explore/history')">Histórico</button><button onclick="go('explore/patches')">Patches</button></div>`;
  if(EXPLORE_TAB==="players"){
    const rows=await api("/api/v12/players?limit=200");S.players=rows;
    page(head+`<section class="panel explorer"><div class="explore-toolbar"><input placeholder="Buscar jogador ou time…" oninput="filterPlayers(this.value)"><span>${rows.length} jogadores no elenco atual</span></div>
      <div id="playerGrid" class="entity-grid">${rows.map(playerCard).join("")}</div></section>`);return;
  }
  if(EXPLORE_TAB==="champions"){
    const rows=await api("/api/v12/champions?limit=250");S.champions=rows;
    page(head+`<section class="panel explorer"><div class="explore-toolbar"><input placeholder="Buscar campeão…" oninput="filterChampions(this.value)"><select onchange="filterChampionRole(this.value)"><option value="">Todas as rotas</option><option value="top">Top</option><option value="jng">Jungle</option><option value="mid">Mid</option><option value="bot">ADC</option><option value="sup">Support</option></select><span>${rows.length} campeão×role</span></div>
      <div id="champGrid" class="champ-grid">${rows.map(champCard).join("")}</div></section>`);return;
  }

  if(EXPLORE_TAB==="history"){
    const h=await api("/api/v13/history/coverage");
    const b=h.bundled_history||{},a=h.imported_alltime||{},manifest=h.manifest||[];
    page(head+`<section class="history-coverage-v13">
      <div class="panel"><small>INCLUÍDO NA BUILD</small><strong>${b.series||0}</strong><span>séries · ${b.min_year||"—"}–${b.max_year||"—"}</span></div>
      <div class="panel"><small>ALL-TIME IMPORTADO</small><strong>${a.series||0}</strong><span>${a.min_year||"nenhum ano"}${a.max_year&&a.max_year!==a.min_year?`–${a.max_year}`:""}</span></div>
      <div class="panel"><small>PIPELINE</small><strong>Pronto</strong><span>CSV local → SQLite normalizado</span></div>
    </section>
    <section class="panel history-import-v13"><div class="section-head"><div><span class="eyebrow">HISTÓRICO ALL-TIME</span><h2>Expansão por temporadas</h2><p>A V13 consegue importar arquivos históricos locais sem colocá-los automaticamente no modelo atual.</p></div></div>
      <div class="history-import-steps-v13"><div><b>1</b><span>Obtenha os CSVs históricos de uma fonte que você possa usar.</span></div><div><b>2</b><span>Coloque-os em uma pasta no Windows.</span></div><div><b>3</b><span>Execute <code>IMPORTAR_HISTORICO_LCK.bat</code>.</span></div><div><b>4</b><span>O app filtra LCK, jogos, jogadores, champions e reconstrói séries.</span></div></div>
      <div class="history-safety-v13"><b>Separação de eras:</b> histórico antigo entra primeiro em Explore/H2H. Ele não altera Elo/modelo 2026 sem uma validação temporal específica.</div>
    </section>
    <section class="panel"><div class="section-head"><div><h2>Manifest de importação</h2><p>Auditoria de quais arquivos realmente entraram no banco.</p></div></div>
      <div class="import-manifest-v13">${manifest.length?manifest.map(m=>`<div><b>${m.source_year||"—"}</b><span>${m.source_file}</span><strong>${m.lck_games} games · ${m.lck_series} séries</strong><em>${m.status}</em></div>`).join(""):`<div class="empty-inline">Nenhum arquivo antigo importado nesta build. O arquivo atual continua 2025–2026.</div>`}</div></section>`);
    return;
  }

  if(EXPLORE_TAB==="patches"){
    page(head+`<section class="panel link-panel"><div><h2>Patch Intelligence</h2><p>Meta por campeão, role, jogador e equipe. Mantemos patch como contexto até provar ganho preditivo fora da amostra.</p></div><button onclick="go('legacy-patches')">Abrir análise de patches →</button></section>`);return;
  }
  const home=await api("/api/v12/home");
  page(head+`<div class="team-grid">${(home.rankings||[]).map(r=>`<button class="team-card" onclick="go('explore/team/${encodeURIComponent(r.team)}')"><span>${r.rank}</span>${teamMark(r.team)}<div><b>${r.team}</b><small>${r.full_name||""}</small></div><strong>${Math.round(r.elo)}</strong><em>${pct(r.series_winrate_last5)} L5</em></button>`).join("")}</div>`);
}
function playerCard(r){return `<button class="entity-card" data-search="${(r.player+" "+r.team).toLowerCase()}" onclick="go('explore/player/${encodeURIComponent(r.player)}')"><div><small>${r.team} · ${r.role_label}</small><h3>${r.player}</h3></div><strong>${r.winrate==null?"—":pct(r.winrate)}</strong><span>${r.games} games</span>${r.signature?`<em>${r.signature.champion} · ${r.signature.games}g</em>`:""}</button>`}
function champCard(r){return `<button class="champ-card" data-search="${r.champion.toLowerCase()}" data-role="${r.role}" onclick="go('explore/champion/${encodeURIComponent(r.champion)}?role=${r.role}')"><div><small>${r.role_label}</small><h3>${r.champion}</h3></div><strong>${pct(r.smoothed_winrate)}</strong><span>${r.games} games</span><em>GD15 ${signed(r.gd15||0)}</em></button>`}
window.filterPlayers=q=>{$$("#playerGrid .entity-card").forEach(x=>x.hidden=!x.dataset.search.includes(q.toLowerCase()))}
window.filterChampions=q=>{$$("#champGrid .champ-card").forEach(x=>x.hidden=!x.dataset.search.includes(q.toLowerCase()))}
window.filterChampionRole=role=>{$$("#champGrid .champ-card").forEach(x=>x.hidden=!!role&&x.dataset.role!==role)}

async function renderPlayer(name){
  const x=await api(`/api/v12/player?name=${encodeURIComponent(name)}`),r=x.roster||{},o=x.overall||{};
  const wr=o.games?o.wins/o.games:null;
  page(`<section class="page-head"><div><button class="back-link" onclick="go('explore/players')">← Jogadores</button><span class="eyebrow">${r.team||"LCK"} · ${r.role||""}</span><h1>${esc(name)}</h1><p>Carreira, temporada, champion pool e forma recente.</p></div></section>
    <section class="profile-hero panel"><div class="profile-avatar">${name.slice(0,2).toUpperCase()}</div><div><small>OVERALL</small><strong>${wr==null?"—":pct(wr)}</strong><span>${o.games||0} games · ${o.wins||0} wins</span></div><div><small>TIME</small><strong>${r.team||"—"}</strong><span>${r.role||"—"}</span></div><div><small>PRIOR EB</small><strong>${o.player_prior!=null?pct(o.player_prior):"—"}</strong><span>base para amostras pequenas</span></div></section>
    <section class="panel"><div class="section-head"><div><h2>Champion pool · carreira</h2><p>Ordenado por volume de jogos.</p></div></div>${championTable(x.career_champions||[])}</section>
    <section class="panel"><div class="section-head"><div><h2>Temporada 2026</h2><p>Mesmo jogador, recorte atual.</p></div></div>${championTable(x.season_champions||[])}</section>
    <section class="panel"><div class="section-head"><div><h2>Jogos recentes</h2><p>Últimos registros detalhados.</p></div></div><div class="recent-games">${(x.recent_games||[]).map(g=>`<div><span>${g.date}</span><b>${g.champion}</b><strong>${g.kills}/${g.deaths}/${g.assists}</strong><em>${g.result?"WIN":"LOSS"}</em><small>GD15 ${signed(g.golddiffat15||0)} · ${Math.round(g.dpm||0)} DPM</small></div>`).join("")}</div></section>`);
}
function championTable(rows){return `<div class="data-table"><div class="data-head"><span>Campeão</span><span>Games</span><span>WR</span><span>KDA</span><span>GD15</span><span>DPM</span></div>${rows.slice(0,20).map(r=>`<button onclick="go('explore/champion/${encodeURIComponent(r.champion)}${r.role?`?role=${r.role}`:""}')"><b>${r.champion}</b><span>${r.games}</span><strong>${pct(r.smoothed_winrate??r.winrate)}</strong><span>${r.kda==null?"—":Number(r.kda).toFixed(2)}</span><span>${r.gd15==null?"—":signed(Math.round(r.gd15))}</span><span>${r.dpm==null?"—":Math.round(r.dpm)}</span></button>`).join("")}</div>`}

async function renderChampion(name){
  const params=new URLSearchParams(location.hash.split("?")[1]||""),role=params.get("role")||"";
  const x=await api(`/api/v12/champion?name=${encodeURIComponent(name)}${role?`&role=${role}`:""}`);
  const m=(x.meta||[]).find(x=>x.scope==="2026")||(x.meta||[])[0]||{};
  page(`<section class="page-head"><div><button class="back-link" onclick="go('explore/champions')">← Campeões</button><span class="eyebrow">${role?role.toUpperCase():"TODAS AS ROTAS"}</span><h1>${esc(name)}</h1><p>Meta, especialistas, patches e matchups.</p></div></section>
    <section class="profile-hero panel"><div class="profile-avatar champion">${name.slice(0,2).toUpperCase()}</div><div><small>WR AJUSTADO</small><strong>${m.smoothed_winrate!=null?pct(m.smoothed_winrate):"—"}</strong><span>${m.games||0} games</span></div><div><small>GD@15</small><strong>${signed(Math.round(m.gd15||0))}</strong><span>recorte ${m.scope||"—"}</span></div><div><small>ROLE</small><strong>${role||m.role||"—"}</strong><span>champion meta</span></div></section>
    <section class="panel"><div class="section-head"><div><h2>Quem mais joga</h2><p>Especialistas e volume de jogos.</p></div></div><div class="specialists">${(x.players||[]).filter(p=>p.scope==="2026").slice(0,15).map(p=>`<button onclick="go('explore/player/${encodeURIComponent(p.player)}')"><b>${p.player}</b><span>${p.team} · ${p.role}</span><strong>${p.games}g · ${pct(p.smoothed_winrate)}</strong><small>GD15 ${signed(Math.round(p.gd15||0))}</small></button>`).join("")}</div></section>
    <section class="panel"><div class="section-head"><div><h2>Por patch</h2><p>Contexto descritivo; não recebe peso central automaticamente.</p></div></div><div class="patch-strip">${(x.patches||[]).slice(0,18).map(p=>`<div><small>${p.patch}</small><b>${p.games}g</b><strong>${pct(p.winrate)}</strong><span>GD15 ${signed(Math.round(p.gd15||0))}</span></div>`).join("")}</div></section>`);
}
async function renderTeam(name){
  const x=await api(`/api/v12/team?name=${encodeURIComponent(name)}`),r=x.rating||{};
  page(`<section class="page-head"><div><button class="back-link" onclick="go('explore/teams')">← Times</button><span class="eyebrow">LCK TEAM</span><h1>${esc(name)}</h1><p>Força atual, elenco e histórico recente.</p></div></section>
    <section class="profile-hero panel">${teamMark(name)}<div><small>ELO</small><strong>${Math.round(r.elo||0)}</strong><span>#${r.rank||"—"} no ranking</span></div><div><small>ÚLTIMAS 5</small><strong>${pct(r.series_winrate_last5)}</strong><span>series win rate</span></div><div><small>ÚLTIMAS 10</small><strong>${pct(r.series_winrate_last10)}</strong><span>series win rate</span></div></section>
    <section class="panel"><div class="section-head"><div><h2>Elenco</h2><p>Roster atual normalizado.</p></div></div><div class="roster-grid">${(x.roster||[]).map(p=>`<button onclick="go('explore/player/${encodeURIComponent(p.player)}')"><small>${String(p.role).toUpperCase()}</small><b>${p.player}</b></button>`).join("")}</div></section>
    <section class="panel"><div class="section-head"><div><h2>Séries recentes</h2></div></div><div class="match-stack">${(x.recent_series||[]).slice(0,10).map(m=>matchRow(m,true)).join("")}</div></section>`);
}

