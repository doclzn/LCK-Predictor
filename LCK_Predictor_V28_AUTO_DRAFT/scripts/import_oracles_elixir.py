"""Importa os CSVs oficiais do Oracle's Elixir para o banco do app.

Substitui o dump manual (pandas) que originou player_games/team_games e que
estava congelado em 2026-06-14. É idempotente: reimportar o mesmo arquivo
substitui as linhas daquela liga/ano em vez de duplicar.

Uso:
    python scripts/import_oracles_elixir.py CAMINHO.csv [CAMINHO2.csv ...]
        [--leagues LCK]        ligas a importar (vírgula)
        [--years 2025,2026]    anos a importar (vírgula); padrão: todos do arquivo
        [--no-rebuild]         só carrega as tabelas cruas, sem refazer agregações
        [--dry-run]            não grava nada, só relata

O CSV do OE traz 165 colunas contra as 39 que o banco tinha. As colunas novas
que interessam ao modelo são criadas automaticamente — em especial ban1..ban5 e
pick1..pick5, que não existiam e sem as quais análise de ban era impossível.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "lck_data_v1.sqlite"

csv.field_size_limit(10 ** 7)

ROLE_MAP = {
    "top": "top", "jng": "jng", "jungle": "jng", "mid": "mid", "middle": "mid",
    "bot": "bot", "bottom": "bot", "adc": "bot", "sup": "sup", "support": "sup",
}

# Colunas do CSV que passam a existir nas tabelas cruas, além das que já havia.
NEW_PLAYER_COLS = [
    ("league", "TEXT"), ("playerid", "TEXT"), ("teamid", "TEXT"),
    ("playoffs", "INTEGER"), ("game", "INTEGER"), ("participantid", "INTEGER"),
    ("datacompleteness", "TEXT"), ("url", "TEXT"),
    ("kp", "REAL"),                      # derivado: (kills+assists)/teamkills
    ("teamkills", "INTEGER"), ("teamdeaths", "INTEGER"),
    ("wpm", "REAL"), ("wcpm", "REAL"),
    ("damagetakenperminute", "REAL"), ("damagemitigatedperminute", "REAL"),
    ("earnedgoldshare", "REAL"), ("total cs", "REAL"),
    ("goldat20", "REAL"), ("xpat20", "REAL"), ("csat20", "REAL"),
    ("golddiffat20", "REAL"), ("xpdiffat20", "REAL"), ("csdiffat20", "REAL"),
    ("goldat25", "REAL"), ("xpat25", "REAL"), ("csat25", "REAL"),
    ("golddiffat25", "REAL"), ("xpdiffat25", "REAL"), ("csdiffat25", "REAL"),
]

NEW_TEAM_COLS = [
    ("league", "TEXT"), ("teamid", "TEXT"), ("datacompleteness", "TEXT"),
    ("url", "TEXT"), ("firstPick", "INTEGER"),
    ("ban1", "TEXT"), ("ban2", "TEXT"), ("ban3", "TEXT"), ("ban4", "TEXT"), ("ban5", "TEXT"),
    ("pick1", "TEXT"), ("pick2", "TEXT"), ("pick3", "TEXT"), ("pick4", "TEXT"), ("pick5", "TEXT"),
    ("ckpm", "REAL"), ("team kpm", "REAL"),
    ("opp_dragons", "REAL"), ("elementaldrakes", "REAL"), ("elders", "REAL"),
    ("void_grubs", "REAL"), ("opp_void_grubs", "REAL"),
    ("atakhans", "REAL"), ("opp_atakhans", "REAL"),
    ("turretplates", "REAL"), ("opp_turretplates", "REAL"),
    ("inhibitors", "REAL"), ("opp_inhibitors", "REAL"),
    ("opp_towers", "REAL"), ("opp_barons", "REAL"), ("opp_heralds", "REAL"),
    ("firstdragon", "REAL"), ("firstherald", "REAL"), ("firstbaron", "REAL"),
    ("firstmidtower", "REAL"), ("firsttothreetowers", "REAL"),
    ("gspd", "REAL"), ("gpr", "REAL"), ("earnedgoldshare", "REAL"),
    ("goldat20", "REAL"), ("golddiffat20", "REAL"),
    ("goldat25", "REAL"), ("golddiffat25", "REAL"),
]


def log(msg):
    # O console do Windows usa cp1252; acentos e setas quebrariam o print.
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def num(v, default=None):
    if v is None:
        return default
    s = str(v).strip()
    if s == "" or s.lower() in ("na", "nan", "null"):
        return default
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return default


def txt(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def ensure_columns(con, table, wanted, dry_run=False):
    """Cria as colunas que faltam. SQLite não tem ADD COLUMN IF NOT EXISTS.

    ALTER TABLE faz auto-commit no sqlite3, então em dry-run apenas relatamos o
    que seria criado — senão o 'ensaio' já alteraria o schema de verdade.
    """
    have = {d[1] for d in con.execute(f'PRAGMA table_info("{table}")')}
    added = []
    for name, typ in wanted:
        if name not in have:
            if not dry_run:
                con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {typ}')
            added.append(name)
    return added


def load_team_map(con):
    """teamname -> código canônico, aprendido do que já está no banco.

    Times mudam de nome entre splits (OKSavingsBank BRION -> HANJIN BRION), então
    o histórico do próprio banco é a fonte mais confiável desse mapeamento.
    """
    m = {}
    for tn, code in con.execute("SELECT DISTINCT teamname, team FROM player_games"):
        if tn and code:
            m[tn.strip()] = code
    return m


def build_indexes(con):
    con.execute('CREATE INDEX IF NOT EXISTS ix_pg_game ON player_games(gameid)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_pg_player ON player_games(playername, champion)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_pg_year ON player_games(year, league)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_tg_game ON team_games(gameid)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_tg_year ON team_games(year, league)')


# --------------------------------------------------------------------------
# Carga das tabelas cruas
# --------------------------------------------------------------------------
def import_csv(con, path, leagues, years, team_map, dry_run=False):
    pcols = [d[1] for d in con.execute('PRAGMA table_info("player_games")')]
    tcols = [d[1] for d in con.execute('PRAGMA table_info("team_games")')]

    player_rows, team_rows = [], []
    seen_scope = set()
    unknown_teams = defaultdict(int)
    skipped_incomplete = 0

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            league = (row.get("league") or "").strip()
            if leagues and league not in leagues:
                continue
            year = num(row.get("year"))
            if years and year not in years:
                continue

            teamname = txt(row.get("teamname"))
            code = team_map.get(teamname or "")
            if not code:
                unknown_teams[teamname] += 1

            if (row.get("datacompleteness") or "").strip().lower() == "ignore":
                skipped_incomplete += 1
                continue

            seen_scope.add((league, year))
            pos = (row.get("position") or "").strip().lower()

            base = dict(row)
            base["year"] = year
            base["team"] = code
            base["patch"] = num(row.get("patch"))

            if pos == "team":
                rec = {c: base.get(c) for c in tcols}
                rec["position"] = "team"
                for k in ("gamelength", "result", "kills", "deaths", "assists",
                          "teamkills", "teamdeaths", "towers", "dragons", "barons",
                          "heralds", "totalgold", "damagetochampions", "visionscore",
                          "wardsplaced", "wardskilled", "controlwardsbought", "game",
                          "playoffs", "firstPick"):
                    if k in rec:
                        rec[k] = num(rec.get(k))
                for k in tcols:
                    if k.startswith(("gold", "xp", "cs", "opp_", "first", "dpm",
                                     "elemental", "elders", "void", "atakhans",
                                     "turret", "inhibitors", "ckpm", "gspd", "gpr",
                                     "earned", "team kpm")):
                        rec[k] = num(rec.get(k))
                team_rows.append(rec)
            elif pos in ROLE_MAP:
                rec = {c: base.get(c) for c in pcols}
                rec["position"] = ROLE_MAP[pos]
                for k in pcols:
                    if k in ("gameid", "split", "date", "side", "position", "playername",
                             "teamname", "champion", "team", "league", "playerid",
                             "teamid", "datacompleteness", "url"):
                        continue
                    rec[k] = num(rec.get(k))
                k_, a_, tk = num(row.get("kills"), 0), num(row.get("assists"), 0), num(row.get("teamkills"), 0)
                rec["kp"] = round((k_ + a_) / tk, 6) if tk else None
                player_rows.append(rec)

    log(f"  {os.path.basename(path)}")
    log(f"    linhas jogador: {len(player_rows)} | linhas time: {len(team_rows)}"
        + (f" | ignoradas (datacompleteness=ignore): {skipped_incomplete}" if skipped_incomplete else ""))
    if unknown_teams:
        top = sorted(unknown_teams.items(), key=lambda x: -x[1])[:8]
        log(f"    AVISO times sem código canônico: {top}")

    if dry_run or not seen_scope:
        return len(player_rows), len(team_rows), seen_scope

    # Idempotência: o CSV é a fonte de verdade para cada (liga, ano) que ele cobre.
    for league, year in sorted(seen_scope):
        for table in ("player_games", "team_games"):
            has_league = "league" in [d[1] for d in con.execute(f'PRAGMA table_info("{table}")')]
            if has_league:
                con.execute(f'DELETE FROM "{table}" WHERE year=? AND (league=? OR league IS NULL)',
                            (year, league))
            else:
                con.execute(f'DELETE FROM "{table}" WHERE year=?', (year,))

    def insert(table, rows, cols):
        if not rows:
            return
        placeholders = ",".join("?" * len(cols))
        quoted = ",".join(f'"{c}"' for c in cols)
        con.executemany(f'INSERT INTO "{table}"({quoted}) VALUES({placeholders})',
                        [[r.get(c) for c in cols] for r in rows])

    insert("player_games", player_rows, pcols)
    insert("team_games", team_rows, tcols)
    return len(player_rows), len(team_rows), seen_scope


# --------------------------------------------------------------------------
# Reconstrução das agregações derivadas
# --------------------------------------------------------------------------
def league_clause(model_leagues, alias=""):
    """Cláusula SQL que restringe uma agregação às ligas que alimentam o modelo.

    Sem isso, importar uma segunda liga (LPL) contamina carreira, forma e meta
    silenciosamente: as agregações varriam player_games inteiro.
    """
    if not model_leagues:
        return "", []
    col = (alias + "." if alias else "") + "league"
    return f" AND {col} IN ({','.join('?' * len(model_leagues))})", sorted(model_leagues)


def rebuild_aggregations(con, local_years=(2025, 2026), current_year=2026,
                         model_leagues=("LCK",)):
    """Refaz as tabelas derivadas a partir de player_games.

    As constantes de suavização foram mantidas idênticas às do dump original
    para não deslocar o modelo: jogador×campeão e sinergia usam (w+2)/(n+4),
    meta de campeão usa (w+5)/(n+10) e counter usa (w+3)/(n+6).
    """
    yrs = tuple(local_years)
    qmark = ",".join("?" * len(yrs))
    lg_sql, lg_params = league_clause(model_leagues)

    rows = con.execute(f"""
        SELECT gameid, year, patch, side, position, playername, teamname, team,
               champion, result, gd15, xpd15, csd15, dpm
        FROM (SELECT *, golddiffat15 AS gd15, xpdiffat15 AS xpd15,
                     csdiffat15 AS csd15, dpm AS dpm FROM player_games)
        WHERE year IN ({qmark}) AND position IN ('top','jng','mid','bot','sup'){lg_sql}
    """, tuple(yrs) + tuple(lg_params)).fetchall()
    log(f"  base para agregação: {len(rows)} linhas de jogador")

    def agg(key_fn, filt=None):
        d = defaultdict(lambda: {"g": 0, "w": 0.0, "gd": 0.0, "xp": 0.0, "cs": 0.0, "dpm": 0.0, "n": 0})
        for r in rows:
            if filt and not filt(r):
                continue
            k = key_fn(r)
            if k is None:
                continue
            e = d[k]
            e["g"] += 1
            e["w"] += 1 if r["result"] else 0
            for src, dst in (("gd15", "gd"), ("xpd15", "xp"), ("csd15", "cs"), ("dpm", "dpm")):
                v = r[src]
                if v is not None:
                    e[dst] += float(v)
            e["n"] += 1
        return d

    # --- draft_player_overall -------------------------------------------------
    ov = defaultdict(lambda: [0, 0])
    for r in rows:
        ov[r["playername"]][0] += 1 if r["result"] else 0
        ov[r["playername"]][1] += 1
    con.execute("DELETE FROM draft_player_overall")
    con.executemany(
        "INSERT INTO draft_player_overall(player,wins,games,player_prior) VALUES(?,?,?,?)",
        [(p, w, n, (w + 2) / (n + 4)) for p, (w, n) in ov.items()])
    log(f"  draft_player_overall: {len(ov)}")

    # --- draft_player_champion (dois escopos) --------------------------------
    con.execute("DELETE FROM draft_player_champion")
    total_pc = 0
    for scope, yr_filter in (("local_2025_2026", None), (str(current_year), current_year)):
        d = agg(lambda r: (r["playername"], r["team"], r["position"], r["champion"]),
                (lambda r: r["year"] == yr_filter) if yr_filter else None)
        payload = []
        for (player, team, role, champ), e in d.items():
            n, w = e["g"], e["w"]
            payload.append((scope, player, team, role, champ, n, w, w / n, (w + 2) / (n + 4),
                            None,
                            e["gd"] / e["n"] if e["n"] else None,
                            e["xp"] / e["n"] if e["n"] else None,
                            e["cs"] / e["n"] if e["n"] else None,
                            e["dpm"] / e["n"] if e["n"] else None))
        con.executemany("""INSERT INTO draft_player_champion
            (scope,player,team,role,champion,games,wins,winrate,smoothed_winrate,kda,gd15,xpd15,csd15,dpm)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", payload)
        total_pc += len(payload)
    log(f"  draft_player_champion: {total_pc}")

    # --- draft_champion_meta --------------------------------------------------
    con.execute("DELETE FROM draft_champion_meta")
    total_cm = 0
    for scope, yr_filter in (("local_2025_2026", None), (str(current_year), current_year)):
        d = agg(lambda r: (r["position"], r["champion"]),
                (lambda r: r["year"] == yr_filter) if yr_filter else None)
        payload = [(scope, role, champ, e["g"], e["w"], e["w"] / e["g"],
                    (e["w"] + 5) / (e["g"] + 10),
                    e["gd"] / e["n"] if e["n"] else None)
                   for (role, champ), e in d.items()]
        con.executemany("""INSERT INTO draft_champion_meta
            (scope,role,champion,games,wins,winrate,smoothed_winrate,gd15)
            VALUES(?,?,?,?,?,?,?,?)""", payload)
        total_cm += len(payload)
    log(f"  draft_champion_meta: {total_cm}")

    # --- draft_synergy (pares do mesmo time no mesmo jogo) -------------------
    by_side = defaultdict(list)
    for r in rows:
        by_side[(r["gameid"], r["side"])].append(r)
    syn = defaultdict(lambda: [0, 0])
    for parts in by_side.values():
        champs = sorted(x["champion"] for x in parts if x["champion"])
        won = 1 if parts[0]["result"] else 0
        for i in range(len(champs)):
            for j in range(i + 1, len(champs)):
                k = (champs[i], champs[j])
                syn[k][0] += 1
                syn[k][1] += won
    con.execute("DELETE FROM draft_synergy")
    con.executemany("""INSERT INTO draft_synergy
        (champion_a,champion_b,games,wins,winrate,smoothed_winrate) VALUES(?,?,?,?,?,?)""",
        [(a, b, n, w, w / n, (w + 2) / (n + 4)) for (a, b), (n, w) in syn.items()])
    log(f"  draft_synergy: {len(syn)}")

    # --- draft_counter (mesma rota, lados opostos, mesmo jogo) ---------------
    by_game_role = defaultdict(list)
    for r in rows:
        by_game_role[(r["gameid"], r["position"])].append(r)
    cnt = defaultdict(lambda: [0, 0])
    for (gid, role), parts in by_game_role.items():
        if len(parts) != 2:
            continue
        a, b = parts
        if a["side"] == b["side"]:
            continue
        for x, y in ((a, b), (b, a)):
            if not x["champion"] or not y["champion"]:
                continue
            k = (role, x["champion"], y["champion"])
            cnt[k][0] += 1
            cnt[k][1] += 1 if x["result"] else 0
    con.execute("DELETE FROM draft_counter")
    con.executemany("""INSERT INTO draft_counter
        (role,champion_a,champion_b,games,wins_a,winrate_a,smoothed_winrate_a) VALUES(?,?,?,?,?,?,?)""",
        [(role, a, b, n, w, w / n, (w + 3) / (n + 6)) for (role, a, b), (n, w) in cnt.items()])
    log(f"  draft_counter: {len(cnt)}")

    # --- patch_player_champion / patch_champion_meta -------------------------
    con.execute("DELETE FROM patch_player_champion")
    d = agg(lambda r: (r["year"], r["patch"], r["playername"], r["team"], r["position"], r["champion"]))
    con.executemany("""INSERT INTO patch_player_champion
        (year,patch,player,team,role,champion,games,wins,gd15,xpd15,csd15,dpm,winrate)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(y, p, pl, tm, ro, ch, e["g"], e["w"],
          e["gd"] / e["n"] if e["n"] else None, e["xp"] / e["n"] if e["n"] else None,
          e["cs"] / e["n"] if e["n"] else None, e["dpm"] / e["n"] if e["n"] else None,
          e["w"] / e["g"]) for (y, p, pl, tm, ro, ch), e in d.items()])
    log(f"  patch_player_champion: {len(d)}")

    con.execute("DELETE FROM patch_champion_meta")
    d = agg(lambda r: (r["year"], r["patch"], r["position"], r["champion"]))
    con.executemany("""INSERT INTO patch_champion_meta
        (year,patch,position,champion,games,wins,gd15,xpd15,csd15,dpm,winrate,smoothed_winrate)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(y, p, ro, ch, e["g"], e["w"],
          e["gd"] / e["n"] if e["n"] else None, e["xp"] / e["n"] if e["n"] else None,
          e["cs"] / e["n"] if e["n"] else None, e["dpm"] / e["n"] if e["n"] else None,
          e["w"] / e["g"], (e["w"] + 5) / (e["g"] + 10))
         for (y, p, ro, ch), e in d.items()])
    log(f"  patch_champion_meta: {len(d)}")


def rebuild_current_form(con, model_leagues=("LCK",)):
    """Popula draft_current_lck_player_form com o split mais recente do banco.

    A tabela existia com 10 jogadores (DK e HLE), preenchidos à mão a partir do
    site em 2026-08-19 — por isso `current_season_web_coverage` era 0 para todas
    as outras equipes e a confiança do modelo ficava travada. Com o split atual
    importado, ela passa a ser derivada como o resto.
    """
    lg_sql, lg_params = league_clause(model_leagues)
    row = con.execute(f"""SELECT year, split FROM player_games
                          WHERE 1=1{lg_sql}
                          ORDER BY date DESC LIMIT 1""", tuple(lg_params)).fetchone()
    if not row:
        return 0
    year, split = row["year"], row["split"]
    scope = f"{'+'.join(sorted(model_leagues)) or 'ALL'} {year} {split}"
    stats = con.execute(f"""
        SELECT playername AS player, team,
               COUNT(*) AS games,
               AVG(CASE WHEN result THEN 1.0 ELSE 0.0 END) AS winrate,
               AVG(CAST(kills AS REAL) + assists) / NULLIF(AVG(NULLIF(deaths,0)),0) AS kda,
               AVG(golddiffat15) AS gd15, AVG(csdiffat15) AS csd15,
               AVG(xpdiffat15) AS xpd15, AVG(dpm) AS dpm
        FROM player_games
        WHERE year=? AND split=? AND position IN ('top','jng','mid','bot','sup'){lg_sql}
        GROUP BY playername, team
    """, (year, split) + tuple(lg_params)).fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    con.execute("DELETE FROM draft_current_lck_player_form")
    con.executemany("""INSERT INTO draft_current_lck_player_form
        (player,team,games,winrate,kda,gd15,csd15,xpd15,dpm,scope,snapshot_date,source_url)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r["player"], r["team"], r["games"],
          round(r["winrate"], 4) if r["winrate"] is not None else None,
          round(r["kda"], 2) if r["kda"] is not None else None,
          int(r["gd15"]) if r["gd15"] is not None else None,
          int(r["csd15"]) if r["csd15"] is not None else None,
          int(r["xpd15"]) if r["xpd15"] is not None else None,
          int(r["dpm"]) if r["dpm"] is not None else None,
          scope, today, "Oracle's Elixir match data")
         for r in stats])
    log(f"  draft_current_lck_player_form: {len(stats)} ({scope})")
    return len(stats)


def rebuild_career(con, current_season_year=2026, model_leagues=("LCK",)):
    """Constrói carreira e temporada atual por jogador a partir do histórico.

    Essas tabelas existiam com 10 jogadores (DK e HLE), copiados do site à mão —
    é o que zerava `career_coverage` e `current_season_web_coverage` na confiança
    do modelo para todas as outras equipes. Com o histórico completo importado,
    passam a ser derivadas.

    Ressalva honesta: é carreira *na LCK*, não a carreira global do jogador —
    passagens por outras ligas não entram enquanto só importarmos LCK.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    scope_lbl = "+".join(sorted(model_leagues)) or "ALL"
    src = f"Oracle's Elixir match data ({scope_lbl})"
    lg_sql, lg_params = league_clause(model_leagues)

    # --- por jogador x campeão, dois escopos --------------------------------
    con.execute("DELETE FROM draft_player_champion_web")
    total = 0
    for scope, where, params in (
        ("career", "", ()),
        ("S16", " AND year=?", (current_season_year,)),
    ):
        rows = con.execute(f"""
            SELECT playername AS player, champion,
                   COUNT(*) AS games,
                   AVG(CASE WHEN result THEN 1.0 ELSE 0.0 END) AS winrate,
                   (SUM(kills)+SUM(assists))*1.0/NULLIF(SUM(deaths),0) AS kda
            FROM player_games
            WHERE position IN ('top','jng','mid','bot','sup') AND champion IS NOT NULL{where}{lg_sql}
            GROUP BY playername, champion
        """, tuple(params) + tuple(lg_params)).fetchall()
        con.executemany("""INSERT INTO draft_player_champion_web
            (player,champion,games,winrate,kda,scope,snapshot_date,gol_player_id,source_url)
            VALUES(?,?,?,?,?,?,?,NULL,?)""",
            [(r["player"], r["champion"], r["games"],
              round(r["winrate"], 4) if r["winrate"] is not None else None,
              round(r["kda"], 2) if r["kda"] is not None else None,
              scope, today, src) for r in rows])
        total += len(rows)
    log(f"  draft_player_champion_web: {total}")

    # --- totais de carreira por jogador -------------------------------------
    rows = con.execute(f"""
        SELECT playername AS player,
               SUM(CASE WHEN result THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN result THEN 0 ELSE 1 END) AS losses,
               COUNT(*) AS games,
               AVG(CASE WHEN result THEN 1.0 ELSE 0.0 END) AS winrate,
               (SUM(kills)+SUM(assists))*1.0/NULLIF(SUM(deaths),0) AS kda
        FROM player_games
        WHERE position IN ('top','jng','mid','bot','sup'){lg_sql}
        GROUP BY playername
    """, tuple(lg_params)).fetchall()
    con.execute("DELETE FROM draft_player_career_total")
    con.executemany("""INSERT INTO draft_player_career_total
        (player,wins,losses,winrate,kda,games,snapshot_date,gol_player_id,source_url)
        VALUES(?,?,?,?,?,?,?,NULL,?)""",
        [(r["player"], r["wins"], r["losses"],
          round(r["winrate"], 4) if r["winrate"] is not None else None,
          round(r["kda"], 2) if r["kda"] is not None else None,
          r["games"], today, src) for r in rows])
    log(f"  draft_player_career_total: {len(rows)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--leagues", default="LCK",
                    help="ligas a CARREGAR nas tabelas cruas")
    ap.add_argument("--model-leagues", default="LCK",
                    help="ligas que alimentam as agregações do modelo "
                         "(vírgula; 'all' = todas). Carregar LPL sem incluí-la "
                         "aqui deixa os dados no banco sem tocar no modelo.")
    ap.add_argument("--years", default="")
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    leagues = {x.strip() for x in a.leagues.split(",") if x.strip()}
    ml = a.model_leagues.strip()
    model_leagues = () if ml.lower() == "all" else tuple(
        sorted({x.strip() for x in ml.split(",") if x.strip()}))
    years = {int(x) for x in a.years.split(",") if x.strip()} if a.years else None

    db = Path(a.db)
    if not db.exists():
        log(f"ERRO: banco não encontrado: {db}")
        return 2

    if not a.dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = db.with_name(f"{db.stem}.backup-{stamp}{db.suffix}")
        shutil.copy2(db, backup)
        log(f"backup: {backup.name}")

    con = sqlite3.connect(str(db), timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=60000")

    log(f"ligas={sorted(leagues) or 'todas'} anos={sorted(years) if years else 'todos'}"
        + (" [DRY-RUN]" if a.dry_run else ""))

    added_p = ensure_columns(con, "player_games", NEW_PLAYER_COLS, a.dry_run)
    added_t = ensure_columns(con, "team_games", NEW_TEAM_COLS, a.dry_run)
    verb = "seriam criadas" if a.dry_run else "criadas"
    if added_p:
        log(f"colunas {verb} em player_games ({len(added_p)}): {', '.join(added_p)}")
    if added_t:
        log(f"colunas {verb} em team_games ({len(added_t)}): {', '.join(added_t)}")
    if not a.dry_run:
        # As linhas do dump original são todas de LCK e não tinham a coluna.
        con.execute("UPDATE player_games SET league='LCK' WHERE league IS NULL")
        con.execute("UPDATE team_games SET league='LCK' WHERE league IS NULL")

    team_map = load_team_map(con)
    log(f"mapa de times conhecido: {len(team_map)} nomes")

    log("importando:")
    t0 = time.time()
    all_scope = set()
    for p in a.csvs:
        _, _, scope = import_csv(con, p, leagues, years, team_map, a.dry_run)
        all_scope |= scope

    if a.dry_run:
        log("dry-run: nada gravado")
        return 0

    build_indexes(con)
    con.commit()

    if not a.no_rebuild:
        log("reconstruindo agregações:")
        log(f"  ligas no modelo: {'todas' if not model_leagues else ', '.join(model_leagues)}")
        rebuild_aggregations(con, model_leagues=model_leagues)
        rebuild_current_form(con, model_leagues=model_leagues)
        rebuild_career(con, model_leagues=model_leagues)
        con.commit()

    g = con.execute("SELECT COUNT(DISTINCT gameid) FROM player_games").fetchone()[0]
    d0, d1 = con.execute("SELECT MIN(date), MAX(date) FROM player_games").fetchone()
    log(f"pronto em {time.time()-t0:.1f}s | jogos no banco: {g} | período: {d0} → {d1}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
