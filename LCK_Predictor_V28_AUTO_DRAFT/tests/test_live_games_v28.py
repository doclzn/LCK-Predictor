from pathlib import Path
import importlib.util
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]

riot_spec = importlib.util.spec_from_file_location("riot_feed", ROOT / "riot_feed.py")
riot = importlib.util.module_from_spec(riot_spec)
riot_spec.loader.exec_module(riot)

server_spec = importlib.util.spec_from_file_location("server", ROOT / "server.py")
server = importlib.util.module_from_spec(server_spec)
server_spec.loader.exec_module(server)
tmp_db = Path(tempfile.mkdtemp()) / "live.sqlite"
shutil.copy2(ROOT / "data" / "lck_data_v1.sqlite", tmp_db)
server.DB = tmp_db
server._PLAYER_ROSTER_INDEX = None

assert riot._window_is_live({"gameMetadata": {"patchVersion": "16.16"}}) is False

roster = server.db_one("SELECT team,player FROM draft_rosters WHERE team='T1' LIMIT 1")
assert roster
player = roster["player"]
riot.get_window = lambda game_id, starting_time=None: {
    "gameMetadata": {
        "patchVersion": "16.16.1",
        "blueTeamMetadata": {
            "teamCode": "T1",
            "participantMetadata": [{"summonerName": "T1" + player, "championId": "Gnar", "role": "top"}],
        },
        "redTeamMetadata": {
            "teamCode": "GEN",
            "participantMetadata": [{"summonerName": "GEN" + player, "championId": "Renekton", "role": "top"}],
        },
    }
}
draft = riot.fetch_live_draft("game-1")
assert isinstance(draft["blue"], list)
assert draft["team_codes"]["blue"] == "T1"
server.riot_fetch_live_draft = lambda game_id: draft
normalized = server.live_draft_api("game-1")
assert normalized["ok"]
assert normalized["blue"][0]["player"] == player

server.riot_discover_live_games = lambda league_ids=None: [{
    "league": "LCK Challengers", "blueTeam": "DRX Challengers", "redTeam": "BNK FEARX Youth",
    "blueCode": "KRX", "redCode": "BFX", "gameId": "game-1", "gameNum": 1,
}]
challengers = server.live_games_api()
assert challengers["games"][0]["blueLocal"] is None
assert challengers["games"][0]["redLocal"] is None
print("V28 live-games edge cases: OK")