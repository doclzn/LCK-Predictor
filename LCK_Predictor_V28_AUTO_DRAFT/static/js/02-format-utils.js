// Formatação: texto, datas, números, nomes de time, escape HTML

function esc(x){return String(x??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
function pct(x,d=1){return x==null?"—":`${(Number(x)*100).toFixed(d)}%`}
function probBadge(x){return x==null?"—":`${pct(x)}<span class="wr-tip" tabindex="0" data-tip="WR — chance de vitória estimada pelo nosso modelo próprio, com base em Elo e histórico de confrontos entre as equipes.">WR<b>i</b></span>`}
function num(x){return Number(x||0).toLocaleString("pt-BR")}
function signed(x){x=Number(x||0);return `${x>0?"+":""}${num(x)}`}
function code(x){const m={"Hanwha Life Esports":"HLE","Dplus KIA":"DK","Dplus Kia":"DK","Gen.G":"GEN","KT Rolster":"KT","BNK FEARX":"BFX","BNK FearX":"BFX","Nongshim RedForce":"NS","Kiwoom DRX":"KRX","HANJIN BRION":"BRO","DN SOOPers":"DNS"};return m[x]||x||"—"}
function dateText(x){
  if(!x)return "—";
  try{
    const s=String(x);
    if(/^\d{4}-\d{2}-\d{2}$/.test(s)){
      const [y,m,d]=s.split("-").map(Number);
      const dt=new Date(y,m-1,d,12,0,0);
      return new Intl.DateTimeFormat("pt-BR",{day:"2-digit",month:"short"}).format(dt);
    }
    return new Intl.DateTimeFormat("pt-BR",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(s));
  }catch{return String(x)}
}
function dayText(x){if(!x)return "—";const s=String(x).slice(0,10).split("-");return s.length===3?`${s[2]}/${s[1]}/${s[0]}`:x}
function clock(sec){sec=Math.round(Number(sec||0));return sec?`${Math.floor(sec/60)}:${String(sec%60).padStart(2,"0")}`:"—"}
function favorite(p,a,b){p=Number(p);return p>=.5?{team:a,p}:{team:b,p:1-p}}
function advantage(p){const d=Math.abs(Number(p)-.5);const lvl=d<.035?["Equilibrado","tight"]:d<.08?["Leve vantagem","soft"]:d<.16?["Vantagem moderada","mid"]:["Vantagem clara","strong"];return `<em class="adv-tag adv-${lvl[1]}">${lvl[0]}</em>`}
function initials(t){return code(t).slice(0,3)}
function teamIconPath(t){const c=code(t);return `/static/team_icons/${encodeURIComponent(c)}.svg`}
function teamMark(t,small=false){
  const raw=code(t),c=esc(raw);
  const official=S.teamAssets?.[raw]?.image;
  const src=official||teamIconPath(t);
  return `<span class="team-mark ${small?"small":""} ${official?"official":""}" title="${esc(t||c)}"><img src="${esc(src)}" onerror="if(!this.dataset.fb){this.dataset.fb='1';this.src='${teamIconPath(t)}'}else{this.style.visibility='hidden';this.closest('.team-mark').classList.add('broken')}" alt="${c}" loading="lazy"><em>${c}</em></span>`;
}
function statusLabel(x){x=String(x||"").toLowerCase();if(x.includes("progress")||x==="live")return "Ao vivo";if(x.includes("complete")||x==="completed")return "Final";if(x.includes("upcoming")||x.includes("unstarted"))return "Agendada";return x||"—"}
function phasePill(phase){const p=phase==="live"?"live":phase==="post"?"final":"pre";return `<span class="phase ${p}">${p==="live"?"● AO VIVO":p==="final"?"FINAL":"PRÉ-JOGO"}</span>`}
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2200)}
async function api(url,opts={}){const r=await fetch(url,{cache:"no-store",...opts});if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);return r.json()}
async function post(url,data={}){return api(url,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(data)})}
