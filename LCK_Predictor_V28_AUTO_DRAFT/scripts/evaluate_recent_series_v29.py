"""Avalia o modelo de producao contra os mapas mais recentes, fora da amostra.

Reconstroi o Elo pre-serie replicando recalc_ratings ate a vespera de cada
serie, entao avalia cada mapa com o draft real e o elenco real (nao o
draft_rosters salvo, que envelhece a cada troca de titular).

ATENCAO - VAZAMENTO. O Elo e reconstruido corretamente, mas a MAESTRIA nao:
_pc() le draft_player_champion, que e estado atual. Depois que
apply_completed_riot_series_to_draft_v10 incorpora uma serie, reavaliar os mapas
dessa serie usa maestria que ja viu o resultado deles, e os numeros ficam
otimistas. Para uma leitura honesta, rode ANTES de aplicar o estado de draft, ou
contra series ainda nao aplicadas (confira riot_draft_applied_v10). As metricas
publicadas em 2026-08-29 foram medidas antes da aplicacao.

Uso:  .venv/bin/python scripts/evaluate_recent_series_v29.py [--desde 2026-08-27]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server as S  # noqa: E402


def elo_before(day):
    """Elo de cada time considerando so as series ANTERIORES a `day`."""
    rows = S.db_rows("SELECT date,year,team1,team2,winner FROM series_history "
                     "WHERE day < ? ORDER BY date,series_key", (day,))
    elo = defaultdict(lambda: S.BASE_ELO)
    cy = None
    for r in rows:
        yr = int(r["year"])
        if cy is None:
            cy = yr
        elif yr != cy:
            for t in list(elo):
                elo[t] = S.BASE_ELO + S.SEASON_DECAY * (elo[t] - S.BASE_ELO)
            cy = yr
        t1, t2 = r["team1"], r["team2"]
        y = 1 if r["winner"] == t1 else 0
        d = S.ELO_K * (y - S.elo_prob(elo[t1], elo[t2]))
        elo[t1] += d
        elo[t2] -= d
    return elo


def collect(since):
    games = S.db_rows("""
        SELECT e.start_time, e.event_id, g.game_id, g.game_number,
               g.winner, g.draft_json
        FROM riot_games_v10 g JOIN riot_events_v10 e USING(event_id)
        WHERE substr(e.start_time,1,10) >= ?
          AND g.winner IS NOT NULL AND g.draft_json IS NOT NULL
          AND lower(g.state) LIKE '%complete%'
        ORDER BY e.start_time, g.game_number""", (since,))
    out = []
    for g in games:
        d = json.loads(g["draft_json"])
        blue, red = d.get("blue") or {}, d.get("red") or {}
        if len(blue.get("picks") or {}) < 5 or len(red.get("picks") or {}) < 5:
            continue
        # Snapshots gravados antes da correcao de canonical() guardaram o nome
        # cru do feed ("NONGSHIM RED FORCE"); normaliza na leitura.
        bt = S.canonical(blue.get("team")) or blue.get("team")
        rt = S.canonical(red.get("team")) or red.get("team")
        out.append({
            "day": g["start_time"][:10], "n": g["game_number"],
            "blue": bt, "red": rt,
            "bp": blue["picks"], "bpl": blue.get("players") or {},
            "rp": red["picks"], "rpl": red.get("players") or {},
            "y": 1 if (S.canonical(g["winner"]) or g["winner"]) == bt else 0,
        })
    return out


def metrics(rows, key):
    n = len(rows)
    if not n:
        return 0, 0, 0
    acc = sum(1 for r in rows if (r[key] >= .5) == bool(r["y"])) / n
    ll = -sum(r["y"] * math.log(max(r[key], 1e-9)) +
              (1 - r["y"]) * math.log(max(1 - r[key], 1e-9)) for r in rows) / n
    br = sum((r[key] - r["y"]) ** 2 for r in rows) / n
    return acc, ll, br


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2026-08-27")
    args = ap.parse_args()

    games = collect(args.desde)
    if not games:
        print("Nenhum mapa com draft e vencedor no periodo.")
        return 1

    elo_cache = {}
    rows = []
    print(f"{'dia':11} {'g':>2} {'azul':4} {'verm':4} {'venceu':7} "
          f"{'V8':>8} {'Elo':>8} {'delta pp':>9}  ok")
    print("-" * 68)
    for g in games:
        if g["day"] not in elo_cache:
            elo_cache[g["day"]] = elo_before(g["day"])
        elo = elo_cache[g["day"]]
        ev = S.evaluate_draft({
            "team_a": g["blue"], "team_b": g["red"], "side_a": "Blue",
            "picks_a": g["bp"], "picks_b": g["rp"],
            "players_a": g["bpl"], "players_b": g["rpl"],
            "rating_override": {g["blue"]: elo[g["blue"]], g["red"]: elo[g["red"]]},
        })
        if ev.get("error"):
            print(f"  {g['day']} g{g['n']}: {ev['error']}")
            continue
        p8 = ev["draft_game_probability_team_a"]
        pe = ev["game_baseline_probability_team_a"]
        ok = "sim" if (p8 >= .5) == bool(g["y"]) else "NAO"
        print(f"{g['day']:11} {g['n']:>2} {g['blue']:4} {g['red']:4} "
              f"{('azul' if g['y'] else 'vermelho'):7} {p8:>8.4f} {pe:>8.4f} "
              f"{(p8-pe)*100:>+9.2f}  {ok}")
        rows.append({**g, "p8": p8, "pe": pe,
                     "elo_diff": elo[g["blue"]] - elo[g["red"]],
                     "mastery": ev["mastery_diff"], "syn": ev["synergy_diff"]})

    print(f"\n{'modelo':22} {'n':>3} {'acuracia':>9} {'log-loss':>9} {'brier':>8}")
    print("-" * 56)
    for label, key in (("V8 (producao)", "p8"), ("Elo puro", "pe")):
        a, l, b = metrics(rows, key)
        print(f"{label:22} {len(rows):>3} {a:>9.4f} {l:>9.4f} {b:>8.4f}")

    med, means, scales, coef, b0 = S._draft_model_params()

    def scaled(r, f):
        vals = [r["elo_diff"], r["mastery"], r["syn"]]
        c = [coef[0], coef[1] * f, coef[2]]
        return S._sigmoid(b0 + sum(c[i] * ((vals[i] - means[i]) / scales[i]) for i in range(3)))

    print("\nContrafactual - escalando o coeficiente de mastery_eb_diff:")
    print(f"{'fator':>7} {'coef ef.':>9} {'acuracia':>9} {'log-loss':>9} {'brier':>8}")
    print("-" * 48)
    for f in (1.0, .5, .25, .125, 0.0):
        for r in rows:
            r["pf"] = scaled(r, f)
        a, l, b = metrics(rows, "pf")
        print(f"{f:>7.3f} {coef[1]*f:>9.4f} {a:>9.4f} {l:>9.4f} {b:>8.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
