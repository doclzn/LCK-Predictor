"""Sonda um jogo LCK CONCLUÍDO para descobrir se o feed window expõe draft/picks/bans.

Pergunta central: conseguimos extrair a sequência de picks/bans (ordem de draft)
dos feeds públicos da Riot, e com qual granularidade de tempo?

Testa também getGames?gameIds= (pode carregar draft por jogo).

Uso: runtime\\python.exe scripts\\probe_completed_game.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402

OUT_DIR = ROOT / "data" / "riot_capture"
LCK = riot_feed.COVERED_LEAGUE_IDS[0]


def find_completed_event():
    """Acha o evento concluído mais recente com times reais e resolve gameId via details."""
    sched = riot_feed.get_schedule("en-US", league_id=LCK)
    data = (sched or {}).get("data", {}).get("schedule", {})
    events = data.get("events") or []
    completed = [e for e in events if e.get("state") == "completed"]
    completed.sort(key=lambda e: e.get("startTime") or "", reverse=True)
    for ev in completed:
        teams = (ev.get("match") or {}).get("teams") or []
        if len(teams) < 2:
            continue
        if any("tbd" in str(t.get("name", "")).lower() for t in teams):
            continue
        eid = ev.get("id") or (ev.get("match") or {}).get("id")
        if not eid:
            continue
        try:
            details = riot_feed.get_event_details(eid)
        except Exception:
            continue
        e2 = riot_feed.event_from_details(details)
        games = ((e2 or {}).get("match") or {}).get("games") or []
        if games and games[0].get("id"):
            merged = dict(ev)
            merged["match"] = (e2 or {}).get("match") or ev.get("match")
            return merged, str(games[0]["id"])
    return None, None


def raw_get(url, key=None, timeout=15):
    h = {"User-Agent": "Mozilla/5.0 Probe/1", "Accept": "application/json"}
    if key:
        h["x-api-key"] = key
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body.decode("utf-8", "replace")) if body else None)
    except Exception as e:
        code = getattr(e, "code", "EXC")
        try:
            return code, e.read()[:200].decode("utf-8", "replace")
        except Exception:
            return code, str(e)


def main():
    print("UTC:", datetime.now(timezone.utc).isoformat())
    ev, game_id = find_completed_event()
    if not game_id:
        print("Nenhum evento concluído encontrado.")
        return 1
    match = ev.get("match") or {}
    names = [t.get("name") for t in match.get("teams") or []]
    print(f"Evento: {ev.get('id')} | {names} | gameId: {game_id} | início: {ev.get('startTime')}")

    capture = {"meta": {"utc": datetime.now(timezone.utc).isoformat(),
                        "event_id": ev.get("id"), "game_id": game_id, "teams": names}}

    # 1) window completo
    st, window = raw_get(riot_feed.LIVE + f"/window/{game_id}")
    capture["window_status"] = st
    if isinstance(window, dict):
        frames = window.get("frames") or []
        gm = window.get("gameMetadata") or {}
        capture["window_keys"] = list(window.keys())
        capture["frame_count"] = len(frames)
        capture["game_states"] = sorted({str(f.get("gameState")) for f in frames})
        capture["frame_field_sample"] = sorted(frames[0].keys()) if frames else []
        btm = (gm.get("blueTeamMetadata") or {}).get("participantMetadata") or []
        capture["blue_meta_count"] = len(btm)
        capture["blue_meta_sample"] = btm[:1]
        capture["gameMetadata_keys"] = list(gm.keys())
        print(f"\nWINDOW: {len(frames)} frames | states={capture['game_states']}")
        print("  campos de um frame:", capture["frame_field_sample"])
        print("  gameMetadata keys:", capture["gameMetadata_keys"])
        # primeiro e último frame (timestamps) para medir duração coberta
        if frames:
            print("  primeiro frame ts:", frames[0].get("rfc460Timestamp"),
                  "gameState:", frames[0].get("gameState"))
            print("  último   frame ts:", frames[-1].get("rfc460Timestamp"),
                  "gameState:", frames[-1].get("gameState"))
        capture["window_full"] = window
    else:
        print("window sem payload:", st, window)

    # 2) details completo
    st, details = raw_get(riot_feed.LIVE + f"/details/{game_id}")
    capture["details_status"] = st
    if isinstance(details, dict):
        capture["details_keys"] = list(details.keys())
        dframes = details.get("frames") or []
        capture["details_frame_count"] = len(dframes)
        capture["details_frame_fields"] = sorted(dframes[0].keys()) if dframes else []
        print(f"\nDETAILS: {len(dframes)} frames | campos: {capture['details_frame_fields'][:12]}")

    # 3) getGames (gateway) — pode carregar picks/bans por jogo
    url = riot_feed.PERSISTED + "/getGames?" + urllib.parse.urlencode(
        {"hl": "en-US", "gameIds": str(game_id)})
    st, games = raw_get(url, key=riot_feed.PUBLIC_CLIENT_KEY)
    capture["getGames_status"] = st
    capture["getGames"] = games if isinstance(games, dict) else str(games)[:300]
    print(f"\ngetGames status: {st}")
    if isinstance(games, dict):
        print(json.dumps(games, ensure_ascii=False)[:800])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"completed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(capture, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCaptura salva em: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
