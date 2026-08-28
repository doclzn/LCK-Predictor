from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import riot_feed as rf

for eid in ("115548147900750241","115548147900619029"):
    ep=rf.get_event_details(eid)
    ev=rf.event_from_details(ep)
    if not ev:
        print(eid,"sem evento");continue
    m=ev.get("match") or {}
    print("== event",eid,"state",ev.get("state"),"==")
    print("match keys:",sorted(m.keys()))
    for g in m.get("games") or []:
        print(" game:",json.dumps(g,ensure_ascii=False))
    for t in m.get("teams") or []:
        keep={k:t.get(k) for k in ("code","name","result","record","side","winner") if k in t}
        print(" team:",json.dumps(keep,ensure_ascii=False))
