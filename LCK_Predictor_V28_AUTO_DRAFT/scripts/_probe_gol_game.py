from pathlib import Path
import urllib.request,re,json
ROOT=Path(__file__).resolve().parents[1]
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"}
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")

# pagina de um game (BFX vs NS, serie 2-1)
for page in ("page-summary",):
    url=f"https://gol.gg/game/stats/81865/{page}/"
    html=get(url)
    print("==",page,"size",len(html))
    # tabs disponiveis
    tabs=sorted(set(re.findall(r'href="(\.\./\.\./game/stats/81865/[a-z-]+/)"',html)))
    print("tabs:",tabs)
    # infos basicas
    for pat in [r'Patch[^<]*</[^>]+>\s*<[^>]+>([^<]+)<', r'([0-9]{2}:[0-9]{2})']:
        m=re.findall(pat,html)
        if m: print(pat,"->",m[:6])
    # titulos de coluna
    ths=re.findall(r'<th[^>]*>([^<]{2,30})</th>',html)
    print("th:",ths[:30])
    print(html[:600].replace("\n"," "))
