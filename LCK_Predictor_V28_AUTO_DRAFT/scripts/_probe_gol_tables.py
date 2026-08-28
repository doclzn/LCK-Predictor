import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import RichTableParser
import re

for name in ("_gol_game_81865.html","_gol_series_81865.html"):
    html=open(ROOT/name if (ROOT/name).exists() else name,encoding="utf-8").read()
    p=RichTableParser();p.feed(html)
    print(f"==== {name}: {len(p.rows)} tables")
    for i,r in enumerate(p.rows):
        if 2<=len(r)<=14 and any(x for x in r):
            print(i,len(r),"|"," || ".join(c[:34] for c in r))
    print()
