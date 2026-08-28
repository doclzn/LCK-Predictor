// Página Home

async function renderHome(){
  setNav("home");loading();
  const d=await api("/api/v12/home");S.home=d;S.teamAssets=d.team_assets||S.teamAssets||{};
  const live=d.live||[], upcoming=d.upcoming||[],recent=d.recent||[];
  const guide=findFeaturedGuideMatch(d);
  const featured=live[0]||guide||upcoming[0];
  let hero="";
  if(featured){
    const p=matchProbability(featured),f=p==null?null:favorite(p,featured.team1,featured.team2);
    hero=`<section class="hero-match ${featured.status==="live"?"is-live":""}" onclick="go('match/${encodeURIComponent(matchId(featured))}')">
      <div class="hero-copy">${featured.status==="live"?`<span class="live-signal">● AO VIVO</span>`:`<span class="eyebrow">PRÓXIMO DESTAQUE</span>`}
        <h1>${esc(featured.team1)} <i>vs</i> ${esc(featured.team2)}</h1>
        <p>${dateText(featured.date)} · ${featured.block_name||"LCK"}</p>
        ${f?`<div class="hero-prediction"><small>${featured.probability_team1_now!=null?`LEITURA AGORA · ${featured.wins1??0}–${featured.wins2??0}`:"LEITURA PRÉ-JOGO"}</small><strong>${f.team} ${probBadge(f.p)}</strong><span>${advantage(p)}${pregameShift(featured,f.team)}</span></div>`:""}
      </div>
      <div class="hero-versus"><div>${teamMark(featured.team1)}<b>${featured.team1}</b></div><span>VS</span><div>${teamMark(featured.team2)}<b>${featured.team2}</b></div></div>
      <button>Ver partida →</button>
    </section>`;
  }
  const model=d.model?.winner||{},history=d.data?.history||{};
  page(`${hero}
    <div class="home-grid">
      <section class="panel"><div class="panel-head"><div><h2>Próximas partidas</h2><p>${upcoming.length} partidas futuras no radar</p></div><button onclick="go('matches/upcoming')">Ver agenda</button></div>
        <div class="match-stack">${groupedUpcomingV23(upcoming,6)}</div></section>
      <section class="panel ranking-panel"><div class="panel-head"><div><h2>Ranking de força</h2><p>Elo atual</p></div><button onclick="go('explore/teams')">Explorar</button></div>
        <div class="mini-ranking">${(d.rankings||[]).slice(0,7).map(r=>`<button onclick="go('explore/team/${encodeURIComponent(r.team)}')"><span>${r.rank}</span>${teamMark(r.team,true)}<b>${r.team}</b><strong>${Math.round(r.elo)}</strong></button>`).join("")}</div></section>
    </div>
    <section class="trust-strip">
      <div><small>MODELO PRÉ-JOGO</small><strong>${model.accuracy!=null?pct(model.accuracy):"—"}</strong><span>accuracy no teste externo</span></div>
      <div><small>CALIBRAÇÃO</small><strong>${model.brier!=null?Number(model.brier).toFixed(3):"—"}</strong><span>Brier · menor é melhor</span></div>
      <div><small>ARQUIVO LCK</small><strong>${history.historical_series||0}</strong><span>séries disponíveis</span></div>
      <div><small>FONTE DE PARTIDA</small><strong>Riot</strong><span>agenda · draft · live</span></div>
      <button onclick="go('model')">Como avaliamos →</button>
    </section>
    ${quickStartPanel(d)}
    <section class="panel recent-panel"><div class="panel-head"><div><h2>Resultados recentes</h2><p>Volte e audite o que a plataforma sabia antes.</p></div><button onclick="go('matches/results')">Ver histórico</button></div>
      <div class="match-stack">${recent.map(x=>matchRow(x,true)).join("")}</div></section>`);
}
