from pathlib import Path
import urllib.request,re
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"}
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")

html=get("https://gol.gg/game/stats/81865/page-game/")
open("_gol_game_81865.html","w",encoding="utf-8").write(html)
print("size",len(html))

# winner / victory markers
for m in list(re.finditer(r'(text_victory|text_defeat|winner|Winner|Victory)',html))[:12]:
    s=m.start(); print("@" ,s, repr(html[s-60:s+60]))

print("=== patch ===")
for m in re.finditer(r'[Pp]atch',html):
    s=m.start(); print(repr(html[s-40:s+80]));break

print("=== side / blue / red ===")
for m in list(re.finditer(r'>(Blue|Red) side<|blue_side|red_side',html))[:5]:
    s=m.start();print(repr(html[s-60:s+60]))
