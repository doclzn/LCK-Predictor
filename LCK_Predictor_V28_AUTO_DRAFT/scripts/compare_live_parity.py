"""Compara nosso capture ao vivo com o que dashboards públicos (andydanger) mostram.

Ambos usam os mesmos feeds Riot (window/details + getEventDetails). Imprime o
snapshot atual do jogo live para conferência de paridade (ouro/kills/torres/
dragões/barões/inibidores + CS/KDA/ouro por jogador + tempo de jogo).

Uso: runtime\\python.exe scripts/compare_live_parity.py [event_id]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import riot_feed  # noqa: E402

EVENT_ID = sys.argv[1] if len(sys.argv) > 1 else "116889604984222945"


def main():
    print("UTC:", datetime.now(timezone.utc).isoformat())
    cursor = riot_feed.RealtimeCursor()
    snap = riot_feed.fetch_event_live_incremental(EVENT_ID, cursor)
    gt = snap.get("game_time_seconds")
    tempo = f"{int(gt//60)}:{int(gt%60):02d}" if isinstance(gt, (int, float)) else str(gt)
    print(f"game_state={snap.get('game_state')} tempo={tempo} patch={snap.get('patch')}")
    for side in ("blue", "red"):
        t = snap[side]
        print(f"\n[{side.upper()}] {t.get('team')}  gold={t.get('gold')} kills={t.get('kills')} "
              f"towers={t.get('towers')} dragons={t.get('dragons')} barons={t.get('barons')} "
              f"inh={t.get('inhibitors')}")
        for p in t.get("participants") or []:
            print(f"   {str(p.get('player')):<14} {str(p.get('champion')):<10} "
                  f"cs={p.get('cs'):>3} {p.get('kills')}/{p.get('deaths')}/{p.get('assists')} "
                  f"gold={p.get('gold')} lvl={p.get('level')} items={len(p.get('items') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
