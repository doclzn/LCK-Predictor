from pathlib import Path
import json,importlib.util
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rf",root/"riot_feed.py")
rf=importlib.util.module_from_spec(spec);spec.loader.exec_module(rf)
f=json.loads((root/"tests"/"riot_v10_fixture.json").read_text())
ev=rf.event_from_details(f["event"])
snap=rf.normalize("123",ev,f["window"],f["details"],ev["match"]["games"][0])
assert snap["game_id"]=="456"
assert snap["patch"]=="16.16.805.442"
assert snap["blue"]["team"]=="Hanwha Life Esports"
assert snap["blue"]["participants"][0]["champion"]=="Camille"
assert snap["red"]["participants"][3]["champion"]=="Yunara"
assert snap["blue"]["dragons"]==1
print("Riot V10 fixture: OK")
