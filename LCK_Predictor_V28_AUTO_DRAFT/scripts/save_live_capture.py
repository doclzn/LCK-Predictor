"""Salva um capture do draft AO VIVO (probe + draft ordenado) em data/live_tests."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402

EVENT_ID = sys.argv[1] if len(sys.argv) > 1 else "116889604984222945"


def main():
    probe = riot_feed.fetch_draft_probe(EVENT_ID)
    draft = riot_feed.fetch_live_draft(probe["game_id"])
    out = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "event_id": EVENT_ID,
        "game_id": probe["game_id"],
        "game_number": probe["game_number"],
        "patch": probe["patch"],
        "locked_count": probe["locked_count"],
        "complete": probe["complete"],
        "game_state": probe["game_state"],
        "probe": probe,
        "draft": draft,
    }
    p = ROOT / "data" / "live_tests"
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"live_draft_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("salvo:", f)
    print(f"locked={probe['locked_count']}/10 complete={probe['complete']} game={probe['game_number']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
