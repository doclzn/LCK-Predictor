"""Polling do draft AO VIVO a cada 30s até completar (ou estourar a janela).

Registra a evolução de locked_count (0/10..10/10) e salva cada poll em JSONL
para análise de latência: quanto tempo após o lock a Riot publica o metadata.

Uso: runtime\\python.exe scripts\\poll_live_draft.py [event_id] [intervalo_s] [duracao_min]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402

EVENT_ID = sys.argv[1] if len(sys.argv) > 1 else "116889604984222945"
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 30
DURATION_MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 6


def main():
    out_dir = ROOT / "data" / "live_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / f"draft_poll_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    print(f"event={EVENT_ID} intervalo={INTERVAL}s janela={DURATION_MIN}min")
    print(f"log: {log}")
    deadline = time.time() + DURATION_MIN * 60
    poll = 0
    first_lock_ts = None
    complete_ts = None
    with log.open("a", encoding="utf-8") as fh:
        while time.time() < deadline:
            poll += 1
            ts = datetime.now(timezone.utc).isoformat()
            rec = {"poll": poll, "ts": ts, "locked_count": None, "error": None}
            try:
                probe = riot_feed.fetch_draft_probe(EVENT_ID, delays=(0, 10))
                locked = int(probe.get("locked_count") or 0)
                rec["locked_count"] = locked
                rec["game_state"] = probe.get("game_state")
                rec["game_id"] = probe.get("game_id")
                rec["game_number"] = probe.get("game_number")
                if locked > 0 and first_lock_ts is None:
                    first_lock_ts = ts
                if probe.get("complete") and complete_ts is None:
                    complete_ts = ts
                line = f"[{ts[11:19]}] poll={poll} locked={locked}/10 state={probe.get('game_state')}"
                if locked > 0:
                    for side in ("blue", "red"):
                        s = probe.get(side) or {}
                        picks = [str(p.get("champion") or "?") for p in s.get("picks") or []]
                        line += f"\n        {side}: {picks}"
                print(line, flush=True)
                rec["blue"] = probe.get("blue")
                rec["red"] = probe.get("red")
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"
                print(f"[{ts[11:19]}] poll={poll} erro: {rec['error']}", flush=True)
            fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush()
            if complete_ts and locked >= 10:
                # segura mais 2 polls p/ confirmar estabilidade e depois encerra
                pass
            time.sleep(INTERVAL)
    print(f"\nprimeiro champion visível: {first_lock_ts or 'nunca'}")
    print(f"draft completo (10/10):    {complete_ts or 'não na janela'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
