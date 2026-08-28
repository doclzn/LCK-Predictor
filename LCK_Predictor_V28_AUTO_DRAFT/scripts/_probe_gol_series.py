from pathlib import Path
import urllib.request,re,json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"}
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")

html=get("https://gol.gg/game/stats/81865/page-summary/")
open("_gol_series_81865.html","w",encoding="utf-8").write(html)
print("size",len(html))

# Encontra todas as tabs de pagina (page-summary, page-... )
tabs=sorted(set(re.findall(r'/game/stats/81865/([a-z0-9-]+)/',html)))
print("pages:",tabs)

# Encontra titulos <h2>/<h3>/<div class contendo 'Game'
for m in re.finditer(r'>\s*(Game\s*\d|game\s*\d)\s*<',html):
    print("gamemarker@",m.start(),repr(m.group(1)))

# Encontra nomes de campeoes (title= com nomes conhecidos) perto de 'champion'
idx=html.lower().find("champion")
print("first 'champion' idx",idx, repr(html[idx-100:idx+200]))

# acha imagens de campeao (ddragon ou /cdn/)
champ_imgs=re.findall(r'(?:alt|title)="([A-Za-z\'\.\- ]{3,25})"',html)
from collections import Counter
print("alt/title tokens mais comuns:",Counter(champ_imgs).most_common(20))
