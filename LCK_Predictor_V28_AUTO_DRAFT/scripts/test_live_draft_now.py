"""Captura o draft AO VIVO de um jogo em andamento (teste com partida real).

Procura eventos live via getLive e, para cada um, tenta:
  - fetch_draft_probe(event_id)  -> champions via window gameMetadata
  - fetch_live_draft(game_id)    -> draft ordenado por role

Imprime o que está visível AGORA (durante o champ-select, se a Riot publicar).

Uso: runtime\\python.exe scripts\\test_live_draft_now.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402


def main():
    print("UTC:", datetime.now(timezone.utc).isoformat())

    print("\n=== getLive ===")
    try:
        live = riot_feed.get_live("en-US")
    except Exception as e:
        print("getLive falhou:", e)
        live = None
    events = riot_feed.events_from(live)
    print(f"eventos live: {len(events)}")
    for ev in events:
        league = (ev.get("league") or {}).get("name")
        teams = [t.get("name") for t in (ev.get("match") or {}).get("teams") or []]
        print(f"  [{league}] {teams} | id={ev.get('id')}")

    # também varre agenda de todas as ligas cobertas p/ achar o jogo (pode não estar no getLive)
    print("\n=== varredura de agenda (janelas de 8h) ===")
    games = riot_feed.discover_live_games(window_hours=8)
    print(f"jogos detectados como live: {len(games)}")
    for g in games:
        print(f"  {g.get('league')} | {g.get('blueTeam')} vs {g.get('redTeam')} "
              f"game{g.get('gameNum')} gameId={g.get('gameId')} eventId={g.get('eventId')}")

    targets = []
    for g in games:
        targets.append((g["eventId"], g["gameId"], f"{g.get('blueTeam')} vs {g.get('redTeam')}"))
    # se getLive trouxe algo que a varredura não pegou, inclui
    for ev in events:
        eid = str(ev.get("id") or (ev.get("match") or {}).get("id"))
        if eid and not any(t[0] == eid for t in targets):
            targets.append((eid, None, str([(t.get("name")) for t in (ev.get("match") or {}).get("teams") or []])))

    if not targets:
        print("\nNenhum alvo live encontrado agora.")
        return 1

    for eid, gid, label in targets:
        print(f"\n=== draft probe: {label} (event {eid}) ===")
        try:
            probe = riot_feed.fetch_draft_probe(eid)
            print(f"locked_count={probe.get('locked_count')} complete={probe.get('complete')} "
                  f"game_state={probe.get('game_state')} delay={probe.get('delay_seconds')}s")
            for side in ("blue", "red"):
                s = probe.get(side) or {}
                picks = [f"{p.get('player')}:{p.get('champion')}" for p in s.get("picks") or []]
                print(f"  {side} ({s.get('team')}): {picks}")
        except Exception as e:
            print(f"  draft_probe falhou: {type(e).__name__}: {e}")

        if gid:
            print(f"--- fetch_live_draft (game {gid}) ---")
            try:
                d = riot_feed.fetch_live_draft(gid)
                for side in ("blue", "red"):
                    picks = [f"{p.get('player')}:{p.get('champion')}({p.get('role')})"
                             for p in d.get(side) or []]
                    print(f"  {side}: {picks}")
            except riot_feed.DraftNotReady as e:
                print(f"  DRAFT_NOT_READY: {e}")
            except Exception as e:
                print(f"  falhou: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
