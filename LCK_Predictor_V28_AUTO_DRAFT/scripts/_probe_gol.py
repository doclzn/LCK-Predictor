from pathlib import Path
import urllib.request,re
ROOT=Path(__file__).resolve().parents[1]
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"}
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")

html=get("https://gol.gg/tournament/tournament-matchlist/LCK%202026%20Rounds%203-4/")
print("size",len(html))
links=re.findall(r'href="(/game/[^"]+)"',html)
print("game links:",len(links),"ex:",links[:6])
# contexto de uma linha com link de game
i=html.find("/game/")
print(html[i-600:i+300].replace("\n"," ")[:900])
