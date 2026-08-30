"""Regressão V28.1 — feed de tempo real (cursor incremental + GRID gate).

Cobre:
  - RealtimeCursor.advance/get/reset;
  - fetch_incremental: seed por lookback, avanço de cursor, fallback HTTP 400
    (re-semeia com lookback fresco; NUNCA consulta sem startingTime);
  - fetch_event_live_incremental: sempre usa startingTime;
  - live_response_v10: usa caminho incremental e cai para o legado em erro.
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


riot = load("riot_feed", "riot_feed.py")

WINDOW = {
    "gameMetadata": {
        "patchVersion": "16.16.1",
        "blueTeamMetadata": {
            "teamCode": "T1", "teamName": "T1", "esportsTeamId": "T1id",
            "participantMetadata": [
                {"participantId": 1, "summonerName": "T1Zeus", "championId": "Gnar",
                 "championName": "Gnar", "role": "top"}],
        },
        "redTeamMetadata": {
            "teamCode": "GEN", "teamName": "Gen.G", "esportsTeamId": "GENid",
            "participantMetadata": [
                {"participantId": 6, "summonerName": "GENKiin", "championId": "Renekton",
                 "championName": "Renekton", "role": "top"}],
        },
    },
    "frames": [
        {"rfc460Timestamp": "2026-08-25T04:00:00Z", "gameState": "in_game",
         "blueTeam": {"totalGold": 1000, "totalKills": 1, "towers": 0, "dragons": [],
                      "barons": 0, "inhibitors": 0,
                      "participants": [{"participantId": 1, "level": 3, "kills": 1, "deaths": 0,
                                        "assists": 0, "creepScore": 10, "totalGold": 500}]},
         "redTeam": {"totalGold": 900, "totalKills": 0, "towers": 0, "dragons": [],
                     "barons": 0, "inhibitors": 0,
                     "participants": [{"participantId": 6, "level": 3, "kills": 0, "deaths": 1,
                                       "assists": 0, "creepScore": 9, "totalGold": 450}]}},
        {"rfc460Timestamp": "2026-08-25T04:00:10Z", "gameState": "in_game",
         "blueTeam": {"totalGold": 1100, "totalKills": 2, "towers": 0, "dragons": [],
                      "barons": 0, "inhibitors": 0,
                      "participants": [{"participantId": 1, "level": 4, "kills": 2, "deaths": 0,
                                        "assists": 0, "creepScore": 12, "totalGold": 560}]},
         "redTeam": {"totalGold": 950, "totalKills": 0, "towers": 0, "dragons": [],
                     "barons": 0, "inhibitors": 0,
                     "participants": [{"participantId": 6, "level": 3, "kills": 0, "deaths": 2,
                                       "assists": 0, "creepScore": 10, "totalGold": 470}]}},
    ],
}
DETAILS = {"frames": [{"rfc460Timestamp": "2026-08-25T04:00:10Z",
                        "participants": [
                            {"participantId": 1, "currentHealth": 500, "maxHealth": 600,
                             "items": [], "runes": []},
                            {"participantId": 6, "currentHealth": 400, "maxHealth": 600,
                             "items": [], "runes": []}]}]}
EVENT = {"id": "E1", "state": "inProgress", "league": {"name": "LCK"},
         "match": {"id": "E1",
                   "teams": [{"id": "T1id", "name": "T1", "code": "T1"},
                             {"id": "GENid", "name": "Gen.G", "code": "GEN"}],
                   "games": [{"id": "G1", "number": 1, "state": "inProgress"}],
                   "strategy": {}}}



def test_realtime_feed_v28_1():
    # --- RealtimeCursor -------------------------------------------------------
    cur = riot.RealtimeCursor()
    assert cur.get("G1") is None
    assert cur.advance("G1", WINDOW["frames"]) == "2026-08-25T04:00:10Z"
    assert cur.get("G1") == "2026-08-25T04:00:10Z"
    cur.reset("G1")
    assert cur.get("G1") is None
    assert cur.advance("G1", []) is None  # sem frames não move cursor

    # --- fetch_incremental: seed + avanço de cursor ---------------------------
    calls = []


    def gw_ok(game_id, starting_time=None):
        calls.append(("window", starting_time))
        return WINDOW


    def gd_ok(game_id, starting_time=None):
        calls.append(("details", starting_time))
        return DETAILS


    orig_gw, orig_gd = riot.get_window, riot.get_details
    riot.get_window, riot.get_details = gw_ok, gd_ok
    cur = riot.RealtimeCursor()
    w, d, frames = riot.fetch_incremental("G1", cur, lookback_seconds=90)
    assert len(frames) == 2
    # primeiro uso semeia com startingTime derivado do lookback (nunca None)
    assert calls[0][1] is not None and calls[1][1] is not None
    assert cur.get("G1") == "2026-08-25T04:00:10Z"

    calls.clear()
    w, d, frames = riot.fetch_incremental("G1", cur)
    # segunda chamada usa o cursor salvo como startingTime
    assert calls[0][1] == "2026-08-25T04:00:10Z"

    # --- fetch_incremental: fallback HTTP 400 re-semeia (nunca sem startingTime)
    OLD = "2026-08-25T03:00:00Z"
    seen_400 = []


    def gw_400_on_old(game_id, starting_time=None):
        seen_400.append(starting_time)
        if starting_time == OLD:
            raise urllib.error.HTTPError("http://x", 400, "Bad Request", {}, None)
        return WINDOW


    def gd_400_on_old(game_id, starting_time=None):
        if starting_time == OLD:
            raise urllib.error.HTTPError("http://x", 400, "Bad Request", {}, None)
        return DETAILS


    riot.get_window, riot.get_details = gw_400_on_old, gd_400_on_old
    cur2 = riot.RealtimeCursor()
    cur2.advance("G1", [{"rfc460Timestamp": OLD}])  # cursor fora da janela retida
    w, d, frames = riot.fetch_incremental("G1", cur2)
    assert len(frames) == 2
    assert seen_400[0] == OLD            # 1ª tentativa usa o cursor velho -> 400
    assert seen_400[1] is not None and seen_400[1] != OLD  # re-semeou com lookback fresco
    assert all(t is not None for t in seen_400)  # jamais consultou sem startingTime
    assert cur2.get("G1") == "2026-08-25T04:00:10Z"

    # --- fetch_event_live_incremental: sempre com startingTime -----------------
    seen = {}


    def fake_details(event_id, hl="en-US"):
        return {"data": {"event": EVENT}}


    def gw_cap(game_id, starting_time=None):
        seen["window_start"] = starting_time
        return WINDOW


    def gd_cap(game_id, starting_time=None):
        seen["details_start"] = starting_time
        return DETAILS


    riot.get_event_details = fake_details
    riot.get_window, riot.get_details = gw_cap, gd_cap
    cur3 = riot.RealtimeCursor()
    snap = riot.fetch_event_live_incremental("E1", cur3)
    assert seen["window_start"] is not None and seen["details_start"] is not None
    assert snap["event_id"] == "E1" and snap["game_id"] == "G1"
    assert snap["blue"]["team"] == "T1" and snap["red"]["team"] == "Gen.G"
    assert snap["timestamp"] == "2026-08-25T04:00:10Z"
    riot.get_window, riot.get_details = orig_gw, orig_gd

    # --- server.live_response_v10: incremental + fallback legado --------------
    server = load("server", "server.py")
    tmp_db = Path(tempfile.mkdtemp()) / "rt.sqlite"
    shutil.copy2(ROOT / "data" / "lck_data_v1.sqlite", tmp_db)
    server.DB = tmp_db

    SNAP = {"event_id": "E1", "game_id": "G1", "game_number": 1,
            "game_state": "inProgress", "event_state": "inProgress",
            "patch": "16.16.1", "timestamp": "2026-08-25T04:00:10Z",
            "blue": {"team": "T1"}, "red": {"team": "Gen.G"}, "streams": [],
            "series": {"teams": [], "games": [], "strategy": {}}}

    used = {}
    server.riot_fetch_event_live_incremental = lambda eid, cursor: (used.update(rt=True), SNAP)[1]
    server.riot_fetch_event_live = lambda eid, delay: (used.update(legacy=True), SNAP)[1]
    server.store_riot_snapshot_v10 = lambda s: None
    server.source_health = lambda *a, **k: None
    server.riot_get_event_details = lambda eid, hl="en-US": {"data": {"event": EVENT}}
    server.store_riot_event = lambda ev: None
    server._draft_analysis_v10 = lambda s: {}
    server.live_state_estimate_v10 = lambda s, d: None
    server.series_state_v10 = lambda s, d, le: {}
    server.live_timeline_v10 = lambda gid, limit: []
    server.log_series_pregame_v11 = lambda s: None
    server.log_live_predictions_v11 = lambda *a: None
    server.v19_capture_prospective = lambda s, d: None
    server.v19_score_prospective = lambda: None
    server.v20_capture_live_training = lambda s, d: None
    server.v20_score_live_training = lambda: None
    server.db_rows = lambda *a, **k: []

    out = server.live_response_v10("E1", True)
    assert out["ok"] and used.get("rt") and not used.get("legacy")
    assert isinstance(out["frame_lag_seconds"], (int, float))

    # fallback: caminho incremental falha -> legado assume e cursor é resetado
    used.clear()


    def rt_fail(eid, cursor):
        raise RuntimeError("feed sem frames")


    server.riot_fetch_event_live_incremental = rt_fail
    out = server.live_response_v10("E1", True)
    assert out["ok"] and used.get("legacy")

