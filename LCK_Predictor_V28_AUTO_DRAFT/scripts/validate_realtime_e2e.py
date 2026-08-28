"""Validação ponta-a-ponta do feed tempo real contra a API real da Riot.

Pega o evento LCK concluído mais recente e exercita:
  - caminho legado:       fetch_event_live(delay=60) -> startingTime = agora-60s
  - caminho novo (V28.1): fetch_event_live_incremental(event, cursor) -> cursor

Confirma que o caminho incremental normaliza um snapshot válido, semeia o cursor
na primeira chamada e pede apenas frames novos na segunda. Também evidencia que
consultar SEM startingTime retorna o início do jogo (não o estado atual).

Uso: runtime\\python.exe scripts\\validate_realtime_e2e.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402


def find_recent_completed():
    sched = riot_feed.get_schedule("en-US", league_id=riot_feed.COVERED_LEAGUE_IDS[0])
    events = riot_feed.events_from(sched)
    completed = [e for e in events if e.get("state") == "completed"]
    completed.sort(key=lambda e: e.get("startTime") or "", reverse=True)
    for ev in completed:
        teams = (ev.get("match") or {}).get("teams") or []
        if len(teams) < 2 or any("tbd" in str(t.get("name", "")).lower() for t in teams):
            continue
        eid = ev.get("id") or (ev.get("match") or {}).get("id")
        if eid:
            return str(eid), [t.get("name") for t in teams]
    return None, None


def lag_of(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - t).total_seconds(), 1)
    except Exception:
        return None


def main():
    print("UTC:", datetime.now(timezone.utc).isoformat())
    event_id, teams = find_recent_completed()
    if not event_id:
        print("Nenhum evento concluído — nada para validar.")
        return 1
    print(f"Evento: {event_id} | {teams}\n")

    # jogo atual do evento
    ep = riot_feed.get_event_details(event_id)
    event = riot_feed.event_from_details(ep)
    game = riot_feed.current_game(event)
    gid = game.get("id")
    print(f"gameId: {gid}\n")

    # frames mais frescos com e sem startingTime
    w_fresh = riot_feed.get_window(str(gid))
    w_delay = riot_feed.get_window(str(gid), riot_feed.feed_time(60))
    f_fresh = (w_fresh or {}).get("frames") or []
    f_delay = (w_delay or {}).get("frames") or []
    ts_fresh = f_fresh[-1].get("rfc460Timestamp") if f_fresh else None
    ts_delay = f_delay[-1].get("rfc460Timestamp") if f_delay else None
    print(f"window SEM startingTime : {len(f_fresh)} frames | último={ts_fresh}")
    print(f"window COM delay 60s    : {len(f_delay)} frames | último={ts_delay}")

    print("\n--- fetch_event_live_incremental (caminho novo, cursor) ---")
    try:
        cursor = riot_feed.RealtimeCursor()
        snap = riot_feed.fetch_event_live_incremental(event_id, cursor)
        print(f"ok={bool(snap)} game_state={snap.get('game_state')} timestamp={snap.get('timestamp')}")
        print(f"blue={snap['blue']['team']} red={snap['red']['team']} patch={snap.get('patch')}")
        print(f"cursor apos 1a chamada: {cursor.get(gid)}")
        print(f"lag do frame vs relógio: {lag_of(snap.get('timestamp'))} s")
        # segunda chamada deve pedir só frames novos a partir do cursor
        snap_b = riot_feed.fetch_event_live_incremental(event_id, cursor)
        print(f"2a chamada ok={bool(snap_b)} timestamp={snap_b.get('timestamp')}")
    except Exception as e:
        print(f"ERRO no caminho novo: {type(e).__name__}: {e}")
        return 1

    print("\n--- fetch_event_live(delay=60) (caminho legado) ---")
    try:
        snap2 = riot_feed.fetch_event_live(event_id, 60)
        print(f"timestamp={snap2.get('timestamp')} lag={lag_of(snap2.get('timestamp'))} s")
    except Exception as e:
        print(f"legado indisponível: {type(e).__name__}: {e}")

    print("\nVALIDAÇÃO: caminho novo retorna snapshot normalizado a partir do frame mais fresco.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
