"""Convertido de script solto para teste coletavel pelo pytest.
O server.py e carregado uma vez pela fixture `server` em conftest.py."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_draft_v28(server_tmpdb, monkeypatch):
    # server_tmpdb aponta m.DB para uma cópia descartável e restaura no fim: o
    # módulo agora é compartilhado pela sessão, então vazar o DB aqui quebrava
    # os testes seguintes.
    m = server_tmpdb
    m.v28_ensure_schema()
    fake={"event_id":"E","game_id":"G","game_number":1,"game_state":"inProgress","event_state":"inProgress","patch":"16.16.1","locked_count":10,"complete":True,"source":"fixture",
    "blue":{"team":"T1","picks":[{"champion":"Gnar","role":"TOP"},{"champion":"Vi","role":"JUNGLE"},{"champion":"Azir","role":"MIDDLE"},{"champion":"Jinx","role":"BOTTOM"},{"champion":"Nautilus","role":"SUPPORT"}]},
    "red":{"team":"KT Rolster","picks":[{"champion":"Renekton","role":"TOP"},{"champion":"Sejuani","role":"JUNGLE"},{"champion":"Taliyah","role":"MIDDLE"},{"champion":"Aphelios","role":"BOTTOM"},{"champion":"Rakan","role":"SUPPORT"}]}}
    monkeypatch.setattr(m,"riot_fetch_draft_probe",lambda eid:fake)
    out=m.draft_status_v28("E",True)
    assert out["ok"] and out["complete"] and out["locked_count"]==10
    assert out["blue"]["picks"]["mid"]=="Azir"
    assert out["red"]["picks"]["sup"]=="Rakan"
    assert out["auto_evaluation"] is not None
    row=m.db_one("SELECT draft_json FROM riot_games_v10 WHERE game_id='G'")
    assert row and "Gnar" in row["draft_json"] and "Rakan" in row["draft_json"]
