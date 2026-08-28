"""Pagina o window feed desde um cursor inicial para mapear os gameStates.

Uso principal: durante uma partida AO VIVO, começar antes do champ-select e
verificar se o feed público expõe frames de draft (champ_select) com timestamps.
Achados até agora indicam que NÃO — o draft só aparece via gameMetadata após o
lock (ver REVIEW_V28_1_REALTIME.md).

Uso: runtime\\python.exe scripts\\probe_window_history.py <gameId> [startingTimeISO]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402

OUT_DIR = ROOT / "data" / "riot_capture"
GAME_ID = sys.argv[1] if len(sys.argv) > 1 else "115548147900750230"
START = sys.argv[2] if len(sys.argv) > 2 else "2026-08-23T10:20:24Z"


def main():
    print("UTC:", datetime.now(timezone.utc).isoformat())
    seen = {}
    cursor = START
    all_frames = []
    states = {}
    hops = 0
    while cursor and hops < 60:
        w = riot_feed.get_window(GAME_ID, starting_time=cursor)
        frames = (w or {}).get("frames") or []
        if not frames:
            break
        for f in frames:
            ts = f.get("rfc460Timestamp")
            if ts and ts not in seen:
                seen[ts] = True
                all_frames.append(f)
                gs = str(f.get("gameState"))
                states.setdefault(gs, {"first": ts, "count": 0})
                states[gs]["count"] += 1
        # próximo cursor = último timestamp visto
        cursor = frames[-1].get("rfc460Timestamp") or None
        hops += 1

    all_frames.sort(key=lambda f: f.get("rfc460Timestamp") or "")
    print(f"\nTotal frames únicos: {len(all_frames)} em {hops} saltos")
    print("gameStates encontrados:")
    for gs, info in states.items():
        print(f"  {gs:<14} count={info['count']:<4} primeiro={info['first']}")

    if all_frames:
        print("\nprimeiro frame:", all_frames[0].get("rfc460Timestamp"),
              all_frames[0].get("gameState"))
        print("último  frame:", all_frames[-1].get("rfc460Timestamp"),
              all_frames[-1].get("gameState"))
        # campos presentes em frames champ_select (se houver)
        cs = [f for f in all_frames if str(f.get("gameState")).lower().startswith("champ")]
        if cs:
            print("\ncampos de um frame champ_select:", sorted(cs[0].keys()))
            print("amostra champ_select:", json.dumps(cs[0], ensure_ascii=False)[:600])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"window_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"states": states, "frame_count": len(all_frames),
                               "frames": all_frames}, ensure_ascii=False), encoding="utf-8")
    print(f"\nHistórico salvo em: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
