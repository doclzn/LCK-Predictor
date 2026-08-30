"""Registra eventos de ligas alem da LCK (LPL, CBLOL) em riot_events_v10.

POR QUE SO OS EVENTOS, E NAO OS MAPAS:

  - series_history / Elo. recalc_ratings so escreve times presentes em
    FULL_NAMES (as 10 da LCK) e nao ha jogo entre ligas para ancorar as
    escalas — juntar tudo num pool so produziria Elo sem sentido. A protecao
    ja existe: canonical() devolve None para todo time de fora, e
    archive_completed_series_v10 descarta a serie. Este script nao mexe nisso.

  - draft_player_champion / draft_synergy. apply_completed_riot_series_to_draft_v10
    escreve nessas tabelas SEM filtro de liga. Trazer mapas da LPL para
    riot_games_v10 faria as agregacoes da LCK absorverem jogadores chineses no
    proximo ciclo — exatamente o que a blindagem MODEL_LEAGUES existe para
    evitar, e o que a investigacao da LPL mostrou que PIORA as features por
    jogador. Alimentar os acumuladores com LPL e um passo deliberado que
    depende de tornar aquela funcao ciente de liga primeiro.

Uso:  .venv/bin/python scripts/ingest_other_leagues_v29.py [--ligas LPL,CBLOL]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import riot_feed as R  # noqa: E402
import server as S  # noqa: E402

LEAGUES = {
    "LPL": "98767991314006698",
    "CBLOL": "98767991332355509",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ligas", default="LPL")
    args = ap.parse_args()

    total = 0
    for name in [x.strip().upper() for x in args.ligas.split(",") if x.strip()]:
        lid = LEAGUES.get(name)
        if not lid:
            print(f"{name}: liga desconhecida, pulando")
            continue
        try:
            events = R.events_from(R.get_schedule("en-US", league_id=lid))
        except Exception as e:
            print(f"{name}: falha ao consultar o feed - {type(e).__name__}: {e}")
            continue
        stored = 0
        for ev in events:
            if str(ev.get("state") or "").lower() != "completed":
                continue
            # store_riot_event usa match.id quando o evento nao traz id proprio.
            S.store_riot_event(ev)
            stored += 1
        total += stored
        print(f"{name}: {stored} eventos concluidos registrados")

    # Confere que nada vazou para o historico de Elo da LCK.
    leaked = S.db_rows("""SELECT DISTINCT team1 FROM series_history
                          WHERE team1 NOT IN (SELECT team FROM current_ratings)
                          UNION
                          SELECT DISTINCT team2 FROM series_history
                          WHERE team2 NOT IN (SELECT team FROM current_ratings)""")
    if leaked:
        print("ATENCAO: times fora da LCK entraram em series_history:", leaked)
        return 1
    print(f"\ntotal: {total} eventos | series_history segue so com times da LCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
