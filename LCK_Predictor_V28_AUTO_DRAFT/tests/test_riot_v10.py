"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def test_riot_v10(server, riot):
    m = server
    rf = riot
    f=json.loads((ROOT/"tests"/"riot_v10_fixture.json").read_text())
    ev=rf.event_from_details(f["event"])
    snap=rf.normalize("123",ev,f["window"],f["details"],ev["match"]["games"][0])
    assert snap["game_id"]=="456"
    assert snap["patch"]=="16.16.805.442"
    assert snap["blue"]["team"]=="Hanwha Life Esports"
    assert snap["blue"]["participants"][0]["champion"]=="Camille"
    assert snap["red"]["participants"][3]["champion"]=="Yunara"
    assert snap["blue"]["dragons"]==1
