// Estado global (S), atalhos de DOM ($/1031) e verificação de versão do app
const S={
  theme:localStorage.getItem("lck-theme")||"dark",
  home:null,matches:null,players:null,champions:null,
  liveTimer:null,installPrompt:null
};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const EXPECTED_APP_VERSION="V28_AUTO_DRAFT";
async function verifyVersionV28(){
  try{
    const h=await api('/api/health');
    const proof=document.getElementById('versionProof');
    if(h.app_version!==EXPECTED_APP_VERSION){
      document.body.innerHTML=`<div style="font:700 24px system-ui;padding:40px;max-width:900px;margin:auto"><h1 style="font-size:42px;color:#e05a70">Versão antiga detectada</h1><p>Feche as janelas antigas do LCK Predictor e abra novamente pelo BAT da pasta V28.</p><p>Esperado: <b>${EXPECTED_APP_VERSION}</b><br>Servidor: <b>${h.app_version||'sem versão'}</b></p></div>`;
      return false;
    }
    if(proof)proof.textContent=`V28 • PORTA ${h.port} • AUTO DRAFT`;
    return true;
  }catch(e){return true}
}

document.documentElement.dataset.theme=S.theme;
