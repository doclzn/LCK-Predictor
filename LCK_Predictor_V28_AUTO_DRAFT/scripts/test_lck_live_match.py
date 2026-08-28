from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BRAZIL_TZ = timezone(timedelta(hours=-3))
DEFAULT_START = datetime(2026, 8, 26, 5, 0, tzinfo=BRAZIL_TZ)


TEAM_ALIASES = {
    "drx challengers": "krx challengers",
    "drx challenger": "krx challengers",
    "fearx youth": "bnk fearx youth",
}
def fold(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in text if not unicodedata.combining(c)).lower().strip()
    return TEAM_ALIASES.get(value, value)


def get_json(base_url: str, path: str):
    request = Request(base_url.rstrip("/") + path, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def write_log(handle, record):
    record["checked_at"] = datetime.now(timezone.utc).isoformat()
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()
    return record


def find_match(games, team_a, team_b):
    wanted = {fold(team_a), fold(team_b)}
    for game in games or []:
        actual = {fold(game.get("blueTeam") or game.get("blueCode")), fold(game.get("redTeam") or game.get("redCode"))}
        if wanted == actual:
            return game
    return None


def validate_draft(draft):
    errors = []
    for side in ("blue", "red"):
        picks = draft.get(side) or []
        if not isinstance(picks, list):
            errors.append(f"{side} não é lista")
            continue
        if len(picks) > 5:
            errors.append(f"{side} tem {len(picks)} slots")
        roles = [p.get("role") for p in picks if p.get("role")]
        if len(roles) != len(set(roles)):
            errors.append(f"{side} tem roles duplicadas")
    return errors


def run(args):
    start = datetime.fromisoformat(args.start).astimezone(BRAZIL_TZ)
    end = start + timedelta(hours=args.duration)
    output_dir = ROOT / "data" / "live_tests"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M")
    log_path = output_dir / f"lck_{stamp}_kt_bro.jsonl"

    print(f"Teste agendado: {start.isoformat()} (Brasília)")
    print(f"Janela: até {end.isoformat()}")
    print(f"Log: {log_path}")

    with log_path.open("a", encoding="utf-8") as log:
        while datetime.now(BRAZIL_TZ) < start - timedelta(minutes=args.lead):
            remaining = start - datetime.now(BRAZIL_TZ)
            print(f"Aguardando início ({remaining})", end="\r", flush=True)
            time.sleep(min(args.interval, max(1, int(remaining.total_seconds()))))

        print("\nMonitorando servidor V28...")
        found_games = set()
        draft_ok = 0
        polls = 0
        while datetime.now(BRAZIL_TZ) <= end:
            polls += 1
            try:
                live_path = "/api/live-games"
                if args.league_id:
                    live_path += f"?leagueId={quote(args.league_id)}"
                status, payload = get_json(args.base_url, live_path)
                game = find_match(payload.get("games"), args.team_a, args.team_b)
                record = write_log(log, {"kind": "live-games", "http_status": status, "payload": payload})
                if game:
                    game_id = str(game.get("gameId"))
                    if game_id not in found_games:
                        print(f"[OK] Partida detectada: {game.get('blueTeam')} vs {game.get('redTeam')} Game {game.get('gameNum')}")
                        found_games.add(game_id)
                    try:
                        draft_status, draft = get_json(args.base_url, f"/api/live-draft?gameId={quote(game_id)}")
                        errors = validate_draft(draft)
                        write_log(log, {"kind": "live-draft", "http_status": draft_status, "game": game, "payload": draft, "validation_errors": errors})
                        if draft_status == 200 and draft.get("ok") and not errors:
                            draft_ok += 1
                            print(f"[OK] Draft consultado: blue={len(draft.get('blue') or [])} red={len(draft.get('red') or [])}")
                        elif draft.get("error") == "DRAFT_NOT_READY":
                            print("[--] Draft ainda não publicado pela Riot")
                        else:
                            print(f"[ERRO] Draft inválido: {errors or draft.get('error')}")
                    except (HTTPError, URLError, TimeoutError) as error:
                        write_log(log, {"kind": "live-draft-error", "game": game, "error": repr(error)})
                        print(f"[ERRO] live-draft: {error}")
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
                write_log(log, {"kind": "live-games-error", "error": repr(error)})
                print(f"[ERRO] live-games: {error}")
            time.sleep(args.interval)

    print(f"Teste encerrado. polls={polls}, games={len(found_games)}, drafts_ok={draft_ok}")
    print(f"Log salvo em: {log_path}")
    return 0 if found_games else 2


def main():
    parser = argparse.ArgumentParser(description="Monitora uma partida LCK no servidor V28.")
    parser.add_argument("--start", default=DEFAULT_START.isoformat(), help="Início ISO-8601 com fuso; padrão: 2026-08-26T05:00:00-03:00")
    parser.add_argument("--duration", type=float, default=6, help="Horas de monitoramento após o início")
    parser.add_argument("--lead", type=float, default=20, help="Minutos antes do início para começar a consultar")
    parser.add_argument("--interval", type=int, default=30, help="Segundos entre consultas")
    parser.add_argument("--base-url", default="http://127.0.0.1:8828", help="URL do servidor V28")
    parser.add_argument("--team-a", default="KT Rolster")
    parser.add_argument("--team-b", default="HANJIN BRION")
    parser.add_argument("--league-id", default=None, help="Restringe a consulta a um league ID Riot, usado para testes isolados")
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
