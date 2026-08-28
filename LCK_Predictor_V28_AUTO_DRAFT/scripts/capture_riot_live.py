from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import riot_feed

DEFAULT_LEAGUES = [
    "98767991310872058",  # LCK
]


def save_record(handle, record):
    record["captured_at"] = datetime.now(timezone.utc).isoformat()
    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


def capture_once(league_ids, event_ids, cursor=None):
    record = {"live": None, "schedules": {}, "events": {}, "windows": {}, "new_frames": {}, "errors": []}
    try:
        record["live"] = riot_feed.get_live()
    except Exception as error:
        record["errors"].append({"source": "getLive", "error": repr(error)})

    discovered_event_ids = set(str(x) for x in event_ids)
    for league_id in league_ids:
        try:
            schedule = riot_feed.get_schedule("en-US", league_id=league_id)
            record["schedules"][league_id] = schedule
            now = datetime.now(timezone.utc)
            for event in riot_feed.events_from(schedule):
                start = riot_feed._parse_iso(event.get("startTime"))
                if start is None or abs((now - start).total_seconds()) > 8 * 3600:
                    continue
                match_id = (event.get("match") or {}).get("id") or event.get("id")
                if match_id:
                    discovered_event_ids.add(str(match_id))
        except Exception as error:
            record["errors"].append({"source": f"getSchedule:{league_id}", "error": repr(error)})

    for event_id in sorted(discovered_event_ids):
        try:
            details_payload = riot_feed.get_event_details(event_id)
            record["events"][event_id] = details_payload
            event = riot_feed.event_from_details(details_payload) or {}
            for game in ((event.get("match") or {}).get("games") or []):
                game_id = game.get("id")
                if game_id:
                    try:
                        if cursor is not None:
                            w, d, frames = riot_feed.fetch_incremental(str(game_id), cursor)
                            record["windows"][str(game_id)] = w
                            record["new_frames"][str(game_id)] = len(frames)
                        else:
                            record["windows"][str(game_id)] = riot_feed.get_window(str(game_id))
                    except Exception as error:
                        record["errors"].append({"source": f"window:{game_id}", "error": repr(error)})
        except Exception as error:
            record["errors"].append({"source": f"getEventDetails:{event_id}", "error": repr(error)})
    return record


def main():
    parser = argparse.ArgumentParser(description="Captura respostas brutas da Riot para replay controlado.")
    parser.add_argument("--league-id", action="append", dest="league_ids", default=None)
    parser.add_argument("--event-id", action="append", dest="event_ids", default=[])
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--duration", type=float, default=6)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--incremental", action="store_true",
                        help="Usa cursor startingTime para capturar apenas frames novos (menos duplicatas).")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    league_ids = args.league_ids or DEFAULT_LEAGUES
    output_dir = ROOT / "data" / "riot_capture"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(args.output) if args.output else output_dir / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    deadline = time.time() if args.once else time.time() + args.duration * 3600
    cursor = riot_feed.RealtimeCursor() if args.incremental else None
    polls = 0
    print(f"Captura controlada: leagues={','.join(league_ids)} incremental={args.incremental}")
    print(f"Arquivo: {output}")
    with output.open("a", encoding="utf-8") as handle:
        while True:
            polls += 1
            record = capture_once(league_ids, args.event_ids, cursor=cursor)
            save_record(handle, record)
            print(f"poll={polls} events={len(record['events'])} windows={len(record['windows'])} "
                  f"new_frames={sum(record['new_frames'].values())} errors={len(record['errors'])}")
            if args.once or time.time() >= deadline:
                break
            time.sleep(max(5, args.interval))
    print(f"Captura encerrada: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
