import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import RichTableParser
import urllib.request
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"}
def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")
html=get("https://gol.gg/tournament/tournament-matchlist/LCK%202026%20Rounds%203-4/")
open(ROOT/"_gol_matchlist.html","w",encoding="utf-8").write(html)
p=RichTableParser();p.feed(html)
print("tables:",len(p.rows))
hdr=None
n=0
for r in p.rows:
    if not r: continue
    if any("Date" in c or "Winner" in c for c in r):
        hdr=r; print("HEADER:",r); continue
    if len(r)>=6 and (" - " in str(r[2]) or "-" in str(r[2])):
        n+=1
        if n<=8 or n>90:
            print(n,"|"," || ".join(str(c)[:26] for c in r))
print("series rows:",n)
