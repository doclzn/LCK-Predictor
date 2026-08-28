
from __future__ import annotations

import json
import hashlib
import math
import mimetypes
import os
import random
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
from collections import defaultdict, deque
from datetime import date, datetime, timezone, timedelta
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Python.org's Windows embeddable runtime uses pythonXY._pth and may omit
# the script directory from sys.path. Add the application folder explicitly
# before importing local modules.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from riot_feed import (
    get_live as riot_get_live, get_schedule as riot_get_schedule,
    get_event_details as riot_get_event_details, events_from as riot_events_from,
    event_from_details as riot_event_from_details, is_lck_event as riot_is_lck_event,
    fetch_event_live as riot_fetch_event_live, fetch_game_snapshot as riot_fetch_game_snapshot,
    fetch_event_live_incremental as riot_fetch_event_live_incremental,
    RealtimeCursor as riot_RealtimeCursor,
    fetch_draft_probe as riot_fetch_draft_probe,
    discover_live_games as riot_discover_live_games,
    fetch_live_draft as riot_fetch_live_draft,
    DraftNotReady as riot_DraftNotReady,
    champion_image as riot_champion_image, item_image as riot_item_image
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DB = ROOT / "data" / "lck_data_v1.sqlite"
HOST = "127.0.0.1"
PORT = 8828
APP_VERSION = "V28_AUTO_DRAFT"

BASE_ELO = 1500.0
ELO_K = 64.0
SEASON_DECAY = 0.65
TOURNAMENT = "LCK 2026 Rounds 3-4"
UPDATE_URL = "https://gol.gg/tournament/tournament-matchlist/LCK%202026%20Rounds%203-4/"
RIOT_LIVE_POLL_SECONDS = 10
RIOT_DISCOVER_SECONDS = 15
RIOT_SCHEDULE_SECONDS = 300
DRAFT_WATCH_SECONDS = 5
# V28.1: cursor incremental do feed live (startingTime) por game_id.
_LIVE_CURSOR = riot_RealtimeCursor()
DEFAULT_EVENT_ID = "115548147900619029"
LCK_LEAGUE_ID = "98767991310872058"
# Ligas que alimentam consultas às tabelas cruas (player_games/team_games).
# O banco pode conter outras ligas (LPL) só para avaliação; sem este filtro,
# um tricode ou nickname repetido entre ligas contaminaria priors e histórico.
MODEL_LEAGUES = tuple(x.strip() for x in
                      os.environ.get("MODEL_LEAGUES", "LCK").split(",") if x.strip())
_LG_IN = ",".join("?" * len(MODEL_LEAGUES))
LG_SQL = f" AND league IN ({_LG_IN})" if MODEL_LEAGUES else ""
LG_ARGS = tuple(MODEL_LEAGUES)
BRAZIL_TZ = timezone(timedelta(hours=-3))

ALIASES = {
    "Gen.G":"GEN","GEN":"GEN",
    "Dplus KIA":"DK","Dplus Kia":"DK","Dplus KIA":"DK","DK":"DK",
    "Hanwha Life Esports":"HLE","Hanwha Life":"HLE","HLE":"HLE",
    "T1":"T1",
    "KT Rolster":"KT","KT":"KT",
    "BNK FearX":"BFX","BNK FEARX":"BFX","BFX":"BFX",
    "HANJIN BRION":"BRO","Hanjin BRION":"BRO","BRO":"BRO",
    "DN SOOPers":"DNS","DNS":"DNS",
    "Nongshim RedForce":"NS","NS":"NS",
    "Kiwoom DRX":"KRX","DRX":"KRX","KRX":"KRX",
}
FULL_NAMES = {
    "BRO":"HANJIN BRION","KRX":"Kiwoom DRX","DNS":"DN SOOPers",
    "NS":"Nongshim RedForce","BFX":"BNK FEARX","KT":"KT Rolster",
    "DK":"Dplus KIA","T1":"T1","GEN":"Gen.G","HLE":"Hanwha Life Esports",
}


def db_connect():
    """Conexão única do app. O servidor é multi-thread e, durante uma série ao
    vivo, várias requisições escrevem ao mesmo tempo (snapshot, evento, jogos,
    health). Sem busy_timeout o segundo escritor falha na hora com
    'database is locked' e derruba a requisição."""
    con = sqlite3.connect(DB, timeout=15)
    con.execute("PRAGMA busy_timeout=15000")
    return con


def _enable_wal_once():
    """WAL permite leitores concorrentes com um escritor, em vez de bloquear o
    banco inteiro a cada escrita. É persistente no arquivo — basta ligar uma vez."""
    try:
        with sqlite3.connect(DB, timeout=15) as con:
            con.execute("PRAGMA busy_timeout=15000")
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
    except Exception as e:
        print(f"[db] não foi possível ligar WAL: {type(e).__name__}: {e}")


def db_rows(sql, params=()):
    with db_connect() as con:
        con.row_factory = sqlite3.Row
        return [dict(x) for x in con.execute(sql, params).fetchall()]


def db_one(sql, params=()):
    rows = db_rows(sql, params)
    return rows[0] if rows else None


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def elo_prob(a, b):
    return 1.0 / (1.0 + 10.0 ** (-(float(a)-float(b))/400.0))


def match_analysis(a, b):
    try:
        row = db_one("""SELECT * FROM match_analysis
                        WHERE (team_a=? AND team_b=?) OR (team_a=? AND team_b=?)
                        ORDER BY analysis_date DESC LIMIT 1""", (a,b,b,a))
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    if row["team_a"] == a:
        return row
    rev = dict(row)
    rev["team_a"], rev["team_b"] = a, b
    for k in ("model_probability_team_a","elo_probability_team_a","compact_probability_team_a"):
        if rev.get(k) is not None:
            rev[k] = 1-float(rev[k])
    for x,y in [
        ("recent_form_a","recent_form_b"),("h2h_series_2026_a","h2h_series_2026_b"),
        ("h2h_games_2026_a","h2h_games_2026_b"),("last_h2h_score_a","last_h2h_score_b"),
        ("last_h2h_kills_a","last_h2h_kills_b"),("last_h2h_towers_a","last_h2h_towers_b"),
        ("last_h2h_dragons_a","last_h2h_dragons_b"),("baseline_gd15_a","baseline_gd15_b"),
        ("baseline_first_tower_a","baseline_first_tower_b"),
        ("baseline_dragon_control_a","baseline_dragon_control_b"),
        ("baseline_nashor_control_a","baseline_nashor_control_b"),("edge_a","edge_b")
    ]:
        rev[x], rev[y] = rev.get(y), rev.get(x)
    return rev


def _series_score_outcomes_binomial(series_p_a: float, best_of: int):
    """Enumeração de placares exatos para qualquer best-of-N (usado quando não
    há modelo treinado dedicado, ex.: BO5). Assume prob. por mapa i.i.d.,
    resolvida por bisseção para preservar a probabilidade de série informada,
    reaproveitando a mesma árvore recursiva de _v18_series_win_prob."""
    need=int(best_of)//2+1
    p=min(max(float(series_p_a),1e-6),1-1e-6)
    lo,hi=0.0,1.0
    for _ in range(60):
        mid=(lo+hi)/2
        if _v18_series_win_prob(0,0,best_of,mid,mid)<p:lo=mid
        else:hi=mid
    q=(lo+hi)/2
    outcomes=[]
    for loser_wins in range(need):
        games=need+loser_wins
        combos=math.comb(games-1,loser_wins)
        outcomes.append({"score":f"{need}–{loser_wins}","winner_side":"a",
                          "probability":combos*(q**need)*((1-q)**loser_wins)})
        outcomes.append({"score":f"{need}–{loser_wins}","winner_side":"b",
                          "probability":combos*((1-q)**need)*(q**loser_wins)})
    return outcomes,need

def scoreline_probability(a: str, b: str, series_p_a: float, best_of: int = 3):
    """Return exact score probabilities for a series while preserving the
    central series P(A). BO3 uses the trained Two-stage scoreline model;
    any other best-of (ex.: BO5 nos playoffs) usa um modelo binomial
    calibrado pela mesma probabilidade de série, já que o modelo treinado
    só existe para BO3."""
    best_of=int(best_of or 3)
    p=float(series_p_a)

    if best_of==3:
        cfg=db_one("SELECT * FROM scoreline_model_config_v9 LIMIT 1")
        ra=db_one("SELECT * FROM current_ratings WHERE team=?",(a,))
        rb=db_one("SELECT * FROM current_ratings WHERE team=?",(b,))
        if not cfg or not ra or not rb:
            return None

        med=json.loads(cfg["medians_json"])
        means=json.loads(cfg["means_json"])
        scales=json.loads(cfg["scales_json"])
        coef=json.loads(cfg["coef_json"])
        diffs=[
            float(ra["elo"])-float(rb["elo"]),
            float(ra["series_winrate_last5"])-float(rb["series_winrate_last5"]),
            float(ra["series_winrate_last10"])-float(rb["series_winrate_last10"]),
        ]

        def sweep(vals):
            z=float(cfg["intercept"])
            for i,v in enumerate(vals):
                vv=med[i] if v is None else float(v)
                z += float(coef[i])*((vv-float(means[i]))/float(scales[i]))
            return 1/(1+math.exp(-z))

        sa=sweep(diffs)
        sb=sweep([-x for x in diffs])
        outcomes=[
            {"winner":a,"score":"2–0","probability":p*sa},
            {"winner":a,"score":"2–1","probability":p*(1-sa)},
            {"winner":b,"score":"2–1","probability":(1-p)*(1-sb)},
            {"winner":b,"score":"2–0","probability":(1-p)*sb},
        ]
        outcomes.sort(key=lambda x:x["probability"],reverse=True)
        game3=sum(x["probability"] for x in outcomes if x["score"]=="2–1")
        quality=db_one("""SELECT exact_accuracy,top2_accuracy,multiclass_log_loss
                          FROM scoreline_validation_v9
                          WHERE model='Two-stage scoreline V9' LIMIT 1""")
        return {
            "outcomes":outcomes,
            "most_likely":outcomes[0],
            "game3_probability":game3,
            "sweep_probability":1-game3,
            "expected_games":2+game3,
            "model_quality":quality,
            "best_of":3,"decisive_game_number":3,"model":"trained_two_stage_v9",
            "note":"Exact score is more uncertain than series winner. The score module preserves the central series probability."
        }

    raw,need=_series_score_outcomes_binomial(p,best_of)
    outcomes=[{"winner":a if o["winner_side"]=="a" else b,"score":o["score"],"probability":o["probability"]}
              for o in raw]
    outcomes.sort(key=lambda x:x["probability"],reverse=True)
    decisive=sum(o["probability"] for o in outcomes if o["score"].split("–")[1]==str(need-1))
    expected_games=sum(o["probability"]*(need+int(o["score"].split("–")[1])) for o in outcomes)
    return {
        "outcomes":outcomes,
        "most_likely":outcomes[0],
        "game3_probability":decisive,
        "sweep_probability":1-decisive,
        "expected_games":expected_games,
        "model_quality":None,
        "best_of":best_of,"decisive_game_number":best_of,"model":"binomial_calibrated",
        "note":f"Placar de BO{best_of} calculado por um modelo binomial calibrado pela probabilidade da série — não é o modelo treinado (Elo + histórico), que hoje cobre apenas BO3."
    }


def api_bootstrap():
    meta = {x["key"]:x["value"] for x in db_rows("SELECT key,value FROM metadata")}
    try:
        upcoming = db_rows("SELECT * FROM upcoming_matches ORDER BY date,team_a")
        for u in upcoming:
            try:
                u["scoreline"]=scoreline_probability(u["team_a"],u["team_b"],float(u["probability_team_a"]))
            except Exception:
                u["scoreline"]=None
    except sqlite3.OperationalError:
        upcoming = []
    try:
        status = db_one("SELECT * FROM update_status LIMIT 1")
    except sqlite3.OperationalError:
        status = None
    return {
        "ratings": db_rows("SELECT * FROM current_ratings ORDER BY rank"),
        "predictions": db_rows("SELECT * FROM current_predictions ORDER BY date,team_a"),
        "upcoming": upcoming,
        "evaluation": db_rows("SELECT * FROM model_evaluation"),
        "history": db_rows("""SELECT date,team1,team2,winner,wins1,wins2,n_games,source
                              FROM series_history ORDER BY date DESC LIMIT 260"""),
        "meta": meta,
        "update_status": status,
        "riot": {
            "events": riot_events_api_v10(),
            "last_snapshot": current_cached_snapshot_v10(),
            "sources": db_rows("SELECT * FROM source_registry_v10 ORDER BY priority"),
            "models": db_rows("SELECT * FROM model_registry_v10 ORDER BY rowid")
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def api_match(a, b, best_of=None):
    a,b = a.upper(), b.upper()
    ra = db_one("SELECT * FROM current_ratings WHERE team=?", (a,))
    rb = db_one("SELECT * FROM current_ratings WHERE team=?", (b,))
    if not ra or not rb:
        return None

    try:
        u = db_one("""SELECT * FROM upcoming_matches
                      WHERE (team_a=? AND team_b=?) OR (team_a=? AND team_b=?)
                      ORDER BY date LIMIT 1""",(a,b,b,a))
    except sqlite3.OperationalError:
        u = None
    if u:
        p=float(u["probability_team_a"]); pe=float(u["elo_probability_team_a"])
        if u["team_a"] != a:
            p,pe=1-p,1-pe
        an=match_analysis(a,b)
        pc=an.get("compact_probability_team_a") if an else None
        bo=best_of
        if not bo and u["event_id"]:
            row=db_one("SELECT match_strategy_count FROM riot_events_v10 WHERE event_id=?",(u["event_id"],))
            if row:bo=row.get("match_strategy_count")
        return {"team_a":ra,"team_b":rb,"probability_team_a":p,"probability_team_b":1-p,
                "elo_probability_team_a":pe,"compact_probability_team_a":pc,
                "mode":u["prediction_mode"],"prediction_date":u["date"],"note":u["source"],
                "analysis":an,"scoreline":scoreline_probability(a,b,p,bo or 3)}

    s = db_one("""SELECT * FROM current_predictions WHERE
                  (team_a=? AND team_b=?) OR (team_a=? AND team_b=?)
                  ORDER BY date DESC LIMIT 1""",(a,b,b,a))
    if s:
        p=float(s["conservative_blend_team_a"])
        pe=float(s["elo_probability_team_a"])
        pc=float(s["compact_probability_team_a"])
        if s["team_a"] != a:
            p,pe,pc = 1-p,1-pe,1-pc
        return {"team_a":ra,"team_b":rb,"probability_team_a":p,"probability_team_b":1-p,
                "elo_probability_team_a":pe,"compact_probability_team_a":pc,
                "mode":"saved_blend","prediction_date":s["date"],"note":s["note"],
                "analysis":match_analysis(a,b),"scoreline":scoreline_probability(a,b,p,best_of or 3)}

    p=elo_prob(ra["elo"],rb["elo"])
    return {"team_a":ra,"team_b":rb,"probability_team_a":p,"probability_team_b":1-p,
            "elo_probability_team_a":p,"compact_probability_team_a":None,
            "mode":"elo_fallback","prediction_date":None,"note":"Elo live fallback",
            "analysis":match_analysis(a,b),"scoreline":scoreline_probability(a,b,p,best_of or 3)}


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows=[]
        self.in_tr=False
        self.in_td=False
        self.cur=[]
        self.buf=[]
    def handle_starttag(self,tag,attrs):
        if tag=="tr":
            self.in_tr=True; self.cur=[]
        elif tag=="td" and self.in_tr:
            self.in_td=True; self.buf=[]
    def handle_data(self,data):
        if self.in_td:
            self.buf.append(data)
    def handle_endtag(self,tag):
        if tag=="td" and self.in_td:
            txt=" ".join("".join(self.buf).replace("\xa0"," ").split())
            self.cur.append(txt); self.in_td=False
        elif tag=="tr" and self.in_tr:
            if self.cur: self.rows.append(self.cur)
            self.in_tr=False


def canonical(x):
    x=" ".join((x or "").split())
    if x in ALIASES: return ALIASES[x]
    low=x.lower()
    for k,v in ALIASES.items():
        if k.lower()==low: return v
    return None



# ---------------------------------------------------------------------------
# V10 — Riot / LoL Esports primary match feed
# ---------------------------------------------------------------------------
def source_health(source,status,error=None,records_seen=None):
    now=datetime.now(timezone.utc).isoformat()
    with db_connect() as con:
        old=con.execute("SELECT records_seen,last_success FROM riot_source_health_v10 WHERE source=?",(source,)).fetchone()
        seen=(old[0] if old else 0) if records_seen is None else int(records_seen)
        success=(old[1] if old else None)
        if status=="ok": success=now
        con.execute("""INSERT OR REPLACE INTO riot_source_health_v10
          (source,status,last_success,last_attempt,last_error,records_seen)
          VALUES(?,?,?,?,?,?)""",(source,status,success,now,None if status=="ok" else str(error or ""),seen))
        con.commit()


def _event_team_info(ev):
    match=(ev or {}).get("match") or {}
    teams=match.get("teams") or []
    def one(i):
        t=teams[i] if len(teams)>i else {}
        return {
          "name":t.get("name"),"code":t.get("code"),
          "id":t.get("id"),
          "wins":((t.get("result") or {}).get("gameWins")),
          "record":t.get("record")
        }
    return one(0),one(1)


def _event_strategy(ev):
    st=((ev.get("match") or {}).get("strategy") or {})
    return st.get("type"),st.get("count")


def _event_id(ev):
    """Event id is at the top level on getLive/getEventDetails payloads, but only
    under match.id on getSchedule payloads."""
    if not ev: return None
    eid = ev.get("id") or ((ev.get("match") or {}).get("id"))
    return str(eid) if eid else None


def _attribute_game_winner_v10(con,eid,prev,a,b,ev,now):
    """A Riot não publica o vencedor de cada mapa — só o placar da série. Quando
    o placar sobe, o time que ganhou o ponto venceu o mapa que acabou de fechar.
    Só grava quando a atribuição é inequívoca (exatamente um mapa novo fechado)."""
    try:
        prev_by={}
        if prev.get("team_a_code") is not None:prev_by[prev.get("team_a_code")]=prev.get("score_a")
        if prev.get("team_b_code") is not None:prev_by[prev.get("team_b_code")]=prev.get("score_b")
        gained=[c for c,w in ((a["code"],a["wins"]),(b["code"],b["wins"]))
                if c and w is not None and prev_by.get(c) is not None and int(w)>int(prev_by[c])]
        if len(gained)!=1:return
        winner=canonical(gained[0]) or gained[0]
        pending=[str(g.get("id")) for g in ((ev.get("match") or {}).get("games") or [])
                 if str(g.get("state") or "").lower()=="completed" and g.get("id")]
        if not pending:return
        rows=con.execute("""SELECT game_id FROM riot_games_v10
                            WHERE event_id=? AND winner IS NULL AND game_id IN (%s)
                            ORDER BY game_number""" % ",".join("?"*len(pending)),
                         [eid]+pending).fetchall()
        if len(rows)!=1:return
        con.execute("UPDATE riot_games_v10 SET winner=?,updated_at=? WHERE game_id=?",
                    (winner,now,rows[0]["game_id"]))
    except Exception:
        pass


def _close_last_game_winner_v10(con,eid,a,b,ev,now):
    """Fecha por dedução o único mapa sem vencedor: se todos os outros mapas
    concluídos já têm dono, o que falta é forçosamente o time cujo total de
    vitórias ainda está 1 abaixo do placar da série. É exato, não heurística —
    cobre a transição perdida quando o app estava fora do ar."""
    try:
        totals={}
        for code,wins in ((a["code"],a["wins"]),(b["code"],b["wins"])):
            if not code or wins is None:return
            totals[canonical(code) or code]=int(wins)
        completed=[str(g.get("id")) for g in ((ev.get("match") or {}).get("games") or [])
                   if str(g.get("state") or "").lower()=="completed" and g.get("id")]
        if not completed:return
        rows=con.execute("""SELECT game_id,winner FROM riot_games_v10
                            WHERE event_id=? AND game_id IN (%s)""" % ",".join("?"*len(completed)),
                         [eid]+completed).fetchall()
        missing=[r["game_id"] for r in rows if not r["winner"]]
        if len(missing)!=1:return
        known={}
        for r in rows:
            if r["winner"]:known[r["winner"]]=known.get(r["winner"],0)+1
        short=[t for t,n in totals.items() if n-known.get(t,0)==1]
        if len(short)!=1:return
        con.execute("UPDATE riot_games_v10 SET winner=?,updated_at=? WHERE game_id=?",
                    (short[0],now,missing[0]))
    except Exception:
        pass


def store_riot_event(ev):
    eid=_event_id(ev)
    if not ev or not eid: return
    a,b=_event_team_info(ev)
    typ,count=_event_strategy(ev)
    league=(ev.get("league") or {}).get("name")
    streams=ev.get("streams") or []
    now=datetime.now(timezone.utc).isoformat()
    with db_connect() as con:
        con.row_factory=sqlite3.Row
        prev=con.execute("SELECT * FROM riot_events_v10 WHERE event_id=?",(eid,)).fetchone()
        prev=dict(prev) if prev else {}

        def keep(new,col):
            """Payloads da Riot variam de formato (getSchedule não traz os mesmos
            campos que getLive/getEventDetails). Um campo ausente não pode apagar
            um valor já conhecido — senão uma série ao vivo volta a parecer
            'pré-jogo' quando o refresh seguinte vem incompleto."""
            return prev.get(col) if new is None else new

        con.execute("""INSERT OR REPLACE INTO riot_events_v10
          (event_id,league,block_name,start_time,state,match_strategy_type,match_strategy_count,
           team_a,team_b,team_a_code,team_b_code,score_a,score_b,streams_json,raw_json,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            eid,keep(league,"league"),keep(ev.get("blockName"),"block_name"),
            keep(ev.get("startTime"),"start_time"),keep(ev.get("state"),"state"),
            keep(typ,"match_strategy_type"),keep(count,"match_strategy_count"),
            keep(a["name"],"team_a"),keep(b["name"],"team_b"),
            keep(a["code"],"team_a_code"),keep(b["code"],"team_b_code"),
            keep(a["wins"],"score_a"),keep(b["wins"],"score_b"),
            json.dumps(streams,ensure_ascii=False,separators=(",",":")) if streams else keep(None,"streams_json"),
            json.dumps(ev,ensure_ascii=False,separators=(",",":")),now
        ))
        # O estado por mapa gravado a partir do snapshot congela quando o feed
        # do mapa para de publicar. O EventDetails é a fonte autoritativa —
        # sincronizamos só o state das linhas que já existem.
        for g in ((ev.get("match") or {}).get("games") or []):
            gid=g.get("id");gstate=g.get("state")
            if gid and gstate:
                con.execute("UPDATE riot_games_v10 SET state=?,updated_at=? WHERE game_id=?",
                            (gstate,now,str(gid)))
        _attribute_game_winner_v10(con,eid,prev,a,b,ev,now)
        _close_last_game_winner_v10(con,eid,a,b,ev,now)
        con.commit()


def _local_date_from_iso(x):
    try:
        dt=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return dt.astimezone(BRAZIL_TZ).date().isoformat()
    except Exception:
        return str(x or "")[:10]


# ---------------------------------------------------------------------------
# V23 — Matchday cache hygiene
# ---------------------------------------------------------------------------
def _local_dt_from_iso_v23(x):
    try:
        dt=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BRAZIL_TZ)
    except Exception:
        return None

def _now_local_v23():
    return datetime.now(BRAZIL_TZ)

def v23_ensure_schedule_schema():
    with db_connect() as con:
        cols={r[1] for r in con.execute("PRAGMA table_info(upcoming_matches)")}
        for col,typ in (("start_time","TEXT"),("event_id","TEXT"),("updated_at","TEXT")):
            if col not in cols:
                con.execute(f"ALTER TABLE upcoming_matches ADD COLUMN {col} {typ}")
        con.commit()

def _upcoming_row_is_current_v23(row,now=None):
    return v24_match_state(row.get("start_time"),legacy_date=row.get("date"),now=now)=="upcoming"


def _riot_event_is_stale_v23(row,now=None):
    return v24_match_state(row.get("start_time"),row.get("state"),row.get("score_a"),row.get("score_b"),
                           now=now,best_of=row.get("match_strategy_count"))=="pending"


def prune_stale_schedule_v23():
    """Hide/delete stale scheduled rows without inventing a final result."""
    v23_ensure_schedule_schema()
    now=_now_local_v23()
    rows=db_rows("SELECT rowid,* FROM upcoming_matches")
    stale=[r["rowid"] for r in rows if not _upcoming_row_is_current_v23(r,now)]
    if stale:
        with db_connect() as con:
            con.executemany("DELETE FROM upcoming_matches WHERE rowid=?",[(x,) for x in stale])
            con.commit()
    return len(stale)

def v23_schedule_status():
    now=_now_local_v23()
    health=db_one("""SELECT * FROM riot_source_health_v10
                     WHERE source='Riot schedule' LIMIT 1""") or {}
    stale_events=sum(1 for r in db_rows("SELECT * FROM riot_events_v10")
                     if _riot_event_is_stale_v23(r,now))
    return {
      "local_now":now.isoformat(),
      "last_success":health.get("last_success"),
      "last_attempt":health.get("last_attempt"),
      "status":health.get("status") or "cache",
      "stale_events_hidden":stale_events,
      "pending_sync":v24_schedule_audit().get("pending_sync",0),
      "timezone":"UTC-03:00"
    }


# ---------------------------------------------------------------------------
# V24 — canonical match-state machine
# ---------------------------------------------------------------------------
def v24_match_state(start_time=None, upstream_state=None, score_a=None, score_b=None, now=None, legacy_date=None, best_of=None):
    """Canonical state: completed/live/upcoming/pending/unknown.

    One function owns time/state decisions so Home, Matches and refresh do not
    independently invent rules. 'pending' means the scheduled start already
    passed but no trustworthy final/live state is available; it must NOT be
    shown as upcoming or live.
    """
    now=now or _now_local_v23()
    state=str(upstream_state or '').strip().lower()
    # Explicit completed state/score is authoritative.
    if 'complete' in state:
        return 'completed'
    try:
        sa=int(score_a) if score_a is not None else None
        sb=int(score_b) if score_b is not None else None
        # Vitórias necessárias dependem do formato: 2 em BO3, 3 em BO5. Sem o
        # formato assume-se BO3 (comportamento histórico). Tratar 2 como
        # decisivo numa MD5 encerrava a série em 2-1, ainda em andamento.
        bo=int(best_of) if best_of else 3
        if bo not in (1,3,5,7):bo=3
        need=bo//2+1
        if sa is not None and sb is not None and max(sa,sb)>=need and sa!=sb:
            return 'completed'
    except Exception:
        pass
    dt=_local_dt_from_iso_v23(start_time) if start_time else None
    if 'progress' in state:
        if dt and dt < now-timedelta(hours=6):
            return 'pending'
        return 'live'
    if dt:
        if dt > now-timedelta(minutes=15):
            return 'upcoming'
        return 'pending'
    # Legacy date-only cache: only tomorrow/future is certainly upcoming.
    day=str(legacy_date or '')[:10]
    if day:
        today=now.date().isoformat()
        if day>today:return 'upcoming'
        if day<today:return 'pending'
        # Same-day date-only data is uncertain. Keep it until mid-afternoon only;
        # after that it cannot be honestly called upcoming.
        return 'upcoming' if now.hour<15 else 'pending'
    return 'unknown'


def v24_schedule_audit():
    now=_now_local_v23(); issues=[]; pending=0
    for r in db_rows('SELECT * FROM upcoming_matches'):
        st=v24_match_state(r.get('start_time'),legacy_date=r.get('date'),now=now)
        if st=='pending':pending+=1
        if st not in ('upcoming','pending'):
            issues.append({'type':'unexpected_upcoming_state','team_a':r.get('team_a'),'team_b':r.get('team_b'),'state':st})
    for r in db_rows('SELECT * FROM riot_events_v10'):
        st=v24_match_state(r.get('start_time'),r.get('state'),r.get('score_a'),r.get('score_b'),
                           now=now,best_of=r.get('match_strategy_count'))
        if st=='pending':pending+=1
    return {'local_now':now.isoformat(),'pending_sync':pending,'issues':issues,'ok':not issues}


TEAM_LOGO_CACHE_DIR = STATIC / "team_icons" / "official"

def _cache_team_logo(code0, remote_url):
    """Baixa e cacheia localmente o escudo oficial de um time; retorna o
    caminho estático local se disponível, senão a URL remota original."""
    try:
        ext = os.path.splitext(urllib.parse.urlparse(remote_url).path)[1].lower()
        if ext not in (".png",".jpg",".jpeg",".webp",".svg"):ext=".png"
        cached = TEAM_LOGO_CACHE_DIR / f"{code0}{ext}"
        if cached.exists() and cached.stat().st_size>0:
            return f"/static/team_icons/official/{code0}{ext}"
        TEAM_LOGO_CACHE_DIR.mkdir(parents=True,exist_ok=True)
        req=urllib.request.Request(remote_url.replace("http://","https://",1),
                                    headers={"User-Agent":"Mozilla/5.0 LCKPredictor/10"})
        with urllib.request.urlopen(req,timeout=8) as r:
            data=r.read()
        if data:
            cached.write_bytes(data)
            return f"/static/team_icons/official/{code0}{ext}"
    except Exception:
        pass
    return remote_url

def v23_team_assets():
    """URLs oficiais dos escudos dos times, com backup local em disco: na
    primeira vez que um time aparece, o escudo é baixado para
    static/team_icons/official/ e passa a ser servido localmente (sem
    depender do CDN externo da Riot em cada carregamento)."""
    out={}
    for row in db_rows("SELECT raw_json FROM riot_events_v10 ORDER BY updated_at DESC"):
        try:ev=json.loads(row.get("raw_json") or "{}")
        except Exception:continue
        teams=((ev.get("match") or {}).get("teams") or [])
        for t in teams:
            code0=canonical(t.get("name")) or canonical(t.get("code")) or t.get("code")
            if code0 not in FULL_NAMES or code0 in out:continue
            image=t.get("image") or t.get("imageUrl") or t.get("logo") or t.get("logoUrl")
            if isinstance(image,dict):
                image=image.get("url") or image.get("href")
            if image:
                out[code0]={"image":_cache_team_logo(code0,image),"source":"Riot LoL Esports"}
    return out


def _saved_or_elo_probability(a,b):
    saved=db_one("""SELECT * FROM current_predictions WHERE
                    (team_a=? AND team_b=?) OR (team_a=? AND team_b=?)
                    ORDER BY date DESC LIMIT 1""",(a,b,b,a))
    if saved:
        p=float(saved["conservative_blend_team_a"])
        return p if saved["team_a"]==a else 1-p, "saved_blend"
    ra=db_one("SELECT elo FROM current_ratings WHERE team=?",(a,))
    rb=db_one("SELECT elo FROM current_ratings WHERE team=?",(b,))
    if not ra or not rb:return .5,"neutral"
    return elo_prob(ra["elo"],rb["elo"]),"elo_live"


def refresh_riot_schedule_v10():
    """Riot schedule becomes schedule truth; cache one page backward and one forward."""
    try:
        payload=riot_get_schedule("en-US",league_id=LCK_LEAGUE_ID)
        schedule=((payload.get("data") or {}).get("schedule") or {})
        pages=[payload]
        older=((schedule.get("pages") or {}).get("older"))
        newer=((schedule.get("pages") or {}).get("newer"))
        # Respectful pagination: only one adjacent page each way every 5 minutes.
        for token in (older,newer):
            if token:
                try: pages.append(riot_get_schedule("en-US",league_id=LCK_LEAGUE_ID,page_token=token))
                except Exception: pass
        all_events={}
        for page in pages:
            for ev in riot_events_from(page):
                eid=_event_id(ev)
                if eid: all_events[eid]=ev
        lck=[e for e in all_events.values() if riot_is_lck_event(e)]
        for ev in lck: store_riot_event(ev)

        today=datetime.now(BRAZIL_TZ).date().isoformat()
        with db_connect() as con:
            for ev in lck:
                state=str(ev.get("state") or "").lower()
                a0,b0=_event_team_info(ev)
                a=match_team_code(a0["name"],a0["code"])
                b=match_team_code(b0["name"],b0["code"])
                day=_local_date_from_iso(ev.get("startTime"))
                if not a or not b or day<today or "complete" in state: continue
                eid=_event_id(ev)
                p,mode=_saved_or_elo_probability(a,b)
                ea=con.execute("SELECT elo FROM current_ratings WHERE team=?",(a,)).fetchone()
                eb=con.execute("SELECT elo FROM current_ratings WHERE team=?",(b,)).fetchone()
                pe=elo_prob(ea[0],eb[0]) if ea and eb else p
                con.execute("""DELETE FROM upcoming_matches WHERE date=?
                               AND ((team_a=? AND team_b=?) OR (team_a=? AND team_b=?))""",
                            (day,a,b,b,a))
                con.execute("""INSERT INTO upcoming_matches
                  (date,team_a,team_b,week,patch,probability_team_a,
                   elo_probability_team_a,prediction_mode,source,start_time,event_id,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (day,a,b,ev.get("blockName"),None,p,pe,mode,
                   "Riot LoL Esports schedule · event "+(eid or ""),
                   ev.get("startTime"),eid,datetime.now(timezone.utc).isoformat()))
            con.commit()
        removed=prune_stale_schedule_v23()
        source_health("Riot schedule","ok",records_seen=len(lck))
        return {"ok":True,"events":len(lck),"pages":len(pages),"stale_rows_removed":removed,
                "local_now":_now_local_v23().isoformat()}
    except Exception as e:
        source_health("Riot schedule","error",e)
        return {"ok":False,"error":f"{type(e).__name__}: {e}"}


def discover_lck_live_event_v10():
    try:
        payload=riot_get_live("en-US")
        events=riot_events_from(payload)
        lck=[e for e in events if riot_is_lck_event(e)]
        for ev in lck:store_riot_event(ev)
        source_health("Riot live discovery","ok",records_seen=len(lck))
        return lck[0] if lck else None
    except Exception as e:
        source_health("Riot live discovery","error",e)
        return None



_CHAMPION_CANON_CACHE=None
def _champ_key_v10(x):
    return re.sub(r"[^a-z0-9]","",str(x or "").lower())

def canonical_champion_v10(x):
    global _CHAMPION_CANON_CACHE
    if not x:return x
    if _CHAMPION_CANON_CACHE is None:
        rows=db_rows("SELECT DISTINCT champion FROM draft_champion_meta WHERE champion IS NOT NULL")
        _CHAMPION_CANON_CACHE={_champ_key_v10(r["champion"]):r["champion"] for r in rows}
        _CHAMPION_CANON_CACHE.update({
          "monkeyking":"Wukong","renata":"Renata Glasc","nunu":"Nunu & Willump",
          "jarvaniv":"Jarvan IV","twistedfate":"Twisted Fate","leesin":"Lee Sin",
          "missfortune":"Miss Fortune","masteryi":"Master Yi","drmundo":"Dr. Mundo",
          "tahmkench":"Tahm Kench","reksai":"Rek'Sai","aurelionsol":"Aurelion Sol",
          "xinzhao":"Xin Zhao","kogmaw":"Kog'Maw","kaisa":"Kai'Sa","ksante":"K'Sante",
          "chogath":"Cho'Gath","khazix":"Kha'Zix","velkoz":"Vel'Koz","belveth":"Bel'Veth"
        })
    return _CHAMPION_CANON_CACHE.get(_champ_key_v10(x),x)

def _roles_for_participants(parts):
    roles=["top","jng","mid","bot","sup"]
    out=[]
    for i,x in enumerate(parts or []):
        y=dict(x)
        role=str(y.get("role") or "").lower()
        if role in {"jungle","jg"}:role="jng"
        if role in {"adc","bottom"}:role="bot"
        if role in {"support"}:role="sup"
        if role not in roles:role=roles[i] if i<len(roles) else role
        y["role"]=role
        if y.get("champion"):
            y["champion_key"]=y.get("champion_key") or y.get("champion")
            y["champion"]=canonical_champion_v10(y.get("champion"))
        out.append(y)
    return out


def _strip_team_prefix_v10(player,team):
    """O feed traz o jogador como 'KT Jiwoo'. As tabelas de maestria guardam só
    'Jiwoo', então removemos o prefixo do time."""
    p=str(player or "").strip()
    if not p:return None
    parts=p.split(" ",1)
    if len(parts)==2 and parts[0].strip().upper()==str(team or "").strip().upper():
        return parts[1].strip()
    return p


def _draft_from_snapshot(snap):
    out={"blue":{},"red":{}}
    for side in ("blue","red"):
        parts=_roles_for_participants((snap.get(side) or {}).get("participants") or [])
        team=canonical((snap.get(side) or {}).get("team")) or (snap.get(side) or {}).get("team")
        out[side]={"team":team,
                   "picks":{p["role"]:p.get("champion") for p in parts if p.get("role") and p.get("champion")},
                   # Escalação real do mapa. O elenco salvo em draft_rosters
                   # envelhece (reservas, troca de titular) e não pode mandar
                   # mais que o jogador que está de fato em quadra.
                   "players":{p["role"]:_strip_team_prefix_v10(p.get("player"),team)
                              for p in parts if p.get("role") and p.get("player")}}
    return out


def _prior_fearless(event_id,game_number):
    used=[]
    rows=db_rows("""SELECT draft_json FROM riot_games_v10
                    WHERE event_id=? AND game_number<? AND draft_json IS NOT NULL
                    ORDER BY game_number""",(str(event_id),int(game_number)))
    for r in rows:
        try:d=json.loads(r["draft_json"])
        except:continue
        for side in ("blue","red"):
            used.extend([x for x in ((d.get(side) or {}).get("picks") or {}).values() if x])
    return sorted(set(used))


def _role_gold(parts):
    return {p.get("role"):int(p.get("gold") or 0) for p in _roles_for_participants(parts) if p.get("role")}


def _fill_game_clock_v10(snap):
    """O feed de livestats da Riot não publica o tempo de jogo — os frames trazem
    só rfc460Timestamp. Derivamos o relógio a partir do primeiro frame que
    guardamos para este mapa. Se o primeiro snapshot já pegou o mapa em
    andamento, o relógio é aproximado e é marcado como tal."""
    if snap.get("game_time_seconds") is not None:return
    gid=str(snap.get("game_id") or "")
    ts=_parse_iso_utc_v10(snap.get("timestamp"))
    if not gid or ts is None:return
    row=db_one("""SELECT MIN(captured_at) AS first_ts, MIN(blue_gold+red_gold) AS min_gold
                  FROM riot_live_snapshots_v10 WHERE game_id=?""",(gid,))
    first=_parse_iso_utc_v10((row or {}).get("first_ts"))
    if first is None:return
    elapsed=(ts-first).total_seconds()
    if elapsed<0:return
    # ~2.5k de ouro por time é o start do mapa; acima disso já perdemos o começo.
    min_gold=(row or {}).get("min_gold")
    approx=min_gold is not None and int(min_gold)>6000
    snap["game_time_seconds"]=elapsed
    snap["game_time_approximate"]=bool(approx)


def _parse_iso_utc_v10(x):
    if not x:return None
    try:
        dt=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def store_riot_snapshot_v10(snap):
    now=datetime.now(timezone.utc).isoformat()
    event_id=str(snap["event_id"]);game_id=str(snap["game_id"]);game_number=int(snap["game_number"])
    b=snap["blue"];r=snap["red"];draft=_draft_from_snapshot(snap)
    state=str(snap.get("game_state") or "")
    with db_connect() as con:
        con.execute("""INSERT OR REPLACE INTO riot_games_v10
          (game_id,event_id,game_number,state,patch,blue_team,red_team,winner,duration_seconds,
           blue_gold,red_gold,blue_kills,red_kills,blue_towers,red_towers,
           blue_dragons,red_dragons,blue_barons,red_barons,blue_inhibitors,red_inhibitors,
           draft_json,final_json,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            game_id,event_id,game_number,state,snap.get("patch"),
            canonical(b.get("team")) or b.get("team"),canonical(r.get("team")) or r.get("team"),None,
            snap.get("game_time_seconds"),b.get("gold"),r.get("gold"),b.get("kills"),r.get("kills"),
            b.get("towers"),r.get("towers"),b.get("dragons"),r.get("dragons"),b.get("barons"),r.get("barons"),
            b.get("inhibitors"),r.get("inhibitors"),
            json.dumps(draft,ensure_ascii=False,separators=(",",":")),
            json.dumps(snap,ensure_ascii=False,separators=(",",":")) if state.lower()=="completed" else None,now
        ))
        for side,team in (("blue",b),("red",r)):
            code=canonical(team.get("team")) or team.get("team")
            for p in _roles_for_participants(team.get("participants") or []):
                con.execute("""INSERT OR REPLACE INTO riot_participants_v10
                  (game_id,participant_id,side,role,team,player,champion,level,kills,deaths,assists,cs,gold,
                   current_health,max_health,items_json,runes_json,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                    game_id,p.get("participant_id"),side,p.get("role"),code,p.get("player"),p.get("champion"),
                    p.get("level"),p.get("kills"),p.get("deaths"),p.get("assists"),p.get("cs"),p.get("gold"),
                    p.get("current_health"),p.get("max_health"),
                    json.dumps(p.get("items") or [],separators=(",",":")),
                    json.dumps(p.get("runes") or [],separators=(",",":")),now
                ))
        captured=snap.get("timestamp") or now
        con.execute("""INSERT OR IGNORE INTO riot_live_snapshots_v10
          (event_id,game_id,game_number,captured_at,game_time_seconds,patch,blue_team,red_team,
           blue_gold,red_gold,blue_kills,red_kills,blue_towers,red_towers,blue_dragons,red_dragons,
           blue_barons,red_barons,blue_inhibitors,red_inhibitors,blue_role_gold_json,red_role_gold_json,normalized_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            event_id,game_id,game_number,captured,snap.get("game_time_seconds"),snap.get("patch"),
            canonical(b.get("team")) or b.get("team"),canonical(r.get("team")) or r.get("team"),
            b.get("gold"),r.get("gold"),b.get("kills"),r.get("kills"),b.get("towers"),r.get("towers"),
            b.get("dragons"),r.get("dragons"),b.get("barons"),r.get("barons"),b.get("inhibitors"),r.get("inhibitors"),
            json.dumps(_role_gold(b.get("participants")),separators=(",",":")),
            json.dumps(_role_gold(r.get("participants")),separators=(",",":")),
            json.dumps(snap,ensure_ascii=False,separators=(",",":"))
        ))
        # Keep the portable database bounded while retaining a substantial training set.
        con.execute("""DELETE FROM riot_live_snapshots_v10 WHERE id IN (
          SELECT id FROM riot_live_snapshots_v10 ORDER BY id DESC LIMIT -1 OFFSET 50000
        )""")
        con.commit()


def _draft_analysis_v10(snap):
    draft=_draft_from_snapshot(snap)
    a=draft["blue"]["team"];b=draft["red"]["team"]
    if a not in FULL_NAMES or b not in FULL_NAMES:return None
    picks_a=draft["blue"]["picks"];picks_b=draft["red"]["picks"]
    if len(picks_a)<5 or len(picks_b)<5:return None
    patch=str(snap.get("patch") or "")
    short=".".join(patch.split(".")[:2]) if patch else None
    try:
        return evaluate_draft({
          "team_a":a,"team_b":b,"side_a":"Blue","patch":short,
          "picks_a":picks_a,"picks_b":picks_b,
          "players_a":draft["blue"].get("players") or {},
          "players_b":draft["red"].get("players") or {},
          "fearless_used":_prior_fearless(snap["event_id"],snap["game_number"])
        })
    except Exception:
        return None


def _logit(p):
    p=min(.995,max(.005,float(p)))
    return math.log(p/(1-p))


def _sigmoid_v10(z):
    return 1/(1+math.exp(-max(-12,min(12,z))))


def live_state_estimate_v10(snap,draft_analysis=None):
    """Explicitly experimental until trained on archived Riot snapshots."""
    b=snap["blue"];r=snap["red"]
    p0=float((draft_analysis or {}).get("draft_game_probability_team_a") or .5)
    t=float(snap.get("game_time_seconds") or 0)
    gd=int(b.get("gold") or 0)-int(r.get("gold") or 0)
    kd=int(b.get("kills") or 0)-int(r.get("kills") or 0)
    td=int(b.get("towers") or 0)-int(r.get("towers") or 0)
    dd=int(b.get("dragons") or 0)-int(r.get("dragons") or 0)
    bd=int(b.get("barons") or 0)-int(r.get("barons") or 0)
    idf=int(b.get("inhibitors") or 0)-int(r.get("inhibitors") or 0)
    bg=_role_gold(b.get("participants"));rg=_role_gold(r.get("participants"))
    diffs={role:bg.get(role,0)-rg.get(role,0) for role in ["top","jng","mid","bot","sup"]}
    positive=sum(1 for v in diffs.values() if v>250)
    negative=sum(1 for v in diffs.values() if v<-250)
    breadth=(positive-negative)/5
    time_factor=.55+.45*min(1,t/1800) if t else .55
    z=_logit(p0)
    z += .82*(gd/4000)*time_factor
    z += .20*td + .08*dd + .42*bd + .50*idf + .025*kd
    z += .16*breadth
    p=_sigmoid_v10(z)
    factors=[]
    if abs(gd)>=1000:factors.append({"factor":"Ouro","side":"blue" if gd>0 else "red","value":gd})
    if abs(td)>=1:factors.append({"factor":"Torres","side":"blue" if td>0 else "red","value":td})
    if abs(bd)>=1:factors.append({"factor":"Baron","side":"blue" if bd>0 else "red","value":bd})
    if breadth:
        factors.append({"factor":"Distribuição por rotas","side":"blue" if breadth>0 else "red",
                        "value":round(breadth,2),"role_gold_diff":diffs})
    return {
      "probability_blue":p,"probability_red":1-p,"baseline_draft_blue":p0,
      "status":"EXPERIMENTAL","calibrated":False,
      "warning":"Estimativa live heurística. Não foi validada em histórico de snapshots; não confundir com o modelo pré-jogo auditado.",
      "features":{"game_time_seconds":t,"gold_diff":gd,"kill_diff":kd,"tower_diff":td,
                  "dragon_diff":dd,"baron_diff":bd,"inhibitor_diff":idf,
                  "role_gold_diff":diffs,"lead_breadth":breadth},
      "factors":factors
    }


def _series_game_prob(series_p,best_of=3):
    """Inverte a probabilidade de série para a probabilidade por mapa. Vale para
    qualquer best-of (BO5 dos playoffs inclusive), não só BO3."""
    need=int(best_of)//2+1
    S=min(.999,max(.001,float(series_p)));lo,hi=0.,1.
    for _ in range(55):
        q=(lo+hi)/2
        v=sum(math.comb(need+l-1,l)*(q**need)*((1-q)**l) for l in range(need))
        if v<S:lo=q
        else:hi=q
    return (lo+hi)/2


def _remaining_series_prob(a,b,q,best_of=3):
    need=int(best_of)//2+1
    if a>=need:return 1.0
    if b>=need:return 0.0
    return q*_remaining_series_prob(a+1,b,q,best_of)+(1-q)*_remaining_series_prob(a,b+1,q,best_of)



def _series_terminal_distribution(a,b,q,team_a,team_b,best_of=3):
    need=int(best_of)//2+1
    if a>=need:return {f"{team_a} {need}–{b}":1.0}
    if b>=need:return {f"{team_b} {need}–{a}":1.0}
    left=_series_terminal_distribution(a+1,b,q,team_a,team_b,best_of)
    right=_series_terminal_distribution(a,b+1,q,team_a,team_b,best_of)
    out={}
    for k,v in left.items():out[k]=out.get(k,0)+q*v
    for k,v in right.items():out[k]=out.get(k,0)+(1-q)*v
    return out

def _series_distribution_with_current(a,b,q,team_a,team_b,current_p=None,best_of=3):
    if current_p is None:
        return _series_terminal_distribution(a,b,q,team_a,team_b,best_of)
    win=_series_terminal_distribution(a+1,b,q,team_a,team_b,best_of)
    lose=_series_terminal_distribution(a,b+1,q,team_a,team_b,best_of)
    out={}
    for k,v in win.items():out[k]=out.get(k,0)+current_p*v
    for k,v in lose.items():out[k]=out.get(k,0)+(1-current_p)*v
    return out


def series_state_v10(snap,draft_analysis=None,live_estimate=None):
    teams=(snap.get("series") or {}).get("teams") or []
    if len(teams)<2:return None
    ta=canonical(teams[0].get("name")) or teams[0].get("code") or teams[0].get("name")
    tb=canonical(teams[1].get("name")) or teams[1].get("code") or teams[1].get("name")
    sa=int(((teams[0].get("result") or {}).get("gameWins")) or 0)
    sb=int(((teams[1].get("result") or {}).get("gameWins")) or 0)
    # O snapshot pode estar em cache de um mapa já encerrado, com o placar da
    # série congelado no valor de antes. A linha do evento é a fonte
    # autoritativa do placar e é atualizada a cada refresh.
    ev_row=db_one("SELECT team_a_code,team_b_code,score_a,score_b FROM riot_events_v10 WHERE event_id=?",
                  (str(snap.get("event_id") or ""),))
    if ev_row and ev_row.get("score_a") is not None and ev_row.get("score_b") is not None:
        ea,eb=ev_row.get("team_a_code"),ev_row.get("team_b_code")
        ra,rb=int(ev_row["score_a"]),int(ev_row["score_b"])
        if canonical(ea)==ta or ea==ta: sa,sb=ra,rb
        elif canonical(eb)==ta or eb==ta: sa,sb=rb,ra
    strategy=(snap.get("series") or {}).get("strategy") or {}
    try:best_of=int(strategy.get("count") or 3)
    except Exception:best_of=3
    if best_of not in (1,3,5,7):best_of=3
    pre=api_match(ta,tb,best_of) if ta in FULL_NAMES and tb in FULL_NAMES else None
    p_series=float((pre or {}).get("probability_team_a") or .5)
    q=_series_game_prob(p_series,best_of)

    game_state=str(snap.get("game_state") or "").lower()
    game_in_progress=("progress" in game_state)
    # O game_state do snapshot congela quando o mapa acaba e o cache continua
    # servindo o último bom. Sem esta trava o mapa encerrado seria contado duas
    # vezes: uma no placar da série e outra como "mapa em andamento".
    # Invariante que não envelhece: o mapa N só está em andamento se N == sa+sb+1.
    try:gnum=int(snap.get("game_number") or 0)
    except Exception:gnum=0
    if gnum and gnum<=(sa+sb):
        game_in_progress=False
    current=None
    current_source=None
    blue=canonical(snap["blue"].get("team")) or snap["blue"].get("team")
    if game_in_progress and live_estimate:
        current=float(live_estimate["probability_blue"])
        if blue!=ta:current=1-current
        current_source="live experimental"
    elif game_in_progress and draft_analysis:
        current=float(draft_analysis["draft_game_probability_team_a"])
        if draft_analysis["team_a"]!=ta:current=1-current
        current_source="draft"

    dist=_series_distribution_with_current(sa,sb,q,ta,tb,current,best_of)
    p=sum(v for k,v in dist.items() if k.startswith(ta+" "))
    outcomes=[{"score":k,"probability":v} for k,v in sorted(dist.items(),key=lambda x:x[1],reverse=True)]
    return {
      "team_a":ta,"team_b":tb,"score_a":sa,"score_b":sb,
      "probability_team_a":p,"probability_team_b":1-p,
      "pregame_series_probability_team_a":p_series,
      "future_game_baseline_team_a":q,
      "uses_experimental_live":current_source=="live experimental",
      "current_game_source":current_source,
      "best_of":best_of,
      "remaining_outcomes":outcomes,
      "note":"Mapa encerrado usa placar real. Mapa em andamento pode usar draft ou overlay live experimental; mapas futuros usam o baseline derivado do modelo pré-série."
    }


def current_cached_snapshot_v10(event_id=None):
    if event_id:
        row=db_one("""SELECT normalized_json FROM riot_live_snapshots_v10
                      WHERE event_id=? ORDER BY id DESC LIMIT 1""",(str(event_id),))
    else:
        row=db_one("SELECT normalized_json FROM riot_live_snapshots_v10 ORDER BY id DESC LIMIT 1")
    if not row:return None
    try:return json.loads(row["normalized_json"])
    except:return None


def live_timeline_v10(game_id,limit=240):
    rows=db_rows("""SELECT captured_at,game_time_seconds,blue_team,red_team,blue_gold,red_gold,
                    blue_kills,red_kills,blue_towers,red_towers,blue_dragons,red_dragons,
                    blue_barons,red_barons,blue_inhibitors,red_inhibitors,
                    blue_role_gold_json,red_role_gold_json
                    FROM riot_live_snapshots_v10 WHERE game_id=?
                    ORDER BY game_time_seconds DESC LIMIT ?""",(str(game_id),int(limit)))
    rows.reverse()
    for r in rows:
        for k in ("blue_role_gold_json","red_role_gold_json"):
            try:r[k[:-5]]=json.loads(r.pop(k) or "{}")
            except:r[k[:-5]]={}
    return rows


def _frame_lag_seconds(snap):
    ts=(snap or {}).get("timestamp")
    try:
        t=datetime.fromisoformat(str(ts).replace("Z","+00:00"))
        return round((datetime.now(timezone.utc)-t).total_seconds(),1)
    except Exception:
        return None


def live_response_v10(event_id=None,force=True):
    snap=None;err=None
    if event_id is None:
        live=discover_lck_live_event_v10()
        event_id=str(live["id"]) if live else None
    if event_id and force:
        try:
            try:
                # V28.1: paginação incremental por cursor — pede só frames novos
                # desde o último poll (mesma frescura do caminho legado, sem
                # re-buscar a janela de 60s inteira a cada 5s).
                snap=riot_fetch_event_live_incremental(event_id,_LIVE_CURSOR)
            except Exception:
                _LIVE_CURSOR.reset()
                snap=riot_fetch_event_live(event_id,60)
            store_riot_snapshot_v10(snap)
            source_health("Riot livestats","ok")
            # Full event details supplies richer streams/team series state for event table.
            try:
                ev=riot_event_from_details(riot_get_event_details(event_id,"en-US"))
                if ev:store_riot_event(ev)
            except Exception:pass
        except Exception as e:
            err=f"{type(e).__name__}: {e}"
            source_health("Riot livestats","error",err)
    if snap is None:
        snap=current_cached_snapshot_v10(event_id)
    if snap is None:
        return {"ok":False,"event_id":event_id,"error":err or "Nenhum snapshot disponível",
                "source_health":db_rows("SELECT * FROM riot_source_health_v10 ORDER BY source")}
    _fill_game_clock_v10(snap)
    draft=_draft_analysis_v10(snap)
    is_completed="complete" in str(snap.get("game_state") or "").lower() or "complete" in str(snap.get("event_state") or "").lower()
    live_est=None if is_completed else live_state_estimate_v10(snap,draft)
    series=series_state_v10(snap,draft,live_est)
    prospective_capture=None;training_capture=None
    try:
        log_series_pregame_v11(snap)
        log_live_predictions_v11(snap,draft,live_est)
        prospective_capture=v19_capture_prospective(snap,draft)
        v19_score_prospective()
        training_capture=v20_capture_live_training(snap,draft)
        v20_score_live_training()
    except Exception:pass
    streams=snap.get("streams") or []
    if not streams and event_id:
        row=db_one("SELECT streams_json FROM riot_events_v10 WHERE event_id=?",(str(event_id),))
        if row:
            try:streams=json.loads(row["streams_json"] or "[]")
            except:streams=[]
    return {
      "ok":True,"event_id":str(snap["event_id"]),"game_id":str(snap["game_id"]),
      "snapshot":snap,"draft_analysis":draft,"live_estimate":live_est,"series_analysis":series,
      "timeline":live_timeline_v10(snap["game_id"],240),
      "validation_capture":prospective_capture,"training_capture":training_capture,
      "streams":streams,
      "previous_games":db_rows("""SELECT game_number,state,patch,blue_team,red_team,winner,duration_seconds,
                                 blue_gold,red_gold,blue_kills,red_kills,draft_json
                                 FROM riot_games_v10 WHERE event_id=? AND game_number<?
                                 ORDER BY game_number""",(str(snap["event_id"]),int(snap["game_number"]))),
      "source_health":db_rows("SELECT * FROM riot_source_health_v10 ORDER BY source"),
      "frame_lag_seconds":_frame_lag_seconds(snap),
      "cached":bool(err),"error":err
    }


def riot_events_api_v10():
    return {
      "live":db_rows("""SELECT * FROM riot_events_v10
                        WHERE lower(state) LIKE '%progress%' ORDER BY start_time"""),
      "upcoming":db_rows("""SELECT * FROM riot_events_v10
                            WHERE lower(state) NOT LIKE '%complete%' AND lower(state) NOT LIKE '%progress%'
                            ORDER BY start_time LIMIT 30"""),
      "recent":db_rows("""SELECT * FROM riot_events_v10
                          WHERE lower(state) LIKE '%complete%' ORDER BY start_time DESC LIMIT 30""")
    }



def _winner_from_event_game(event,game):
    """Best-effort winner resolution from EventDetails game data."""
    teams=(game or {}).get("teams") or []
    for gt in teams:
        result=gt.get("result") or {}
        if str(result.get("outcome") or "").lower() in {"win","winner"}:
            tid=str(gt.get("id") or "")
            for mt in ((event.get("match") or {}).get("teams") or []):
                if tid and str(mt.get("id"))==tid:
                    return canonical(mt.get("name")) or mt.get("code") or mt.get("name")
            return gt.get("name") or gt.get("code")
    # Some payloads expose a winner/team id directly.
    wid=game.get("winner") or game.get("winnerId") or game.get("winningTeam")
    if isinstance(wid,dict): wid=wid.get("id") or wid.get("name")
    if wid:
        for mt in ((event.get("match") or {}).get("teams") or []):
            if str(mt.get("id"))==str(wid) or str(mt.get("name"))==str(wid):
                return canonical(mt.get("name")) or mt.get("code") or mt.get("name")
    return None


def backfill_recent_riot_games_v10(limit_events=4):
    """Cache final draft/stats for recent completed LCK maps without aggressive crawling."""
    rows=db_rows("""SELECT event_id FROM riot_events_v10
                    WHERE lower(state) LIKE '%complete%'
                    ORDER BY start_time DESC LIMIT ?""",(int(limit_events),))
    fetched=0;errors=[]
    for row in rows:
        event_id=str(row["event_id"])
        try:
            ep=riot_get_event_details(event_id,"en-US")
            event=riot_event_from_details(ep)
            if not event: continue
            store_riot_event(event)
            games=((event.get("match") or {}).get("games") or [])
            for game in games:
                gid=game.get("id")
                if not gid:continue
                state=str(game.get("state") or "").lower()
                if "complete" not in state and state!="unneeded":continue
                existing=db_one("SELECT final_json FROM riot_games_v10 WHERE game_id=?",(str(gid),))
                if existing and existing.get("final_json"):continue
                try:
                    snap=riot_fetch_game_snapshot(event_id,gid,0)
                    snap["game_state"]="completed"
                    store_riot_snapshot_v10(snap)
                    winner=_winner_from_event_game(event,game)
                    with db_connect() as con:
                        con.execute("""UPDATE riot_games_v10 SET winner=?,state='completed',
                                      final_json=?,updated_at=? WHERE game_id=?""",
                                    (winner,json.dumps(snap,ensure_ascii=False,separators=(",",":")),
                                     datetime.now(timezone.utc).isoformat(),str(gid)))
                        con.commit()
                    fetched+=1
                except Exception as ge:
                    errors.append(f"{gid}: {type(ge).__name__}: {ge}")
        except Exception as e:
            errors.append(f"{event_id}: {type(e).__name__}: {e}")
    source_health("Riot completed-game backfill","ok" if not errors else "partial",
                  "; ".join(errors[:3]) if errors else None,records_seen=fetched)
    return {"fetched":fetched,"errors":errors}



def apply_completed_riot_series_to_draft_v10(event_id):
    """Advance draft feature state only after the whole series ends.

    This avoids contaminating G2/G3 retrospective probabilities with the result of the
    very map being evaluated. Under Fearless, same-series champion reuse is unavailable
    anyway; the completed series becomes training/state information for future matches.
    """
    event=db_one("SELECT state FROM riot_events_v10 WHERE event_id=?",(str(event_id),))
    if not event or "complete" not in str(event.get("state") or "").lower():return 0
    games=db_rows("""SELECT game_id,winner FROM riot_games_v10
                     WHERE event_id=? AND lower(state) LIKE '%complete%' AND winner IS NOT NULL
                     ORDER BY game_number""",(str(event_id),))
    applied=0
    with db_connect() as con:
        for g in games:
            gid=str(g["game_id"])
            if con.execute("SELECT 1 FROM riot_draft_applied_v10 WHERE game_id=?",(gid,)).fetchone():continue
            winner=canonical(g["winner"]) or g["winner"]
            parts=[dict(r) for r in con.execute("""SELECT side,role,team,player,champion,kills,deaths,assists
                                                   FROM riot_participants_v10 WHERE game_id=?
                                                   ORDER BY participant_id""",(gid,)).fetchall()]
            if len(parts)<10:continue
            # player overall + player×champion + descriptive champion meta
            for x in parts:
                player=x["player"];champ=canonical_champion_v10(x["champion"]);role=x["role"]
                team=canonical(x["team"]) or x["team"]
                y=1 if team==winner else 0
                prow=con.execute("SELECT wins,games FROM draft_player_overall WHERE player=?",(player,)).fetchone()
                if prow:
                    w,n=float(prow[0])+y,int(prow[1])+1
                    con.execute("UPDATE draft_player_overall SET wins=?,games=?,player_prior=? WHERE player=?",
                                (w,n,(w+2)/(n+4),player))
                else:
                    con.execute("INSERT INTO draft_player_overall(player,wins,games,player_prior) VALUES(?,?,?,?)",
                                (player,y,1,(y+2)/5))
                pc=con.execute("""SELECT rowid,games,wins FROM draft_player_champion
                                  WHERE scope='local_2025_2026' AND player=? AND champion=?
                                  ORDER BY games DESC LIMIT 1""",(player,champ)).fetchone()
                if pc:
                    rowid,n0,w0=pc;n=int(n0)+1;w=float(w0)+y
                    con.execute("""UPDATE draft_player_champion SET games=?,wins=?,winrate=?,smoothed_winrate=?
                                   WHERE rowid=?""",(n,w,w/n,(w+2)/(n+4),rowid))
                else:
                    deaths=max(1,int(x.get("deaths") or 0));kda=((int(x.get("kills") or 0)+int(x.get("assists") or 0))/deaths)
                    con.execute("""INSERT INTO draft_player_champion
                      (scope,player,team,role,champion,games,wins,winrate,smoothed_winrate,kda,gd15,xpd15,csd15,dpm)
                      VALUES('local_2025_2026',?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)""",
                      (player,team,role,champ,1,y,float(y),(y+2)/5,kda))
                cm=con.execute("""SELECT rowid,games,wins FROM draft_champion_meta
                                  WHERE scope='2026' AND role=? AND champion=? LIMIT 1""",(role,champ)).fetchone()
                if cm:
                    rowid,n0,w0=cm;n=int(n0)+1;w=float(w0)+y
                    con.execute("UPDATE draft_champion_meta SET games=?,wins=?,winrate=?,smoothed_winrate=? WHERE rowid=?",
                                (n,w,w/n,(w+5)/(n+10),rowid))
                else:
                    con.execute("""INSERT INTO draft_champion_meta(scope,role,champion,games,wins,winrate,smoothed_winrate,gd15)
                                   VALUES('2026',?,?,?,?,?,?,NULL)""",(role,champ,1,y,float(y),(y+5)/11))
            # pair synergy, per team
            for team in sorted(set((canonical(x["team"]) or x["team"]) for x in parts)):
                champs=sorted(canonical_champion_v10(x["champion"]) for x in parts if (canonical(x["team"]) or x["team"])==team)
                y=1 if team==winner else 0
                for i in range(len(champs)):
                    for j in range(i+1,len(champs)):
                        a,b=sorted((champs[i],champs[j]))
                        sr=con.execute("SELECT games,wins FROM draft_synergy WHERE champion_a=? AND champion_b=?",(a,b)).fetchone()
                        if sr:
                            n=int(sr[0])+1;w=int(sr[1])+y
                            con.execute("UPDATE draft_synergy SET games=?,wins=?,winrate=?,smoothed_winrate=? WHERE champion_a=? AND champion_b=?",
                                        (n,w,w/n,(w+2)/(n+4),a,b))
                        else:
                            con.execute("INSERT INTO draft_synergy(champion_a,champion_b,games,wins,winrate,smoothed_winrate) VALUES(?,?,?,?,?,?)",
                                        (a,b,1,y,float(y),(y+2)/5))
            con.execute("INSERT INTO riot_draft_applied_v10(game_id,event_id,applied_at,note) VALUES(?,?,?,?)",
                        (gid,str(event_id),datetime.now(timezone.utc).isoformat(),"Applied after series completion"))
            applied+=1
        con.commit()
    return applied


def archive_completed_series_v10():
    """Import completed Riot series results into the Elo history once, with provenance."""
    events=db_rows("""SELECT * FROM riot_events_v10 WHERE lower(state) LIKE '%complete%'
                      AND score_a IS NOT NULL AND score_b IS NOT NULL""")
    added=0
    with db_connect() as con:
        existing={r[0] for r in con.execute("SELECT series_key FROM series_history")}
        for ev in events:
            a,b=canonical(ev["team_a"]),canonical(ev["team_b"])
            if not a or not b or int(ev["score_a"])==int(ev["score_b"]):continue
            day=_local_date_from_iso(ev["start_time"])
            teams=sorted([a,b]);key=f"{day}__{'|'.join(teams)}"
            if key in existing:continue
            wins={a:int(ev["score_a"]),b:int(ev["score_b"])}
            winner=a if wins[a]>wins[b] else b
            con.execute("""INSERT INTO series_history
              (series_key,date,day,year,team1,team2,winner,wins1,wins2,n_games,source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (key,day+" 08:00:00",day,int(day[:4]),teams[0],teams[1],winner,
               wins[teams[0]],wins[teams[1]],wins[a]+wins[b],"Riot LoL Esports event "+ev["event_id"]))
            existing.add(key);added+=1
        if added:recalc_ratings(con)
        con.commit()
    for ev in events:
        try:apply_completed_riot_series_to_draft_v10(ev["event_id"])
        except Exception:pass
    return added

def try_auto_update():
    """Best effort only. Never prevents the app from starting."""
    try:
        req=urllib.request.Request(UPDATE_URL,headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/Portable"
        })
        with urllib.request.urlopen(req,timeout=12) as r:
            raw=r.read().decode("utf-8","replace")
        p=TableParser(); p.feed(raw)
        completed=[]
        for c in p.rows:
            if len(c)<7: continue
            a,b=canonical(c[1]),canonical(c[3])
            score=c[2].strip()
            d=c[6][:10]
            if not a or not b or len(d)!=10: continue
            import re
            m=re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*",score)
            if not m: continue
            sa,sb=map(int,m.groups())
            if sa==sb: continue
            completed.append((d,a,b,sa,sb))
        if not completed: return
        with db_connect() as con:
            existing={r[0] for r in con.execute("SELECT series_key FROM series_history")}
            added=0
            for d,a,b,sa,sb in completed:
                teams=sorted([a,b]); wins={a:sa,b:sb}; key=f"{d}__{'|'.join(teams)}"
                if key in existing: continue
                row=(key,f"{d} 08:00:00",d,int(d[:4]),teams[0],teams[1],
                     a if sa>sb else b,wins[teams[0]],wins[teams[1]],sa+sb,
                     "Games of Legends portable auto update")
                con.execute("""INSERT INTO series_history
                    (series_key,date,day,year,team1,team2,winner,wins1,wins2,n_games,source)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",row)
                existing.add(key); added+=1
            if added:
                recalc_ratings(con)
            con.commit()
    except Exception as e:
        # Intentionally silent: the app must remain usable offline.
        pass


def recalc_ratings(con):
    rows=con.execute("""SELECT date,year,team1,team2,winner FROM series_history
                        ORDER BY date,series_key""").fetchall()
    elo=defaultdict(lambda:BASE_ELO)
    hist=defaultdict(lambda:deque(maxlen=20))
    cy=None
    for d,yr,t1,t2,winner in rows:
        yr=int(yr)
        if cy is None: cy=yr
        elif yr!=cy:
            for t in list(elo.keys()):
                elo[t]=BASE_ELO+SEASON_DECAY*(elo[t]-BASE_ELO)
            cy=yr
        y=1 if winner==t1 else 0
        p=elo_prob(elo[t1],elo[t2])
        delta=ELO_K*(y-p)
        elo[t1]+=delta; elo[t2]-=delta
        hist[t1].append(y); hist[t2].append(1-y)
    latest=con.execute("SELECT MAX(day) FROM series_history").fetchone()[0]
    advrow=con.execute("SELECT value FROM metadata WHERE key='oracle_2026_cutoff'").fetchone()
    adv=advrow[0] if advrow else ""
    out=[]
    for t,name in FULL_NAMES.items():
        h=list(hist[t])
        w5=sum(h[-5:])/len(h[-5:]) if h[-5:] else None
        w10=sum(h[-10:])/len(h[-10:]) if h[-10:] else None
        out.append((t,name,float(elo[t]),w5,w10,adv,latest))
    out.sort(key=lambda x:x[2],reverse=True)
    con.execute("DELETE FROM current_ratings")
    for rank,r in enumerate(out,1):
        con.execute("""INSERT INTO current_ratings
            (team,full_name,elo,series_winrate_last5,series_winrate_last10,
             advanced_stats_cutoff,result_updates_cutoff,rank)
             VALUES(?,?,?,?,?,?,?,?)""",(*r,rank))
    con.execute("DELETE FROM metadata WHERE key='web_result_update_cutoff'")
    con.execute("INSERT INTO metadata(key,value) VALUES('web_result_update_cutoff',?)",(latest,))


def draft_bootstrap():
    rosters=db_rows("SELECT * FROM draft_rosters ORDER BY team, CASE role WHEN 'top' THEN 1 WHEN 'jng' THEN 2 WHEN 'mid' THEN 3 WHEN 'bot' THEN 4 WHEN 'sup' THEN 5 END")
    champions=[r["champion"] for r in db_rows("SELECT DISTINCT champion FROM draft_champion_meta ORDER BY champion")]
    validation=db_rows("SELECT * FROM draft_validation_v6")
    sources=db_rows("SELECT * FROM draft_data_sources")
    global_meta=db_rows("SELECT * FROM draft_global_meta_sources")
    # Top 8 2026 champions per current player, useful for fast draft entry.
    pools={}
    for r in rosters:
        p=r["player"]
        rows=db_rows("""SELECT champion,games,winrate,smoothed_winrate,gd15,kda
                        FROM draft_player_champion
                        WHERE scope='2026' AND player=?
                        ORDER BY games DESC,winrate DESC LIMIT 8""",(p,))
        pools[p]=rows
    return {"rosters":rosters,"champions":champions,"validation":validation,"sources":sources,
            "global_meta":global_meta,"pools":pools}


def _sigmoid(z):
    if z>=0:
        e=math.exp(-z); return 1/(1+e)
    e=math.exp(z); return e/(1+e)


def _draft_model_probability(elo_diff,mastery_diff,synergy_diff):
    cfg=db_one("SELECT * FROM draft_model_config_v8 LIMIT 1")
    med=json.loads(cfg["medians_json"]); means=json.loads(cfg["means_json"])
    scales=json.loads(cfg["scales_json"]); coef=json.loads(cfg["coef_json"])
    vals=[elo_diff,mastery_diff,synergy_diff]
    vals=[med[i] if vals[i] is None else float(vals[i]) for i in range(3)]
    z=float(cfg["intercept"])
    for i,v in enumerate(vals):
        z += coef[i]*((v-means[i])/scales[i])
    return _sigmoid(z)


def _pc(player,champion,scope="local_2025_2026"):
    """Maestria do jogador no campeão. O mesmo jogador aparece em linhas
    separadas por time (quem trocou de equipe tem histórico dividido), então
    somamos os jogos: a experiência no campeão é dele, não do time. Métricas de
    taxa entram como média ponderada por jogos."""
    if not champion: return None
    row=db_one("""SELECT player,champion,role,
                         SUM(games) AS games, SUM(wins) AS wins,
                         SUM(kda*games)/NULLIF(SUM(games),0)  AS kda,
                         SUM(gd15*games)/NULLIF(SUM(games),0) AS gd15,
                         SUM(xpd15*games)/NULLIF(SUM(games),0) AS xpd15,
                         SUM(csd15*games)/NULLIF(SUM(games),0) AS csd15,
                         SUM(dpm*games)/NULLIF(SUM(games),0)  AS dpm,
                         GROUP_CONCAT(DISTINCT team) AS teams
                  FROM draft_player_champion
                  WHERE scope=? AND player=? AND champion=?""",(scope,player,champion))
    if not row or not row.get("games"): return None
    g=float(row["games"]); w=float(row["wins"] or 0)
    row["scope"]=scope
    row["winrate"]=w/g if g else None
    row["smoothed_winrate"]=(w+2)/(g+4) if g else None
    return row


def _player_prior(player):
    row=db_one("SELECT * FROM draft_player_overall WHERE player=? LIMIT 1",(player,))
    return float(row["player_prior"]) if row else .5


def _eb_mastery(player,pcrow,strength=32.0):
    prior=_player_prior(player)
    if not pcrow: return prior,0,prior*strength,(1-prior)*strength
    n=float(pcrow["games"]); w=float(pcrow["wins"])
    alpha=w+strength*prior
    beta=(n-w)+strength*(1-prior)
    return alpha/(alpha+beta),n,alpha,beta


def _career_pc(player,champion,scope="career"):
    if not champion: return None
    return db_one("""SELECT * FROM draft_player_champion_web
                     WHERE player=? AND champion=? AND scope=? LIMIT 1""",(player,champion,scope))


def _current_form(player):
    return db_one("SELECT * FROM draft_current_lck_player_form WHERE player=? LIMIT 1",(player,))


def _meta(role,champion):
    if not champion: return None
    return db_one("""SELECT * FROM draft_champion_meta
                     WHERE scope='2026' AND role=? AND champion=? LIMIT 1""",(role,champion))


def _syn(a,b):
    if not a or not b: return None
    x,y=sorted([a,b])
    return db_one("SELECT * FROM draft_synergy WHERE champion_a=? AND champion_b=? LIMIT 1",(x,y))


def _counter(role,a,b):
    if not a or not b: return None
    return db_one("""SELECT * FROM draft_counter
                     WHERE role=? AND champion_a=? AND champion_b=? LIMIT 1""",(role,a,b))


def _percentile(vals,q):
    vals=sorted(vals)
    if not vals: return None
    pos=(len(vals)-1)*q
    lo=int(pos); hi=min(len(vals)-1,lo+1)
    f=pos-lo
    return vals[lo]*(1-f)+vals[hi]*f


class RichTableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.in_tr=False; self.in_td=False; self.cur=[]; self.buf=[]
    def handle_starttag(self,tag,attrs):
        if tag=="tr":
            self.in_tr=True; self.cur=[]
        elif tag=="td" and self.in_tr:
            self.in_td=True; self.buf=[]
        elif tag=="img" and self.in_td:
            alt=dict(attrs).get("alt")
            if alt: self.buf.append(alt+" ")
    def handle_data(self,data):
        if self.in_td: self.buf.append(data)
    def handle_endtag(self,tag):
        if tag=="td" and self.in_td:
            self.cur.append(" ".join("".join(self.buf).replace("\xa0"," ").split())); self.in_td=False
        elif tag=="tr" and self.in_tr:
            if self.cur:self.rows.append(self.cur)
            self.in_tr=False


GOL_PLAYER_IDS={"ShowMaker":1250,"Siwoo":5392,"Smash":4940,"Career":5204,"Lucid":3895,
                "Zeus":3658,"Kanavi":2360,"Zeka":2906,"Gumayusi":3247,"Delight":3411}
CURRENT_PLAYERS_URL="https://gol.gg/players/list/season-ALL/split-ALL/tournament-LCK%202026%20Rounds%203-4/"
GLOBAL_META_URLS={
    "LCK 2026 Rounds 3-4":"https://gol.gg/tournament/tournament-picksandbans/LCK%202026%20Rounds%203-4/",
    "LPL 2026 Split 2":"https://gol.gg/tournament/tournament-picksandbans/LPL%202026%20Split%202/",
    "LPL 2026 Split 3":"https://gol.gg/tournament/tournament-picksandbans/LPL%202026%20Split%203/",
    "LCK CL 2026 Rounds 3-4":"https://gol.gg/tournament/tournament-picksandbans/LCK%20CL%202026%20Rounds%203-4/",
}


def _fetch(url,timeout=12):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCKPredictor/6.0"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8","replace")


def _parse_pct(x):
    m=re.search(r"(-?\d+(?:\.\d+)?)\s*%",x or "")
    return float(m.group(1))/100 if m else None


def _parse_num(x):
    try:return float(str(x).strip())
    except:return None


def refresh_draft_web_cache():
    result={"ok":True,"updated":[],"errors":[]}
    now=datetime.now(timezone.utc).isoformat()
    # 1) Current LCK player form in one request.
    try:
        raw=_fetch(CURRENT_PLAYERS_URL); p=RichTableParser(); p.feed(raw)
        with db_connect() as con:
            for c in p.rows:
                if len(c)<22 or c[0] not in GOL_PLAYER_IDS: continue
                games=int(float(c[2])); wr=_parse_pct(c[3]); kda=_parse_num(c[4])
                dpm=_parse_num(c[14]); gd=_parse_num(c[19]); csd=_parse_num(c[20]); xpd=_parse_num(c[21])
                teamrow=con.execute("SELECT team FROM draft_rosters WHERE player=? LIMIT 1",(c[0],)).fetchone()
                team=teamrow[0] if teamrow else ""
                con.execute("DELETE FROM draft_current_lck_player_form WHERE player=?",(c[0],))
                con.execute("""INSERT INTO draft_current_lck_player_form
                    (player,team,games,winrate,kda,gd15,csd15,xpd15,dpm,scope,snapshot_date,source_url)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c[0],team,games,wr,kda,gd,csd,xpd,dpm,"LCK 2026 Rounds 3-4",now[:10],CURRENT_PLAYERS_URL))
            con.commit()
        result["updated"].append("current_lck_player_form")
    except Exception as e:
        result["errors"].append("current_form: "+str(e))

    # 2) S16 champion pools for the 10 DK/HLE players.
    for player,pid in GOL_PLAYER_IDS.items():
        try:
            url=f"https://gol.gg/players/player-stats/{pid}/season-S16/split-ALL/tournament-ALL/champion-ALL/"
            raw=_fetch(url); p=RichTableParser(); p.feed(raw)
            parsed=[]
            for c in p.rows:
                if len(c)<4: continue
                try: games=int(float(c[1]))
                except: continue
                wr=_parse_pct(c[2]); kda=_parse_num(c[3])
                if c[0] and wr is not None:
                    parsed.append((c[0],games,wr,kda))
            if parsed:
                with db_connect() as con:
                    con.execute("DELETE FROM draft_player_champion_web WHERE player=? AND scope='S16'",(player,))
                    for champ,games,wr,kda in parsed:
                        con.execute("""INSERT INTO draft_player_champion_web
                            (player,champion,games,winrate,kda,scope,snapshot_date,gol_player_id,source_url)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                            (player,champ,games,wr,kda,"S16",now[:10],pid,url))
                    con.commit()
                result["updated"].append("S16:"+player)
        except Exception as e:
            result["errors"].append(player+": "+str(e))

    # 3) Coverage counts for external meta sources.
    for tournament,url in GLOBAL_META_URLS.items():
        try:
            raw=_fetch(url); txt=re.sub(r"<[^>]+>"," ",raw); txt=" ".join(txt.split())
            m=re.search(r"Total\s*:\s*(\d+)",txt)
            if m:
                with db_connect() as con:
                    con.execute("""UPDATE draft_global_meta_sources
                                   SET champions_in_pickban=?,snapshot_date=?
                                   WHERE tournament=?""",(int(m.group(1)),now[:10],tournament))
                    con.commit()
        except Exception as e:
            result["errors"].append(tournament+": "+str(e))
    result["ok"]=not bool(result["errors"])
    return result


def patch_bootstrap():
    return {
        "patches":db_rows("""SELECT year,patch,games,avg_game_minutes,avg_kills_per_team,
                            avg_dragons_per_team,avg_barons_per_team,avg_towers_per_team
                            FROM patch_summary ORDER BY year DESC,patch DESC"""),
        "external":db_rows("SELECT * FROM patch_external_state"),
        "validation":db_rows("SELECT * FROM patch_validation_v7"),
        "config":db_one("SELECT * FROM patch_model_config_v7 LIMIT 1")
    }


def patch_detail(patch):
    try:p=float(patch)
    except:return {"error":"Patch inválido"}
    return {
        "patch":p,
        "summary":db_one("SELECT * FROM patch_summary WHERE patch=? ORDER BY year DESC LIMIT 1",(p,)),
        "champions":db_rows("""SELECT position,champion,games,winrate,smoothed_winrate,gd15,xpd15,csd15,dpm
                              FROM patch_champion_meta WHERE patch=?
                              ORDER BY games DESC,winrate DESC LIMIT 100""",(p,)),
        "teams":db_rows("""SELECT team,games,winrate,gd15,xpd15,csd15,dpm,dragons,barons,towers
                           FROM patch_team_performance WHERE patch=?
                           ORDER BY winrate DESC,games DESC""",(p,))
    }


def _patch_context_for_pick(patch,role,player,champion):
    if not patch or not champion:return {"champion":None,"player":None}
    try:p=float(patch)
    except:return {"champion":None,"player":None}
    champ=db_one("""SELECT * FROM patch_champion_meta
                    WHERE patch=? AND position=? AND champion=? ORDER BY year DESC LIMIT 1""",(p,role,champion))
    pc=db_one("""SELECT * FROM patch_player_champion
                 WHERE patch=? AND role=? AND player=? AND champion=? ORDER BY year DESC LIMIT 1""",(p,role,player,champion))
    return {"champion":champ,"player":pc}

def _patch_model_probability(values):
    cfg=db_one("SELECT * FROM patch_model_config_v7 LIMIT 1")
    if not cfg or not int(cfg["promoted"]):
        return None
    features=json.loads(cfg["features_json"])
    med=json.loads(cfg["medians_json"]); means=json.loads(cfg["means_json"])
    scales=json.loads(cfg["scales_json"]); coef=json.loads(cfg["coef_json"])
    z=float(cfg["intercept"])
    for i,name in enumerate(features):
        v=values.get(name)
        if v is None:v=med[i]
        z += coef[i]*((float(v)-means[i])/scales[i])
    return _sigmoid(z)


def _global_champion_prior(role,champion):
    r=db_one("""SELECT wins,games FROM draft_champion_meta
                WHERE scope='local_2025_2026' AND role=? AND champion=? LIMIT 1""",(role,champion))
    if not r:return .5
    return (float(r["wins"])+5)/(float(r["games"])+10)


def _team_game_prior(team):
    r=db_one(f"SELECT SUM(result) wins,COUNT(*) games FROM team_games WHERE team=?{LG_SQL}",
             (team,)+LG_ARGS)
    if not r or not r["games"]:return .5
    return (float(r["wins"])+5)/(float(r["games"])+10)


def _live_patch_features(patch,team_a,team_b,side_a,picks_a,picks_b,ros_a,ros_b,mastery_diff,synergy_diff,elo_diff):
    if patch in (None,"","auto"):return None
    try:p=float(patch)
    except:return None
    cfg=db_one("SELECT * FROM patch_model_config_v7 LIMIT 1")
    if not cfg or not int(cfg["promoted"]):return None
    champK=float(cfg["champ_patch_prior_strength"])
    pcK=float(cfg["player_champ_patch_prior_strength"])
    teamK=10.0
    roles=["top","jng","mid","bot","sup"]
    patch_meta_a=[];patch_meta_b=[];patch_master_a=[];patch_master_b=[]
    coverage=[]
    for role in roles:
        for team_side,picks,ros,out_meta,out_master in [
            ("a",picks_a,ros_a,patch_meta_a,patch_master_a),
            ("b",picks_b,ros_b,patch_meta_b,patch_master_b)]:
            ch=picks.get(role) or ""; pl=ros.get(role)
            # Empty pick contributes neutral; it must not create fake patch confidence.
            if not ch:
                out_meta.append(.5);out_master.append(.5);continue
            gprior=_global_champion_prior(role,ch)
            pr=db_one("""SELECT games,wins FROM patch_champion_meta
                         WHERE patch=? AND position=? AND champion=?
                         ORDER BY year DESC LIMIT 1""",(p,role,ch))
            if pr:
                n=float(pr["games"]);w=float(pr["wins"])
                out_meta.append((w+champK*gprior)/(n+champK));coverage.append(min(n,12)/12)
            else:
                out_meta.append(gprior);coverage.append(0)
            pcr=_pc(pl,ch)
            base_master,_n,_a,_b=_eb_mastery(pl,pcr)
            rr=db_one("""SELECT games,wins FROM patch_player_champion
                         WHERE patch=? AND role=? AND player=? AND champion=?
                         ORDER BY year DESC LIMIT 1""",(p,role,pl,ch))
            if rr:
                n=float(rr["games"]);w=float(rr["wins"])
                out_master.append((w+pcK*base_master)/(n+pcK));coverage.append(min(n,8)/8)
            else:
                out_master.append(base_master);coverage.append(0)
    def team_patch(team):
        base=_team_game_prior(team)
        r=db_one("""SELECT games,wins FROM patch_team_performance
                    WHERE patch=? AND team=? ORDER BY year DESC LIMIT 1""",(p,team))
        if not r:return base,0
        n=float(r["games"]);w=float(r["wins"])
        return (w+teamK*base)/(n+teamK),min(n,10)/10
    ta,tca=team_patch(team_a);tb,tcb=team_patch(team_b)
    coverage.extend([tca,tcb])
    # Orient all model features Blue - Red, exactly as in training.
    values={
        "elo_diff":elo_diff,
        "mastery_eb_diff":mastery_diff,
        "synergy_diff":synergy_diff,
        "patch_champion_meta_diff":sum(patch_meta_a)/5-sum(patch_meta_b)/5,
        "patch_player_mastery_diff":sum(patch_master_a)/5-sum(patch_master_b)/5,
        "team_patch_adaptation_diff":ta-tb
    }
    if side_a!="Blue":
        values={k:-v for k,v in values.items()}
    # Require at least some actual same-patch evidence; otherwise use V6.
    cov=sum(coverage)/len(coverage) if coverage else 0
    if cov<=0:
        return {"active":False,"coverage":0,"patch":p,"reason":"No exact-patch local sample"}
    pblue=_patch_model_probability(values)
    pa=pblue if side_a=="Blue" else 1-pblue
    return {"active":True,"coverage":cov,"patch":p,"probability_team_a":pa,"features":values}


def evaluate_draft(payload):
    a=str(payload.get("team_a","DK")).upper(); b=str(payload.get("team_b","HLE")).upper()
    side_a=str(payload.get("side_a","Blue")).title()
    picks_a=payload.get("picks_a") or {}; picks_b=payload.get("picks_b") or {}
    fearless=[str(x).strip().lower() for x in (payload.get("fearless_used") or []) if str(x).strip()]
    ra=db_one("SELECT * FROM current_ratings WHERE team=?",(a,)); rb=db_one("SELECT * FROM current_ratings WHERE team=?",(b,))
    if not ra or not rb:return {"error":"Equipe não encontrada."}
    # Historical/regression evaluations may freeze the rating state explicitly.
    # This prevents a past draft regression from changing merely because current Elo advanced.
    rating_override=payload.get("rating_override") or {}
    elo_a=float(rating_override.get(a,ra["elo"]))
    elo_b=float(rating_override.get(b,rb["elo"]))
    ros_a={r["role"]:r["player"] for r in db_rows("SELECT role,player FROM draft_rosters WHERE team=?",(a,))}
    ros_b={r["role"]:r["player"] for r in db_rows("SELECT role,player FROM draft_rosters WHERE team=?",(b,))}
    # Quando a escalação real do mapa é conhecida (feed ao vivo), ela prevalece
    # sobre o elenco salvo, que envelhece a cada troca de titular/reserva.
    ros_a={**ros_a,**{k:v for k,v in (payload.get("players_a") or {}).items() if v}}
    ros_b={**ros_b,**{k:v for k,v in (payload.get("players_b") or {}).items() if v}}
    roles=["top","jng","mid","bot","sup"]; detail=[]; illegal=[]
    ma=[];mb=[]; posterior_a=[];posterior_b=[]; mastery_cov=[]; career_cov=[]; s16_cov=[]; counter_cov=[]
    current_forms=[]
    for role in roles:
        ca=picks_a.get(role) or ""; cb=picks_b.get(role) or ""
        pa=ros_a.get(role); pb=ros_b.get(role)
        if ca and ca.lower() in fearless:illegal.append(ca)
        if cb and cb.lower() in fearless:illegal.append(cb)
        pca=_pc(pa,ca); pcb=_pc(pb,cb)
        va,na,aa,ba=_eb_mastery(pa,pca); vb,nb,ab,bb=_eb_mastery(pb,pcb)
        ma.append(va if ca else .5); mb.append(vb if cb else .5)
        posterior_a.append((aa,ba) if ca else None); posterior_b.append((ab,bb) if cb else None)
        if ca:mastery_cov.append(min(na,12)/12)
        if cb:mastery_cov.append(min(nb,12)/12)
        car_a=_career_pc(pa,ca,"career"); car_b=_career_pc(pb,cb,"career")
        s16_a=_career_pc(pa,ca,"S16"); s16_b=_career_pc(pb,cb,"S16")
        if ca:career_cov.append(1 if car_a else 0); s16_cov.append(1 if s16_a else 0)
        if cb:career_cov.append(1 if car_b else 0); s16_cov.append(1 if s16_b else 0)
        cnt=_counter(role,ca,cb)
        if ca and cb:counter_cov.append(min((cnt["games"] if cnt else 0),6)/6)
        fa=_current_form(pa); fb=_current_form(pb)
        if fa:current_forms.append(("a",float(fa["winrate"])))
        if fb:current_forms.append(("b",float(fb["winrate"])))
        requested_patch=payload.get("patch")
        pctx_a=_patch_context_for_pick(requested_patch,role,pa,ca)
        pctx_b=_patch_context_for_pick(requested_patch,role,pb,cb)
        detail.append({"role":role,"team_a_player":pa,"team_b_player":pb,
            "team_a_champion":ca,"team_b_champion":cb,
            "team_a_patch_context":pctx_a,"team_b_patch_context":pctx_b,
            "team_a_mastery":pca,"team_b_mastery":pcb,
            "team_a_mastery_eb":va,"team_b_mastery_eb":vb,
            "team_a_career":car_a,"team_b_career":car_b,
            "team_a_s16":s16_a,"team_b_s16":s16_b,
            "team_a_current_form":fa,"team_b_current_form":fb,
            "team_a_meta":_meta(role,ca),"team_b_meta":_meta(role,cb),
            "counter_a_vs_b":cnt})

    def team_synergy(picks):
        cs=[picks.get(r) for r in roles if picks.get(r)]; vals=[]; cov=[]; post=[]
        for i in range(len(cs)):
            for j in range(i+1,len(cs)):
                s=_syn(cs[i],cs[j])
                if s:
                    w=float(s["wins"]); n=float(s["games"]); alpha=w+2; beta=n-w+2
                    vals.append(alpha/(alpha+beta)); cov.append(min(n,12)/12); post.append((alpha,beta))
                else:
                    vals.append(.5); cov.append(0); post.append((2,2))
        return (sum(vals)/len(vals) if vals else .5,sum(cov)/len(cov) if cov else 0,post)
    sa,sca,post_sa=team_synergy(picks_a); sb,scb,post_sb=team_synergy(picks_b)
    mastery_diff=sum(ma)/5-sum(mb)/5; synergy_diff=sa-sb
    if side_a=="Blue":
        elo_diff=elo_a-elo_b; p_a=_draft_model_probability(elo_diff,mastery_diff,synergy_diff)
        base_a=_draft_model_probability(elo_diff,0,0)
    else:
        elo_diff=elo_b-elo_a; p_a=1-_draft_model_probability(elo_diff,-mastery_diff,-synergy_diff)
        base_a=1-_draft_model_probability(elo_diff,0,0)

    patch_eval=_live_patch_features(payload.get("patch"),a,b,side_a,picks_a,picks_b,ros_a,ros_b,
                                    mastery_diff,synergy_diff,elo_diff)
    v6_probability_team_a=p_a
    # V8 audit: patch overlay is experimental/context only after failing the one-time 2026 external test.
    if patch_eval and patch_eval.get("active"):
        patch_eval["experimental_probability_team_a"]=patch_eval.get("probability_team_a")
        patch_eval["production_weight"]=0.0

    # Posterior simulation: uncertainty from player×champion and synergy samples.
    sims=[]
    for _ in range(350):
        sma=[];smb=[]
        for x in posterior_a:sma.append(random.betavariate(x[0],x[1]) if x else .5)
        for x in posterior_b:smb.append(random.betavariate(x[0],x[1]) if x else .5)
        def syn_draw(posts):
            return sum(random.betavariate(x[0],x[1]) for x in posts)/len(posts) if posts else .5
        ssa=syn_draw(post_sa); ssb=syn_draw(post_sb)
        md=sum(sma)/5-sum(smb)/5; sd=ssa-ssb
        if side_a=="Blue": sims.append(_draft_model_probability(elo_diff,md,sd))
        else: sims.append(1-_draft_model_probability(elo_diff,-md,-sd))
    low=_percentile(sims,.10); high=_percentile(sims,.90)
    width=(high-low) if low is not None else .30

    selected=sum(bool(picks_a.get(r)) for r in roles)+sum(bool(picks_b.get(r)) for r in roles)
    completeness=selected/10
    mcov=sum(mastery_cov)/len(mastery_cov) if mastery_cov else 0
    sycov=(sca+scb)/2
    ccov=sum(counter_cov)/len(counter_cov) if counter_cov else 0
    carc=sum(career_cov)/len(career_cov) if career_cov else 0
    s16c=sum(s16_cov)/len(s16_cov) if s16_cov else 0
    interval_stability=max(0,1-min(1,width/.30))
    freshness=.55
    evidence=round(100*(.20*completeness+.18*mcov+.12*sycov+.08*ccov+.12*carc+.10*s16c+.10*interval_stability+.05*freshness+.05*.74))
    label="Alta" if evidence>=75 else ("Moderada" if evidence>=55 else "Baixa")
    match=api_match(a,b); series_p=match["probability_team_a"] if match else elo_prob(ra["elo"],rb["elo"])
    form_a=[v for side,v in current_forms if side=="a"]; form_b=[v for side,v in current_forms if side=="b"]
    return {"team_a":a,"team_b":b,"side_a":side_a,"series_probability_team_a":series_p,
        "draft_game_probability_team_a":p_a,"draft_delta_pp":(p_a-base_a)*100,
        "game_baseline_probability_team_a":base_a,"mastery_diff":mastery_diff,"synergy_diff":synergy_diff,
        "team_a_synergy":sa,"team_b_synergy":sb,
        "posterior_interval_80":{"low":low,"high":high,"width":width},
        "evidence_confidence":evidence,"evidence_label":label,
        "confidence_components":{"draft_completeness":completeness,"local_mastery_coverage":mcov,
            "career_coverage":carc,"current_season_web_coverage":s16c,"synergy_coverage":sycov,
            "counter_coverage":ccov,"posterior_stability":interval_stability,"advanced_data_freshness":freshness},
        "current_lck_team_player_form":{"team_a_avg_wr":sum(form_a)/len(form_a) if form_a else None,
                                        "team_b_avg_wr":sum(form_b)/len(form_b) if form_b else None},
        "roles":detail,"fearless_illegal":sorted(set(illegal)),
        "patch_requested":payload.get("patch"),
        "patch_model":patch_eval,
        "v6_probability_team_a":v6_probability_team_a,
        "warning":"V8 production uses the statistically audited base game model. Patch analytics remain visible and can produce an experimental overlay, but predictive weight is zero after the patch candidate failed to improve the untouched 2026 external test."
    }



# ---------------------------------------------------------------------------
# V11 — Match Center / historical audit
# ---------------------------------------------------------------------------
def _historical_series_games_v11(row):
    day=str(row["date"])[:10]
    a,b=row["team1"],row["team2"]
    trows=db_rows(f"""SELECT * FROM team_games
                      WHERE substr(date,1,10)=? AND team IN (?,?){LG_SQL}
                      ORDER BY game,gameid,side""",(day,a,b)+LG_ARGS)
    prows=db_rows("""SELECT gameid,side,position,playername,team,champion,kills,deaths,assists,
                            totalgold,golddiffat15,xpdiffat15,csdiffat15,dpm
                     FROM player_games
                     WHERE substr(date,1,10)=? AND team IN (?,?)"""+LG_SQL+"""
                     ORDER BY gameid,side,position""",(day,a,b)+LG_ARGS)
    by_game={}
    for tr in trows:
        gid=str(tr["gameid"])
        g=by_game.setdefault(gid,{"game_id":gid,"game_number":tr.get("game"),"patch":tr.get("patch"),"teams":[],"players":[]})
        g["teams"].append({
          "team":tr["team"],"side":tr["side"],"winner":bool(tr["result"]),
          "kills":tr["kills"],"gold":tr["totalgold"],"towers":tr["towers"],
          "dragons":tr["dragons"],"barons":tr["barons"],
          "gd15":tr["golddiffat15"],"xp15":tr["xpdiffat15"],"cs15":tr["csdiffat15"],
          "duration_seconds":tr["gamelength"]
        })
    for pr in prows:
        gid=str(pr["gameid"])
        if gid in by_game:
            by_game[gid]["players"].append(pr)
    out=list(by_game.values())
    out.sort(key=lambda g:(g.get("game_number") or 999,g["game_id"]))
    return out


def _journal_for_v11(entity_type,entity_id):
    rows=db_rows("""SELECT * FROM prediction_journal_v11
                    WHERE entity_type=? AND entity_id=?
                    ORDER BY captured_at, id""",(entity_type,str(entity_id)))
    for r in rows:
        try:r["context"]=json.loads(r.pop("context_json") or "{}")
        except:r["context"]={}
    return rows


def _audit_prediction_v11(probability_a,team_a,winner):
    if probability_a is None:return None
    p=float(probability_a)
    y=1 if winner==team_a else 0
    pwin=p if y else 1-p
    return {
      "predicted_favorite":team_a if p>=.5 else None,
      "correct":bool((p>=.5)==bool(y)),
      "brier":(p-y)**2,
      "log_loss":-(y*math.log(max(p,1e-9))+(1-y)*math.log(max(1-p,1e-9))),
      "winner_probability":pwin,
      "surprise":-math.log(max(pwin,1e-9))
    }


def match_center_summary_v11():
    total=db_one("SELECT COUNT(*) n FROM match_archive_v11") or {"n":0}
    row=db_one("""SELECT COUNT(*) scored_series,
                         AVG(pregame_elo_correct) accuracy,
                         AVG(pregame_elo_brier) brier,
                         AVG(1-pregame_elo_correct) upset_rate,
                         AVG(CASE WHEN n_games=2 THEN 1.0 ELSE 0.0 END) sweep_rate
                  FROM match_archive_v11 WHERE pregame_elo_p_team1 IS NOT NULL""") or {}
    sweep_all=db_one("SELECT AVG(CASE WHEN wins1=0 OR wins2=0 THEN 1.0 ELSE 0.0 END) v FROM match_archive_v11") or {}
    tracked=db_one("SELECT COUNT(DISTINCT entity_type||':'||entity_id) n FROM prediction_journal_v11 WHERE validation_status='VALIDATED'") or {"n":0}
    riot_games=db_one("SELECT COUNT(*) n FROM riot_games_v10") or {"n":0}
    snapshots=db_one("SELECT COUNT(*) n FROM riot_live_snapshots_v10") or {"n":0}
    return {
      "historical_series":total.get("n",0),"historical_scored_series":row.get("scored_series",0),
      "historical_baseline_coverage":(float(row.get("scored_series") or 0)/float(total.get("n") or 1)),
      "historical_baseline_accuracy":row.get("accuracy"),"historical_baseline_brier":row.get("brier"),
      "historical_upset_rate":row.get("upset_rate"),"historical_sweep_rate":sweep_all.get("v"),
      "platform_forecasts_archived":tracked.get("n",0),
      "riot_games_cached":riot_games.get("n",0),"live_snapshots_saved":snapshots.get("n",0)
    }


def _historical_list_v11(team=None,year=None,limit=500):
    where=[];params=[]
    if team:
        where.append("(team1=? OR team2=?)");params.extend([team,team])
    if year:
        where.append("year=?");params.append(int(year))
    sql="""SELECT series_key,date,year,team1,team2,winner,wins1,wins2,n_games,source,
                  pregame_elo_p_team1,pregame_elo_favorite,pregame_elo_correct,pregame_elo_brier,
                  pregame_elo_log_loss
           FROM match_archive_v11"""
    if where:sql+=" WHERE "+" AND ".join(where)
    sql+=" ORDER BY date DESC LIMIT ?";params.append(int(limit))
    rows=db_rows(sql,tuple(params))
    for r in rows:
        r.update({"kind":"historical","status":"completed","id":"hist:"+r["series_key"],
                  "prediction_kind":"reconstructed_pregame_elo" if r["pregame_elo_p_team1"] is not None else None})
    return rows


def _series_prob_now_v29(pregame,score_a,score_b,best_of=3):
    """Probabilidade da série AGORA, derivada só do placar + leitura pré-série.

    Atualiza em evento discreto e certo — o fim de cada mapa. Deliberadamente
    não usa o overlay live experimental (ouro/torres): ele não é validado e faria
    o número da home tremer a cada refresh, contradizendo a régua de confiança
    que o resto do app aplica."""
    if pregame is None:return None
    try:
        sa=int(score_a or 0);sb=int(score_b or 0);bo=int(best_of or 3)
    except Exception:
        return None
    if bo not in (1,3,5,7):bo=3
    need=bo//2+1
    if sa>=need:return 1.0
    if sb>=need:return 0.0
    q=_series_game_prob(float(pregame),bo)
    return _remaining_series_prob(sa,sb,q,bo)


def _riot_event_items_v11():
    rows=db_rows("SELECT * FROM riot_events_v10 ORDER BY start_time DESC")
    out=[]
    now=_now_local_v23()
    for r in rows:
        status=v24_match_state(r.get("start_time"),r.get("state"),r.get("score_a"),r.get("score_b"),
                               now=now,best_of=r.get("match_strategy_count"))
        if status not in ("live","completed","upcoming"):
            continue
        a=canonical(r.get("team_a")) or r.get("team_a_code") or r.get("team_a")
        b=canonical(r.get("team_b")) or r.get("team_b_code") or r.get("team_b")
        # Um evento sem identificação de time não é exibível: viraria um card
        # "null x null" na home. Acontece quando o getLive traz um payload de
        # outra liga sem o bloco de times.
        if not a or not b:
            continue
        p=None
        if a in FULL_NAMES and b in FULL_NAMES:
            try:p=float(api_match(a,b)["probability_team_a"])
            except:pass
        out.append({
          "kind":"riot_event","status":status,"id":"riot:"+str(r["event_id"]),"event_id":str(r["event_id"]),
          "date":r.get("start_time"),"year":int(str(r.get("start_time") or "0000")[:4] or 0),
          "team1":a,"team2":b,"wins1":r.get("score_a"),"wins2":r.get("score_b"),
          "winner":a if status=="completed" and r.get("score_a") is not None and r.get("score_b") is not None and int(r["score_a"])>int(r["score_b"]) else (
                   b if status=="completed" and r.get("score_a") is not None and r.get("score_b") is not None and int(r["score_b"])>int(r["score_a"]) else None),
          "source":"Riot LoL Esports","probability_team1":p,"block_name":r.get("block_name"),
          # Leitura pré-série congelada (auditável) + leitura no placar atual.
          # Só faz sentido divergirem enquanto a série está em andamento.
          "pregame_probability_team1":p,
          "probability_team1_now":(_series_prob_now_v29(p,r.get("score_a"),r.get("score_b"),
                                                        r.get("match_strategy_count"))
                                   if status=="live" else None),
          "best_of":r.get("match_strategy_count")
        })
    return out

def match_center_v11(status="all",team=None,year=None,limit=500):
    team=canonical(team) if team else None
    items=[]
    if status in ("all","completed","history"):
        items.extend(_historical_list_v11(team,year,limit))
    # Riot adds live/upcoming and any completed events that may not yet be in historical archive.
    for r in _riot_event_items_v11():
        if status!="all" and status!="history" and r["status"]!=status:continue
        if status=="history" and r["status"]!="completed":continue
        if team and team not in (r["team1"],r["team2"]):continue
        if year and int(r.get("year") or 0)!=int(year):continue
        # avoid duplicate completed series if pair/date already in local history
        if r["status"]=="completed":
            day=str(r["date"] or "")[:10]
            if any(x["kind"]=="historical" and x["date"]==day and {x["team1"],x["team2"]}=={r["team1"],r["team2"]} for x in items):
                continue
        items.append(r)
    def sortkey(x):
        return str(x.get("date") or "")
    items=sorted(items,key=sortkey,reverse=True)[:int(limit)]
    return {"summary":match_center_summary_v11(),"items":items,
            "years":sorted({int(x["year"]) for x in items if x.get("year")},reverse=True),
            "teams":[r["team"] for r in db_rows("SELECT team FROM current_ratings ORDER BY rank")]}


def historical_detail_v11(series_key):
    row=db_one("SELECT * FROM match_archive_v11 WHERE series_key=?",(series_key,))
    if not row:return None
    p=row.get("pregame_elo_p_team1")
    audit=_audit_prediction_v11(p,row["team1"],row["winner"])
    games=_historical_series_games_v11(row)
    # True archived forecast, if any future matching journal exists by series key.
    journal=_journal_for_v11("series",series_key)
    matching_event=None;platform_journal=[]
    for ev in db_rows("SELECT * FROM riot_events_v10 ORDER BY start_time DESC"):
        ea=canonical(ev.get("team_a")) or ev.get("team_a_code")
        eb=canonical(ev.get("team_b")) or ev.get("team_b_code")
        if {ea,eb}=={row["team1"],row["team2"]} and _local_date_from_iso(ev.get("start_time"))==str(row["date"])[:10]:
            matching_event=ev
            platform_journal=_journal_for_v11("series",ev["event_id"])
            break
    return {
      "kind":"historical","series":row,"audit":audit,"journal":journal,"games":games,
      "matching_riot_event":matching_event,"platform_journal":platform_journal,
      "coverage":{
        "prediction":"baseline pré-jogo reconstruído" if p is not None else "sem previsão histórica",
        "detailed_games":bool(games),
        "note":"A previsão histórica reconstruída usa somente o Elo existente antes da série. Ela não é apresentada como se fosse um forecast originalmente salvo pela plataforma."
      }
    }


def riot_detail_v11(event_id):
    ev=db_one("SELECT * FROM riot_events_v10 WHERE event_id=?",(str(event_id),))
    if not ev:return None
    games=db_rows("SELECT * FROM riot_games_v10 WHERE event_id=? ORDER BY game_number",(str(event_id),))
    for g in games:
        try:g["draft"]=json.loads(g.get("draft_json") or "{}")
        except:g["draft"]={}
        g["participants"]=db_rows("""SELECT * FROM riot_participants_v10
                                    WHERE game_id=? ORDER BY side,participant_id""",(str(g["game_id"]),))
        g["journal"]=_journal_for_v11("game",g["game_id"])
        g["timeline"]=live_timeline_v10(g["game_id"],500)
        case=db_one("""SELECT * FROM live_case_studies_v10
                       WHERE event_id=? AND game_number=?""",(str(event_id),int(g["game_number"])))
        g["case_study"]=case
        if case and case.get("result_winner"):
            g["draft_audit"]=_audit_prediction_v11(case.get("draft_p_a"),case.get("team_a"),case.get("result_winner"))
            g["pregame_audit"]=_audit_prediction_v11(case.get("pre_series_p_a"),case.get("team_a"),case.get("result_winner"))
    a=canonical(ev.get("team_a")) or ev.get("team_a_code") or ev.get("team_a")
    b=canonical(ev.get("team_b")) or ev.get("team_b_code") or ev.get("team_b")
    pre=None
    if a in FULL_NAMES and b in FULL_NAMES:
        try:pre=api_match(a,b,ev.get("match_strategy_count"))
        except:pass
    return {"kind":"riot_event","event":ev,"games":games,"current_prediction":pre,
            "source_note":"Riot é a fonte de estado/draft/live. Forecasts arquivados são mantidos separadamente do resultado final."}



def log_series_pregame_v11(snap):
    event_id=str(snap.get("event_id") or "")
    if not event_id:return
    existing=db_one("""SELECT id FROM prediction_journal_v11
                       WHERE entity_type='series' AND entity_id=? AND stage='pre_series' LIMIT 1""",(event_id,))
    if existing:return
    teams=(snap.get("series") or {}).get("teams") or []
    if len(teams)<2:return
    a=canonical(teams[0].get("name")) or teams[0].get("code")
    b=canonical(teams[1].get("name")) or teams[1].get("code")
    if a not in FULL_NAMES or b not in FULL_NAMES:return
    m=api_match(a,b)
    if not m:return
    with db_connect() as con:
        con.execute("""INSERT OR IGNORE INTO prediction_journal_v11
          (entity_type,entity_id,stage,captured_at,team_a,team_b,probability_team_a,
           model_version,validation_status,context_json,source)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
          "series",event_id,"pre_series",
          str(snap.get("timestamp") or datetime.now(timezone.utc).isoformat()),
          a,b,float(m["probability_team_a"]),"V8 audited series","VALIDATED",
          json.dumps({"event_id":event_id,"prediction_mode":m.get("mode"),"note":m.get("note")},ensure_ascii=False),
          "Riot event start capture"
        ))
        con.commit()

def log_live_predictions_v11(snap,draft_analysis=None,live_estimate=None):
    """Append-only journal: preserves what the model said at that moment."""
    gid=str(snap.get("game_id") or "")
    if not gid:return
    now=str(snap.get("timestamp") or datetime.now(timezone.utc).isoformat())
    entries=[]
    if draft_analysis:
        # one immutable draft forecast per game: use a stable stage timestamp derived from game id if absent
        existing=db_one("""SELECT id FROM prediction_journal_v11
                           WHERE entity_type='game' AND entity_id=? AND stage='post_draft' LIMIT 1""",(gid,))
        if not existing:
            entries.append(("game",gid,"post_draft",now,draft_analysis["team_a"],draft_analysis["team_b"],
                            float(draft_analysis["draft_game_probability_team_a"]),"V8 audited draft","VALIDATED",
                            json.dumps({"patch":snap.get("patch"),"game_number":snap.get("game_number"),
                                        "picks":_draft_from_snapshot(snap)},ensure_ascii=False),
                            "Riot live capture"))
    if live_estimate:
        entries.append(("game",gid,"live",now,canonical(snap["blue"].get("team")) or snap["blue"].get("team"),
                        canonical(snap["red"].get("team")) or snap["red"].get("team"),
                        float(live_estimate["probability_blue"]),"V10 live heuristic","EXPERIMENTAL",
                        json.dumps(live_estimate.get("features") or {},ensure_ascii=False),"Riot live snapshot"))
    if entries:
        with db_connect() as con:
            con.executemany("""INSERT OR IGNORE INTO prediction_journal_v11
              (entity_type,entity_id,stage,captured_at,team_a,team_b,probability_team_a,
               model_version,validation_status,context_json,source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",entries)
            con.commit()



# ---------------------------------------------------------------------------
# V12 — Product APIs: unified matches + explore
# ---------------------------------------------------------------------------
ROLE_LABELS_V12={"top":"Top","jng":"Jungle","mid":"Mid","bot":"ADC","sup":"Support"}

def v12_player_list(team=None,role=None,q=None,limit=200):
    where=[];params=[]
    if team:
        where.append("r.team=?");params.append(canonical(team) or team)
    if role:
        where.append("r.role=?");params.append(role)
    if q:
        where.append("(lower(r.player) LIKE ? OR lower(r.team) LIKE ?)");like=f"%{q.lower()}%";params += [like,like]
    sql="""SELECT r.team,r.role,r.player,r.verified_date,
                  COALESCE(o.games,0) games,COALESCE(o.wins,0) wins,
                  COALESCE(o.player_prior,0.5) player_prior
           FROM draft_rosters r LEFT JOIN draft_player_overall o ON o.player=r.player"""
    if where: sql+=" WHERE "+" AND ".join(where)
    sql+=" ORDER BY r.team, CASE r.role WHEN 'top' THEN 1 WHEN 'jng' THEN 2 WHEN 'mid' THEN 3 WHEN 'bot' THEN 4 ELSE 5 END, r.player LIMIT ?"
    params.append(int(limit))
    rows=db_rows(sql,tuple(params))
    for r in rows:
        g=float(r.get("games") or 0);w=float(r.get("wins") or 0)
        r["winrate"]=w/g if g else None
        r["role_label"]=ROLE_LABELS_V12.get(r["role"],r["role"])
        fav=db_one("""SELECT champion,games,wins,smoothed_winrate,kda,gd15,xpd15,csd15,dpm
                      FROM draft_player_champion WHERE player=? AND scope='local_2025_2026'
                      ORDER BY games DESC LIMIT 1""",(r["player"],))
        r["signature"]=fav
    return rows


def v12_player_detail(player):
    roster=db_one("""SELECT team,role,player,verified_date FROM draft_rosters
                     WHERE player=? ORDER BY verified_date DESC LIMIT 1""",(player,))
    overall=db_one("SELECT * FROM draft_player_overall WHERE player=?",(player,))
    career=db_rows("""SELECT player,champion,games,winrate,kda,scope,snapshot_date,source_url
                      FROM draft_player_champion_web WHERE player=? AND scope='career'
                      ORDER BY games DESC, winrate DESC LIMIT 80""",(player,))
    local_history=db_rows("""SELECT * FROM draft_player_champion WHERE player=? AND scope='local_2025_2026'
                             ORDER BY games DESC, smoothed_winrate DESC LIMIT 80""",(player,))
    current=db_rows("""SELECT * FROM draft_player_champion WHERE player=? AND scope='2026'
                       ORDER BY games DESC, smoothed_winrate DESC LIMIT 60""",(player,))
    patches=db_rows("""SELECT patch,champion,role,games,wins,winrate,gd15,xpd15,csd15,dpm
                       FROM patch_player_champion WHERE player=? AND year=2026
                       ORDER BY patch DESC,games DESC LIMIT 100""",(player,))
    recent=db_rows("""SELECT substr(date,1,10) date,teamname team,position role,champion,result,kills,deaths,assists,
                      totalgold,cspm,dpm,golddiffat15,xpdiffat15,csdiffat15
                      FROM player_games WHERE playername=?"""+LG_SQL+"""
                      ORDER BY date DESC,gameid DESC LIMIT 20""",(player,)+LG_ARGS)
    return {"player":player,"roster":roster,"overall":overall,"career_champions":career,
            "local_2025_2026_champions":local_history,"season_champions":current,
            "patches":patches,"recent_games":recent}


def v12_champion_list(role=None,q=None,limit=250):
    where=["scope='2026'"];params=[]
    if role:
        where.append("role=?");params.append(role)
    if q:
        where.append("lower(champion) LIKE ?");params.append(f"%{q.lower()}%")
    rows=db_rows("""SELECT role,champion,games,wins,winrate,smoothed_winrate,gd15
                    FROM draft_champion_meta WHERE """+" AND ".join(where)+
                 " ORDER BY games DESC,champion LIMIT ?",tuple(params+[int(limit)]))
    for r in rows:r["role_label"]=ROLE_LABELS_V12.get(r["role"],r["role"])
    return rows


def v12_champion_detail(champion,role=None):
    params=[champion];role_sql=""
    if role: role_sql=" AND role=?";params.append(role)
    meta=db_rows("""SELECT * FROM draft_champion_meta WHERE champion=?"""+role_sql+
                 """ ORDER BY CASE scope WHEN '2026' THEN 1 ELSE 2 END,games DESC""",tuple(params))
    players=db_rows("""SELECT player,team,role,scope,games,wins,winrate,smoothed_winrate,kda,gd15,xpd15,csd15,dpm
                       FROM draft_player_champion WHERE champion=?"""+role_sql+
                    """ ORDER BY CASE scope WHEN '2026' THEN 1 ELSE 2 END,games DESC LIMIT 80""",tuple(params))
    patch_params=[champion]; patch_role=""
    if role:patch_role=" AND position=?";patch_params.append(role)
    patches=db_rows("""SELECT year,patch,position role,games,wins,winrate,smoothed_winrate,gd15,xpd15,csd15,dpm
                       FROM patch_champion_meta WHERE champion=?"""+patch_role+
                    """ ORDER BY year DESC,patch DESC""",tuple(patch_params))
    matchups=db_rows("""SELECT * FROM draft_counter
                       WHERE champion_a=? OR champion_b=?
                       ORDER BY games DESC LIMIT 60""",(champion,champion))
    return {"champion":champion,"role":role,"meta":meta,"players":players,"patches":patches,"matchups":matchups}


def v12_team_detail(team):
    team=canonical(team) or team
    rating=db_one("SELECT * FROM current_ratings WHERE team=?",(team,))
    roster=db_rows("""SELECT team,role,player,verified_date FROM draft_rosters WHERE team=?
                      ORDER BY CASE role WHEN 'top' THEN 1 WHEN 'jng' THEN 2 WHEN 'mid' THEN 3 WHEN 'bot' THEN 4 ELSE 5 END""",(team,))
    history=_historical_list_v11(team,None,50)
    recent=[x for x in history[:15]]
    champs=db_rows("""SELECT champion,role,SUM(games) games,SUM(wins) wins,
                             SUM(wins)*1.0/NULLIF(SUM(games),0) winrate
                      FROM draft_player_champion WHERE team=? AND scope='2026'
                      GROUP BY champion,role ORDER BY games DESC LIMIT 30""",(team,))
    return {"team":team,"rating":rating,"roster":roster,"recent_series":recent,"champion_pool":champs}



# ---------------------------------------------------------------------------
# V27 — resilient live discovery / schedule fallback
# ---------------------------------------------------------------------------
def _completed_match_exists_v27(day,a,b):
    row=db_one("""SELECT 1 ok FROM match_archive_v11
                  WHERE substr(date,1,10)=?
                    AND ((team1=? AND team2=?) OR (team1=? AND team2=?))
                  LIMIT 1""",(str(day)[:10],a,b,b,a))
    return bool(row)

def _schedule_rows_for_day_v27(day):
    return db_rows("""SELECT rowid,* FROM upcoming_matches
                      WHERE substr(date,1,10)=?
                      ORDER BY rowid""",(str(day)[:10],))

def _schedule_start_v27(row,now=None):
    """Resolve an exact or fallback local start for an LCK matchday row.

    Exact Riot start_time wins. Legacy date-only rows use LCK's two regular
    matchday slots in Brazil: 05:00 and 07:00 (UTC-3), preserving insertion order.
    This is only a display/live-recovery fallback; it never becomes historical truth.
    """
    now=now or _now_local_v23()
    if row.get("start_time"):
        dt=_local_dt_from_iso_v23(row.get("start_time"))
        if dt:return dt,"riot_exact"
    day=str(row.get("date") or "")[:10]
    try:
        y,m,d=map(int,day.split("-"))
    except Exception:
        return None,"unknown"
    rows=_schedule_rows_for_day_v27(day)
    ids=[int(x["rowid"]) for x in rows]
    try:idx=ids.index(int(row.get("rowid")))
    except Exception:idx=0
    # Regular LCK R3/R4 matchday fallback: first series 05:00, second 07:00 BRT.
    hour=5+2*idx
    return datetime(y,m,d,hour,0,0,tzinfo=BRAZIL_TZ),"legacy_slot_inferred"

def _schedule_row_state_v27(row,now=None):
    now=now or _now_local_v23()
    a=row.get("team_a");b=row.get("team_b");day=str(row.get("date") or "")[:10]
    if _completed_match_exists_v27(day,a,b):
        return "completed"
    start,source=_schedule_start_v27(row,now)
    if not start:return "unknown"
    rows=_schedule_rows_for_day_v27(day)
    starts=[]
    for rr in rows:
        st,_=_schedule_start_v27(rr,now)
        if st:starts.append((int(rr["rowid"]),st))
    starts.sort(key=lambda x:x[1])
    next_start=None
    for rid,st in starts:
        if int(rid)==int(row.get("rowid")):
            later=[x[1] for x in starts if x[1]>st]
            next_start=min(later) if later else None
            break
    if now < start-timedelta(minutes=15):
        return "upcoming"
    if now < start:
        return "upcoming"
    # First series stops being the fallback live candidate once the next scheduled
    # series has begun. Last series gets a conservative three-hour window.
    live_until=next_start if next_start else start+timedelta(hours=3)
    if start <= now < live_until:
        return "live_candidate"
    return "pending"

def _fallback_live_candidate_v27(now=None):
    now=now or _now_local_v23()
    day=now.date().isoformat()
    rows=_schedule_rows_for_day_v27(day)
    cands=[]
    for r in rows:
        if _schedule_row_state_v27(r,now)!="live_candidate":continue
        start,source=_schedule_start_v27(r,now)
        cands.append((start,r,source))
    if not cands:return None
    cands.sort(key=lambda x:x[0],reverse=True)
    start,r,source=cands[0]
    a=r["team_a"];b=r["team_b"]
    p=r.get("probability_team_a")
    return {
      "kind":"upcoming","status":"live",
      "id":f"upcoming:{r['date']}:{a}:{b}",
      "date":start.isoformat(),"team1":a,"team2":b,
      "probability_team1":p,"block_name":r.get("week"),
      "source":"LCK schedule fallback",
      "live_confidence":"schedule_fallback",
      "live_detection_note":"Horário do matchday indica jogo em andamento; sincronizando Riot Event ID.",
      "event_id":r.get("event_id")
    }

def _live_items_v27(include_fallback=True):
    live=[x for x in _riot_event_items_v11() if x["status"]=="live"]
    if live:return live
    if include_fallback:
        fb=_fallback_live_candidate_v27()
        if fb:return [fb]
    return []

def sync_live_now_v27():
    """Actively try to promote a schedule fallback to a real Riot live event."""
    result={"ok":False,"event_id":None,"source":None,"errors":[]}
    # 1. Dedicated getLive endpoint.
    try:
        ev=discover_lck_live_event_v10()
        if ev:
            eid=str(ev["id"])
            try:
                live_response_v10(eid,True)
            except Exception as e:
                result["errors"].append(f"livestats: {type(e).__name__}: {e}")
            result.update({"ok":True,"event_id":eid,"source":"riot_getLive"})
            return result
    except Exception as e:
        result["errors"].append(f"getLive: {type(e).__name__}: {e}")

    # 2. Refresh schedule; schedule events themselves can carry inProgress state.
    try:
        sched=refresh_riot_schedule_v10()
        live=[x for x in _riot_event_items_v11() if x["status"]=="live"]
        if live:
            eid=str(live[0]["event_id"])
            try:live_response_v10(eid,True)
            except Exception as e:result["errors"].append(f"livestats: {type(e).__name__}: {e}")
            result.update({"ok":True,"event_id":eid,"source":"riot_schedule","schedule":sched})
            return result
        result["schedule"]=sched
    except Exception as e:
        result["errors"].append(f"schedule: {type(e).__name__}: {e}")

    # 3. Honest fallback: show the current scheduled series, but do not invent live stats.
    fb=_fallback_live_candidate_v27()
    if fb:
        result.update({"ok":True,"source":"schedule_fallback","fallback":fb})
    return result

def v12_match_items(status="all",limit=500):
    prune_stale_schedule_v23()
    items=[]
    # Riot events are authoritative whenever available.
    for r in _riot_event_items_v11():
        if status!="all" and r["status"]!=status:continue
        items.append(r)

    # Live recovery fallback: never leave the tab blank just because Event ID sync lags.
    if status in ("all","live") and not any(x.get("status")=="live" for x in items):
        fb=_fallback_live_candidate_v27()
        if fb:items.append(fb)

    # Scheduled rows only remain in Upcoming if their resolved V27 state is actually future.
    if status in ("all","upcoming"):
        existing={(str(x.get("date") or "")[:10],frozenset([x["team1"],x["team2"]])) for x in items}
        for u in db_rows("SELECT rowid,* FROM upcoming_matches ORDER BY date,rowid"):
            if _schedule_row_state_v27(u)!="upcoming":continue
            key=(str(u.get("date") or "")[:10],frozenset([u["team_a"],u["team_b"]]))
            if key in existing:continue
            st,_src=_schedule_start_v27(u)
            items.append({
              "kind":"upcoming","status":"upcoming",
              "id":f"upcoming:{u['date']}:{u['team_a']}:{u['team_b']}",
              "date":st.isoformat() if st else (u.get("start_time") or u["date"]),
              "team1":u["team_a"],"team2":u["team_b"],
              "probability_team1":u.get("probability_team_a"),
              "block_name":u.get("week"),"source":u.get("source")
            })
            existing.add(key)

    if status in ("all","completed"):
        existing={(str(x.get("date") or "")[:10],frozenset([x["team1"],x["team2"]])) for x in items if x["status"]=="completed"}
        for h in _historical_list_v11(None,None,limit):
            key=(str(h["date"])[:10],frozenset([h["team1"],h["team2"]]))
            if key not in existing:items.append(h)

    items=sorted(items,key=lambda x:str(x.get("date") or ""),reverse=(status=="completed"))
    return items[:int(limit)]

def v12_upcoming_detail(raw_id):
    # raw_id = upcoming:YYYY-MM-DD:TEAM:TEAM
    parts=raw_id.split(":")
    if len(parts)<4:return None
    _,day,a,b=parts[:4]
    row=db_one("""SELECT * FROM upcoming_matches WHERE date=? AND team_a=? AND team_b=? LIMIT 1""",(day,a,b))
    if not row:
        row=db_one("""SELECT * FROM upcoming_matches WHERE date=? AND team_a=? AND team_b=? LIMIT 1""",(day,b,a))
        if not row:return None
        a,b=row["team_a"],row["team_b"]
    m=api_match(a,b)
    row2=dict(row)
    rowid=db_one("""SELECT rowid rid FROM upcoming_matches WHERE date=? AND team_a=? AND team_b=? LIMIT 1""",(day,a,b))
    if rowid:row2["rowid"]=rowid["rid"]
    state=_schedule_row_state_v27(row2)
    st,st_source=_schedule_start_v27(row2)
    return {"kind":"upcoming","id":raw_id,"date":st.isoformat() if st else day,
            "team_a":a,"team_b":b,"prediction":m,
            "scoreline":m.get("scoreline"),"analysis":m.get("analysis"),
            "schedule_state":state,"live_confidence":"schedule_fallback" if state=="live_candidate" else None,
            "start_source":st_source,
            "note":"Prévia usa apenas dados disponíveis antes da série."}


def v12_unified_match(ident):
    if ident.startswith("hist:"):
        return historical_detail_v11(ident[5:])
    if ident.startswith("riot:"):
        obj=riot_detail_v11(ident[5:])
        if obj:
            ev=obj.get("event") or {}
            state=str(ev.get("state") or "").lower()
            games=obj.get("games") or []
            game_states=[str(g.get("state") or "").lower() for g in games]
            # O estado do evento pode vir vazio/nulo da Riot enquanto a série já
            # rola. Os mapas são a fonte mais confiável nesse caso: se qualquer
            # mapa está em andamento, a série está ao vivo.
            # Série decidida encerra, mesmo com o event.state ainda 'inProgress'
            # (a Riot demora a fechar esse campo). Placar é fato; state envelhece.
            decided=False
            try:
                bo=int(ev.get("match_strategy_count") or 3)
                need=(bo if bo in (1,3,5,7) else 3)//2+1
                decided=max(int(ev.get("score_a") or 0),int(ev.get("score_b") or 0))>=need
            except Exception:
                pass
            if decided:
                obj["phase"]="post"
            elif "progress" in state or any("progress" in s for s in game_states):
                obj["phase"]="live"
            elif "complete" in state:
                obj["phase"]="post"
            else:
                canonical_state=v24_match_state(ev.get("start_time"),state or None,
                                                ev.get("score_a"),ev.get("score_b"),
                                                best_of=ev.get("match_strategy_count"))
                obj["phase"]={"completed":"post","live":"live"}.get(canonical_state,"pre")
            obj["state_source"]=("event" if state else
                                 ("games" if any("progress" in s for s in game_states) else "schedule"))
        return obj
    if ident.startswith("upcoming:"):
        obj=v12_upcoming_detail(ident)
        if obj:obj["phase"]="live" if obj.get("schedule_state")=="live_candidate" else "pre"
        return obj
    return None


def v12_home():
    removed=prune_stale_schedule_v23()
    live=_live_items_v27(True)
    upcoming=[]
    existing={(str(x.get("date") or "")[:10],frozenset([x["team1"],x["team2"]])) for x in live}
    for r in _riot_event_items_v11():
        if r["status"]!="upcoming":continue
        key=(str(r.get("date") or "")[:10],frozenset([r["team1"],r["team2"]]))
        if key not in existing:
            upcoming.append(r);existing.add(key)
    for u in db_rows("SELECT rowid,* FROM upcoming_matches ORDER BY date,rowid LIMIT 30"):
        if _schedule_row_state_v27(u)!="upcoming":continue
        key=(str(u["date"])[:10],frozenset([u["team_a"],u["team_b"]]))
        if key in existing:continue
        st,_src=_schedule_start_v27(u)
        upcoming.append({
          "kind":"upcoming","status":"upcoming","id":f"upcoming:{u['date']}:{u['team_a']}:{u['team_b']}",
          "date":st.isoformat() if st else (u.get("start_time") or u["date"]),
          "team1":u["team_a"],"team2":u["team_b"],
          "probability_team1":u.get("probability_team_a"),"block_name":u.get("week"),"source":u.get("source")
        })
        existing.add(key)
    recent=_historical_list_v11(None,2026,6)
    return {
      "live":live[:3],"upcoming":sorted(upcoming,key=lambda x:str(x.get("date") or ""))[:8],"recent":recent[:6],
      "rankings":db_rows("SELECT * FROM current_ratings ORDER BY rank LIMIT 10"),
      "model":{"winner":db_one("SELECT * FROM statistical_audit_v8 WHERE stage='V8 Production'"),
               "scoreline":db_one("SELECT * FROM scoreline_validation_v9 WHERE model='Two-stage scoreline V9'")},
      "schedule_status":{**v23_schedule_status(),"stale_rows_removed":removed,
                         "live_source":live[0].get("live_confidence","riot") if live else None},
      "team_assets":v23_team_assets(),
      "data":{"history":match_center_summary_v11(),
              "source":db_one("SELECT value FROM metadata WHERE key='primary_match_feed'")}
    }



# ---------------------------------------------------------------------------
# V13 — Draft Decision Engine
# ---------------------------------------------------------------------------
def _v13_player_for(team,role):
    row=db_one("SELECT player FROM draft_rosters WHERE team=? AND role=? LIMIT 1",(team,role))
    return row["player"] if row else None


def _v13_candidate_pool(player,role,limit=28):
    seen={}
    # Player 2026 pool gets first priority.
    for r in db_rows("""SELECT champion,games,wins,winrate,smoothed_winrate,kda,gd15
                        FROM draft_player_champion
                        WHERE player=? AND scope='2026'
                        ORDER BY games DESC,smoothed_winrate DESC LIMIT 18""",(player,)):
        seen[r["champion"]]={"champion":r["champion"],"player_row":r,"source_rank":0}
    # Local 2025-2026 history broadens comfort pool.
    for r in db_rows("""SELECT champion,games,wins,winrate,smoothed_winrate,kda,gd15
                        FROM draft_player_champion
                        WHERE player=? AND scope='local_2025_2026'
                        ORDER BY games DESC,smoothed_winrate DESC LIMIT 24""",(player,)):
        if r["champion"] not in seen:
            seen[r["champion"]]={"champion":r["champion"],"player_row":r,"source_rank":1}
    # Role meta adds plausible legal champions not yet played much by the player.
    for r in db_rows("""SELECT champion,games,wins,winrate,smoothed_winrate,gd15
                        FROM draft_champion_meta
                        WHERE scope='2026' AND role=?
                        ORDER BY games DESC,smoothed_winrate DESC LIMIT 24""",(role,)):
        if r["champion"] not in seen:
            seen[r["champion"]]={"champion":r["champion"],"player_row":None,"source_rank":2}
        seen[r["champion"]]["meta_row"]=r
    # Enrich meta for player-derived candidates.
    for c in list(seen):
        if "meta_row" not in seen[c]:
            seen[c]["meta_row"]=db_one("""SELECT champion,games,wins,winrate,smoothed_winrate,gd15
                                         FROM draft_champion_meta
                                         WHERE scope='2026' AND role=? AND champion=? LIMIT 1""",(role,c))
    vals=list(seen.values())
    vals.sort(key=lambda x:(
        x.get("source_rank",9),
        -(float((x.get("player_row") or {}).get("games") or 0)),
        -(float((x.get("meta_row") or {}).get("games") or 0))
    ))
    return vals[:int(limit)]


def _v13_pick_set(payload):
    vals=[]
    for side in ("picks_a","picks_b"):
        for c in (payload.get(side) or {}).values():
            if c:vals.append(str(c))
    return {_champ_key_v10(x) for x in vals}


def _v13_recommend_reason(item,target_side,target_role,opponent_champion):
    pr=item.get("player_row") or {}
    mr=item.get("meta_row") or {}
    parts=[]
    if pr and float(pr.get("games") or 0)>=6:
        parts.append(f"{int(pr['games'])} jogos do jogador")
    elif pr and float(pr.get("games") or 0)>0:
        parts.append(f"{int(pr['games'])} jogos do jogador (amostra pequena)")
    else:
        parts.append("sem amostra relevante do jogador")
    if mr and float(mr.get("games") or 0)>=8:
        parts.append(f"{int(mr['games'])} jogos no meta 2026 da role")
    if opponent_champion:
        parts.append(f"resposta a {opponent_champion}")
    return " · ".join(parts)


def draft_recommend_v13(payload):
    a=str(payload.get("team_a","")).upper()
    b=str(payload.get("team_b","")).upper()
    if a==b or not a or not b:
        return {"error":"Escolha duas equipes diferentes."}
    target_side=str(payload.get("target_side","a")).lower()
    target_role=str(payload.get("target_role","")).lower()
    if target_side not in ("a","b") or target_role not in ("top","jng","mid","bot","sup"):
        return {"error":"target_side/target_role inválidos."}

    picks_a=dict(payload.get("picks_a") or {})
    picks_b=dict(payload.get("picks_b") or {})
    fearless=[str(x).strip() for x in (payload.get("fearless_used") or []) if str(x).strip()]
    fearless_keys={_champ_key_v10(x) for x in fearless}
    used=_v13_pick_set(payload)

    target_team=a if target_side=="a" else b
    target_picks=picks_a if target_side=="a" else picks_b
    opponent_picks=picks_b if target_side=="a" else picks_a
    player=_v13_player_for(target_team,target_role)
    if not player:
        return {"error":"Não encontrei o jogador atual dessa role."}

    # Current partial draft is the neutral comparator.
    baseline_payload={
      "team_a":a,"team_b":b,"side_a":payload.get("side_a","Blue"),"patch":payload.get("patch"),
      "picks_a":picks_a,"picks_b":picks_b,"fearless_used":fearless
    }
    current=evaluate_draft(baseline_payload)
    if current.get("error"):return current
    current_p=float(current["draft_game_probability_team_a"])
    current_target=current_p if target_side=="a" else 1-current_p

    existing=target_picks.get(target_role)
    if existing:
        used.discard(_champ_key_v10(existing))

    candidates=[]
    opponent_champion=opponent_picks.get(target_role)
    for item in _v13_candidate_pool(player,target_role,int(payload.get("candidate_pool_limit") or 28)):
        champ=item["champion"]
        ck=_champ_key_v10(champ)
        if ck in used or ck in fearless_keys:continue
        ca=dict(picks_a);cb=dict(picks_b)
        (ca if target_side=="a" else cb)[target_role]=champ
        ev=evaluate_draft({
          "team_a":a,"team_b":b,"side_a":payload.get("side_a","Blue"),"patch":payload.get("patch"),
          "picks_a":ca,"picks_b":cb,"fearless_used":fearless
        })
        if ev.get("error"):continue
        p_a=float(ev["draft_game_probability_team_a"])
        target_p=p_a if target_side=="a" else 1-p_a
        role_row=next((x for x in ev.get("roles",[]) if x.get("role")==target_role),{})
        pr=item.get("player_row") or {}
        mr=item.get("meta_row") or {}
        player_games=int(pr.get("games") or 0)
        meta_games=int(mr.get("games") or 0)
        evidence_conf=int(ev.get("evidence_confidence") or 0)
        # Recommendation-policy shrinkage: the V8 probability itself is untouched.
        # Only the ordering of candidate recommendations is pulled toward the
        # current partial-draft baseline when player/meta evidence is thin.
        familiarity=min(player_games,12)/12
        meta_support=min(meta_games,20)/20
        policy_confidence=min(1.0,max(0.25,0.35+0.30*familiarity+0.20*meta_support+0.15*(evidence_conf/100)))
        decision_p=current_target+(target_p-current_target)*policy_confidence
        candidates.append({
          "champion":champ,
          "probability_team_a":p_a,
          "probability_target_team":target_p,
          "delta_target_pp":(target_p-current_target)*100,
          "decision_probability_target_team":decision_p,
          "decision_delta_target_pp":(decision_p-current_target)*100,
          "policy_confidence":policy_confidence,
          "evidence_confidence":evidence_conf,
          "evidence_label":ev.get("evidence_label"),
          "player":player,
          "player_games":player_games,
          "player_wr":pr.get("winrate"),
          "player_eb":role_row.get("team_a_mastery_eb") if target_side=="a" else role_row.get("team_b_mastery_eb"),
          "meta_games":meta_games,
          "meta_wr":mr.get("smoothed_winrate") if mr else None,
          "opponent_champion":opponent_champion,
          "counter_context":role_row.get("counter_a_vs_b"),
          "reason":_v13_recommend_reason(item,target_side,target_role,opponent_champion),
          "production_model":"V8 audited draft core",
          "recommendation_status":"EXPERIMENTAL_DECISION_SUPPORT"
        })

    candidates.sort(key=lambda x:(x["decision_probability_target_team"],
                                  x["probability_target_team"],
                                  x["evidence_confidence"]),reverse=True)
    top=candidates[:int(payload.get("limit") or 10)]

    # Log only returned candidates, not every temporary simulation.
    try:
        with db_connect() as con:
            now=datetime.now(timezone.utc).isoformat()
            picks_json=json.dumps({"a":picks_a,"b":picks_b},ensure_ascii=False,separators=(",",":"))
            fearless_json=json.dumps(fearless,ensure_ascii=False,separators=(",",":"))
            for x in top:
                con.execute("""INSERT INTO draft_decision_log_v13
                 (created_at,team_a,team_b,side_a,patch,target_side,target_role,current_probability_team_a,
                  candidate,candidate_probability_team_a,candidate_delta_target_pp,evidence_confidence,
                  player,player_games,player_wr,player_eb,meta_games,meta_wr,opponent_champion,
                  fearless_json,picks_json,recommendation_status,model_version)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (now,a,b,payload.get("side_a","Blue"),payload.get("patch"),target_side,target_role,current_p,
                  x["champion"],x["probability_team_a"],x["decision_delta_target_pp"],x["evidence_confidence"],
                  player,x["player_games"],x["player_wr"],x["player_eb"],x["meta_games"],x["meta_wr"],
                  opponent_champion,fearless_json,picks_json,x["recommendation_status"],x["production_model"]))
            con.commit()
    except Exception:
        pass

    return {
      "team_a":a,"team_b":b,"target_side":target_side,"target_team":target_team,"target_role":target_role,
      "player":player,"opponent_champion":opponent_champion,
      "current_probability_team_a":current_p,"current_probability_target_team":current_target,
      "recommendation_status":"EXPERIMENTAL_DECISION_SUPPORT",
      "note":"Ranking relativo usando o motor V8, com shrinkage adicional apenas no ranking de recomendação quando player/meta têm pouca evidência. A probabilidade bruta V8 não é alterada. A política de recomendar picks ainda não possui validação própria e não é Production.",
      "candidates":top
    }


def history_coverage_v13():
    manifest=db_rows("SELECT * FROM history_import_manifest_v13 ORDER BY source_year,source_file")
    years=db_rows("""SELECT year,COUNT(*) games,COUNT(DISTINCT series_key) series_count
                     FROM (
                       SELECT g.year,g.game_key,s.series_key
                       FROM lck_alltime_games_v13 g
                       LEFT JOIN lck_alltime_series_v13 s ON s.year=g.year
                     ) GROUP BY year ORDER BY year""")
    base=db_one("""SELECT MIN(year) min_year,MAX(year) max_year,COUNT(*) series_count
                   FROM match_archive_v11""") or {}
    alltime=db_one("""SELECT MIN(year) min_year,MAX(year) max_year,COUNT(*) series_count
                      FROM lck_alltime_series_v13""") or {}
    return {
      "bundled_history":{"min_year":base.get("min_year"),"max_year":base.get("max_year"),
                         "series":base.get("series_count")},
      "imported_alltime":{"min_year":alltime.get("min_year"),"max_year":alltime.get("max_year"),
                          "series":alltime.get("series_count")},
      "manifest":manifest,
      "policy":db_rows("SELECT * FROM history_license_policy_v13 ORDER BY source"),
      "status":"READY_FOR_LOCAL_FILES"
    }


# ---------------------------------------------------------------------------
# V14 — Strategic Draft Layer
# ---------------------------------------------------------------------------
PICK_ORDER_V14=["B1","R1","R2","B2","B3","R3","R4","B4","B5","R5"]
BAN_ORDER_V14=["B1BAN","R1BAN","B2BAN","R2BAN","B3BAN","R3BAN","R4BAN","B4BAN","R5BAN","B5BAN"]

def _v14_blue_is_a(payload):
    return str(payload.get("side_a","Blue")).lower()=="blue"

def _v14_slot_target_side(payload,slot):
    blue_is_a=_v14_blue_is_a(payload)
    token=str(slot or "").upper()
    if token.startswith("B"):
        return "a" if blue_is_a else "b"
    if token.startswith("R"):
        return "b" if blue_is_a else "a"
    return None

def _v14_slot_index(slot):
    slot=str(slot or "").upper()
    if slot in PICK_ORDER_V14:return PICK_ORDER_V14.index(slot)
    if slot in BAN_ORDER_V14:return BAN_ORDER_V14.index(slot)
    return 99

def _v14_flex_profile(champion):
    row=db_one("SELECT * FROM champion_flex_profile_v14 WHERE champion=?",(champion,))
    if not row:return {"role_count":1,"flex_score":0.0,"roles":{}}
    try:roles=json.loads(row.get("roles_json") or "{}")
    except:roles={}
    return {**row,"roles":roles}

def _v14_player_mastery(player,champion):
    row=db_one("""SELECT games,wins,winrate,smoothed_winrate,kda,gd15
                  FROM draft_player_champion
                  WHERE player=? AND champion=? AND scope='2026' LIMIT 1""",(player,champion))
    if not row:
        row=db_one("""SELECT games,wins,winrate,smoothed_winrate,kda,gd15
                      FROM draft_player_champion
                      WHERE player=? AND champion=? AND scope='local_2025_2026' LIMIT 1""",(player,champion))
    return row

def _v14_role_meta(champion,role):
    return db_one("""SELECT games,wins,winrate,smoothed_winrate,gd15
                     FROM draft_champion_meta
                     WHERE champion=? AND role=? AND scope='2026' LIMIT 1""",(champion,role))

def _v14_opponent_denial(team,champion,used_keys=None):
    used_keys=used_keys or set()
    rows=db_rows("""SELECT r.player,r.role,
                           COALESCE(pc.games,0) games,
                           COALESCE(pc.smoothed_winrate,0.5) mastery
                    FROM draft_rosters r
                    LEFT JOIN draft_player_champion pc
                      ON pc.player=r.player AND pc.champion=? AND pc.scope='2026'
                    WHERE r.team=?""",(champion,team))
    best=None
    for r in rows:
        # Compare candidate mastery with the player's next-best available pool.
        pool=db_rows("""SELECT champion,games,smoothed_winrate
                        FROM draft_player_champion
                        WHERE player=? AND scope='2026'
                        ORDER BY games DESC,smoothed_winrate DESC LIMIT 12""",(r["player"],))
        alternatives=[x for x in pool if _champ_key_v10(x["champion"]) not in used_keys and _champ_key_v10(x["champion"])!=_champ_key_v10(champion)]
        alt=max([float(x.get("smoothed_winrate") or .5) for x in alternatives],default=.5)
        mastery=float(r.get("mastery") or .5)
        games=int(r.get("games") or 0)
        support=min(1,games/10)
        gap=max(0,mastery-alt)
        score=(gap*100)*support
        item={"player":r["player"],"role":r["role"],"games":games,"mastery":mastery,
              "next_best_mastery":alt,"denial_pp_equiv":score}
        if best is None or item["denial_pp_equiv"]>best["denial_pp_equiv"]:
            best=item
    return best or {"player":None,"role":None,"games":0,"mastery":.5,"next_best_mastery":.5,"denial_pp_equiv":0.0}

def _v14_future_pool_cost(player,role,champion,used_keys,fearless_keys,remaining_maps=1):
    current=_v14_player_mastery(player,champion) or {}
    cur=float(current.get("smoothed_winrate") or .5)
    games=int(current.get("games") or 0)
    pool=db_rows("""SELECT champion,games,smoothed_winrate
                    FROM draft_player_champion
                    WHERE player=? AND scope='2026'
                    ORDER BY games DESC,smoothed_winrate DESC LIMIT 20""",(player,))
    alternatives=[]
    for r in pool:
        ck=_champ_key_v10(r["champion"])
        if ck in used_keys or ck in fearless_keys or ck==_champ_key_v10(champion):continue
        alternatives.append(r)
    alt=max([float(x.get("smoothed_winrate") or .5) for x in alternatives],default=.5)
    comfort_gap=max(0,cur-alt)
    evidence=min(1,games/10)
    # Cost is pp-equivalent, capped, and scaled by expected future maps.
    cost=min(4.0,comfort_gap*100*evidence*0.55)*min(2,max(0,remaining_maps))
    return {"cost_pp_equiv":cost,"current_mastery":cur,"next_best_mastery":alt,
            "player_games":games,"remaining_maps":remaining_maps}

def _v14_pick_information_weight(slot):
    idx=_v14_slot_index(slot)
    # Flex is more valuable when picked earlier because it preserves hidden role information.
    if idx<=0:return 1.00
    if idx<=2:return .85
    if idx<=5:return .55
    if idx<=7:return .30
    return .10

def _v14_expected_future_maps(payload,current_probability_team_a=.5):
    """Expected number of maps AFTER the current map in a Bo3."""
    if payload.get("expected_future_maps") is not None:
        try:return max(0.0,min(1.5,float(payload["expected_future_maps"])))
        except:return 0.0
    game_number=int(payload.get("game_number") or 1)
    q=max(.01,min(.99,float(current_probability_team_a or .5)))
    if game_number<=1:
        # Game 2 is guaranteed; Game 3 happens if first two maps split.
        return 1.0 + 2.0*q*(1.0-q)
    if game_number==2:
        sa=payload.get("series_score_a"); sb=payload.get("series_score_b")
        try:sa=int(sa);sb=int(sb)
        except:sa=sb=None
        if sa==1 and sb==0:
            return 1.0-q       # G3 only if team A loses G2
        if sa==0 and sb==1:
            return q           # G3 only if team A wins G2
        return .5              # unknown score: neutral fallback
    return 0.0

def draft_strategy_pick_v14(payload):
    slot=str(payload.get("pick_slot") or "").upper()
    if slot not in PICK_ORDER_V14:
        return {"error":"pick_slot inválido."}
    target_side=_v14_slot_target_side(payload,slot)
    if not target_side:
        return {"error":"Não consegui resolver o lado desse pick."}
    role=str(payload.get("target_role") or "").lower()
    if role not in ("top","jng","mid","bot","sup"):
        return {"error":"target_role inválida."}

    base=dict(payload)
    base["target_side"]=target_side
    base["target_role"]=role
    base["limit"]=max(12,int(payload.get("candidate_pool_limit") or 16))
    raw=draft_recommend_v13(base)
    if raw.get("error"):return raw

    a=raw["team_a"];b=raw["team_b"]
    target_team=raw["target_team"]
    opponent=b if target_team==a else a
    used=_v13_pick_set(payload)
    fearless_keys={_champ_key_v10(x) for x in (payload.get("fearless_used") or [])}
    expected_future_maps=_v14_expected_future_maps(payload,raw.get("current_probability_team_a"))
    info_weight=_v14_pick_information_weight(slot)
    current_target=float(raw["current_probability_target_team"])

    out=[]
    for c in raw["candidates"]:
        champ=c["champion"]
        flex=_v14_flex_profile(champ)
        flex_bonus=float(flex.get("flex_score") or 0)*1.25*info_weight  # pp-equivalent
        denial=_v14_opponent_denial(opponent,champ,used|fearless_keys)
        own_games=int(c.get("player_games") or 0)
        own_familiarity=0.20+0.80*min(1,own_games/8)
        # Taking an opponent comfort is only strategically valuable if our own
        # player has enough evidence to plausibly use the champion.
        denial_bonus=min(1.5,float(denial.get("denial_pp_equiv") or 0)*0.25*own_familiarity)
        pool_cost=_v14_future_pool_cost(raw["player"],role,champ,used,fearless_keys,expected_future_maps)
        # Start from V13 evidence-adjusted delta, then strategic overlays.
        immediate_delta=float(c["decision_delta_target_pp"])
        strategy_delta=immediate_delta + flex_bonus + denial_bonus - float(pool_cost["cost_pp_equiv"])
        strategy_score=max(.01,min(.99,current_target+strategy_delta/100))
        out.append({
          **c,
          "pick_slot":slot,
          "target_role":role,
          "flex_score":float(flex.get("flex_score") or 0),
          "flex_roles":flex.get("roles") or {},
          "flex_bonus_pp_equiv":flex_bonus,
          "denial":denial,
          "own_familiarity_for_denial":own_familiarity,
          "denial_bonus_pp_equiv":denial_bonus,
          "future_pool":pool_cost,
          "future_pool_cost_pp_equiv":float(pool_cost["cost_pp_equiv"]),
          "strategy_delta_pp_equiv":strategy_delta,
          "strategy_score":strategy_score,
          "strategy_status":"EXPERIMENTAL"
        })

    out.sort(key=lambda x:(x["strategy_score"],x["decision_probability_target_team"],x["evidence_confidence"]),reverse=True)
    top=out[:int(payload.get("limit") or 8)]

    try:
        with db_connect() as con:
            now=datetime.now(timezone.utc).isoformat()
            picks_json=json.dumps({"a":payload.get("picks_a") or {},"b":payload.get("picks_b") or {}},ensure_ascii=False,separators=(",",":"))
            bans_json=json.dumps(payload.get("bans") or [],ensure_ascii=False,separators=(",",":"))
            fearless_json=json.dumps(payload.get("fearless_used") or [],ensure_ascii=False,separators=(",",":"))
            for x in top:
                con.execute("""INSERT INTO draft_strategy_log_v14
                  (created_at,team_a,team_b,side_a,patch,action_type,pick_slot,target_side,target_role,candidate,
                   immediate_probability_team_a,immediate_delta_target_pp,series_adjusted_score,series_adjusted_delta_pp,
                   future_pool_cost,flex_value,denial_value,evidence_confidence,player,fearless_json,picks_json,bans_json,
                   recommendation_status,model_version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (now,a,b,payload.get("side_a","Blue"),payload.get("patch"),"PICK",slot,target_side,role,x["champion"],
                   x["probability_team_a"],x["decision_delta_target_pp"],x["strategy_score"],x["strategy_delta_pp_equiv"],
                   x["future_pool_cost_pp_equiv"],x["flex_bonus_pp_equiv"],x["denial_bonus_pp_equiv"],
                   x["evidence_confidence"],raw["player"],fearless_json,picks_json,bans_json,
                   "EXPERIMENTAL_STRATEGY","V14 over V8/V13"))
            con.commit()
    except Exception:
        pass

    return {
      "team_a":a,"team_b":b,"target_team":target_team,"target_side":target_side,"target_role":role,
      "player":raw["player"],"pick_slot":slot,"current_probability_target_team":current_target,
      "expected_future_maps":expected_future_maps,
      "status":"EXPERIMENTAL_STRATEGY",
      "note":"Strategy score is not a calibrated win probability. It combines the evidence-shrunk V13 delta with flex, denial and future-pool cost to rank decisions.",
      "candidates":top
    }

def _v14_ban_candidate_pool(opponent_team,unfilled_roles,used_keys,fearless_keys,limit=50):
    vals={}
    roster=db_rows("SELECT player,role FROM draft_rosters WHERE team=?",(opponent_team,))
    for r in roster:
        if unfilled_roles and r["role"] not in unfilled_roles:continue
        pool=db_rows("""SELECT champion,games,smoothed_winrate,winrate,gd15
                        FROM draft_player_champion
                        WHERE player=? AND scope='2026'
                        ORDER BY games DESC,smoothed_winrate DESC LIMIT 15""",(r["player"],))
        for p in pool:
            ck=_champ_key_v10(p["champion"])
            if ck in used_keys or ck in fearless_keys:continue
            k=p["champion"]
            item=vals.setdefault(k,{"champion":k,"targets":[]})
            item["targets"].append({"player":r["player"],"role":r["role"],**p})
    # Add strong role-meta champions that may be new/low sample for player.
    for role in unfilled_roles or ["top","jng","mid","bot","sup"]:
        for m in db_rows("""SELECT champion,games,smoothed_winrate,gd15
                            FROM draft_champion_meta
                            WHERE role=? AND scope='2026'
                            ORDER BY games DESC,smoothed_winrate DESC LIMIT 10""",(role,)):
            ck=_champ_key_v10(m["champion"])
            if ck in used_keys or ck in fearless_keys:continue
            vals.setdefault(m["champion"],{"champion":m["champion"],"targets":[]})
    return list(vals.values())[:limit]

def draft_ban_strategy_v14(payload):
    slot=str(payload.get("ban_slot") or "").upper()
    if slot not in BAN_ORDER_V14:
        return {"error":"ban_slot inválido."}
    banning_side=_v14_slot_target_side(payload,slot)
    if not banning_side:return {"error":"Não consegui resolver o lado do ban."}
    a=str(payload.get("team_a","")).upper();b=str(payload.get("team_b","")).upper()
    banning_team=a if banning_side=="a" else b
    opponent=b if banning_team==a else a

    picks_a=payload.get("picks_a") or {};picks_b=payload.get("picks_b") or {}
    opponent_picks=picks_b if opponent==b else picks_a
    used=_v13_pick_set(payload)
    banned={_champ_key_v10(x) for x in (payload.get("bans") or [])}
    fearless={_champ_key_v10(x) for x in (payload.get("fearless_used") or [])}
    used_all=used|banned

    unfilled=[r for r in ("top","jng","mid","bot","sup") if not opponent_picks.get(r)]
    candidates=_v14_ban_candidate_pool(opponent,unfilled,used_all,fearless,60)
    scored=[]
    for item in candidates:
        champ=item["champion"]
        flex=_v14_flex_profile(champ)
        # Best target among opponent roster.
        best_target=None
        targets=item.get("targets") or []
        for t in targets:
            mastery=float(t.get("smoothed_winrate") or .5)
            games=int(t.get("games") or 0)
            support=min(1,games/10)
            comfort=max(0,mastery-.5)*100*support
            cand={**t,"comfort_value":comfort}
            if best_target is None or cand["comfort_value"]>best_target["comfort_value"]:best_target=cand
        if best_target is None:
            # Meta-only candidate
            best_role=None;best_meta=None
            for role in unfilled:
                m=_v14_role_meta(champ,role)
                if m and (best_meta is None or int(m.get("games") or 0)>int(best_meta.get("games") or 0)):
                    best_meta=m;best_role=role
            best_target={"player":_v13_player_for(opponent,best_role) if best_role else None,
                         "role":best_role,"games":0,"smoothed_winrate":.5,"comfort_value":0}
        meta=_v14_role_meta(champ,best_target.get("role")) if best_target.get("role") else None
        meta_games=int((meta or {}).get("games") or 0)
        meta_wr=float((meta or {}).get("smoothed_winrate") or .5)
        meta_value=max(0,meta_wr-.5)*100*min(1,meta_games/18)
        flex_value=float(flex.get("flex_score") or 0)*12
        # Scarcity = strong champion in a role with few high-volume alternatives for opponent player.
        player=best_target.get("player")
        scarcity=0
        if player:
            pool=db_rows("""SELECT champion,games,smoothed_winrate FROM draft_player_champion
                            WHERE player=? AND scope='2026' ORDER BY games DESC LIMIT 8""",(player,))
            viable=sum(1 for p in pool if int(p.get("games") or 0)>=4 and float(p.get("smoothed_winrate") or .5)>=.5
                       and _champ_key_v10(p["champion"]) not in used_all|fearless)
            scarcity=max(0,6-viable)*1.3
        total=0.50*best_target["comfort_value"]+0.25*meta_value+0.15*flex_value+0.10*scarcity
        evidence=min(100,round(35+min(35,int(best_target.get("games") or 0)*3)+min(20,meta_games)+min(10,float(flex.get("role_count") or 1)*2)))
        scored.append({
          "champion":champ,"ban_priority_score":total,"target_player":best_target.get("player"),
          "target_role":best_target.get("role"),"player_games":int(best_target.get("games") or 0),
          "player_mastery":float(best_target.get("smoothed_winrate") or .5),
          "meta_games":meta_games,"meta_wr":meta_wr,"flex_score":float(flex.get("flex_score") or 0),
          "role_count":int(flex.get("role_count") or 1),"scarcity_value":scarcity,
          "evidence_confidence":evidence,"status":"EXPERIMENTAL_BAN_POLICY"
        })
    scored.sort(key=lambda x:(x["ban_priority_score"],x["evidence_confidence"]),reverse=True)
    top=scored[:int(payload.get("limit") or 10)]
    mx=max([float(x["ban_priority_score"]) for x in top],default=1.0) or 1.0
    for x in top:
        x["relative_priority"]=100*float(x["ban_priority_score"])/mx
    return {
      "team_a":a,"team_b":b,"ban_slot":slot,"banning_team":banning_team,"opponent_team":opponent,
      "unfilled_opponent_roles":unfilled,"status":"EXPERIMENTAL_BAN_POLICY",
      "note":"Ban priority is a strategic score, not a win probability. It combines opponent comfort denial, meta strength, flex value and pool scarcity.",
      "candidates":top
    }

def draft_sequence_v14(payload):
    """Return resolved team/action order for the standard pro draft."""
    blue_a=_v14_blue_is_a(payload)
    def team_for(token):
        blue=token.startswith("B")
        return payload.get("team_a") if blue==blue_a else payload.get("team_b")
    return {
      "pick_order":[{"slot":x,"team":team_for(x),"side":"Blue" if x.startswith("B") else "Red"} for x in PICK_ORDER_V14],
      "ban_order":[{"slot":x,"team":team_for(x),"side":"Blue" if x.startswith("B") else "Red"} for x in BAN_ORDER_V14]
    }


def series_context_v14(event_id,game_number=None):
    ev=db_one("SELECT * FROM riot_events_v10 WHERE event_id=?",(str(event_id),))
    if not ev:
        return {"error":"Evento Riot não encontrado no cache."}
    a=canonical(ev.get("team_a")) or ev.get("team_a_code") or ev.get("team_a")
    b=canonical(ev.get("team_b")) or ev.get("team_b_code") or ev.get("team_b")
    if game_number is None:
        try:
            game_number=int(ev.get("score_a") or 0)+int(ev.get("score_b") or 0)+1
        except:
            game_number=1
    game_number=max(1,int(game_number))
    prior=db_rows("""SELECT game_number,blue_team,red_team,winner,draft_json
                     FROM riot_games_v10
                     WHERE event_id=? AND game_number<?
                     ORDER BY game_number""",(str(event_id),game_number))
    used=[]
    prior_games=[]
    for g in prior:
        try:d=json.loads(g.get("draft_json") or "{}")
        except:d={}
        picks=[]
        for side in ("blue","red"):
            vals=list(((d.get(side) or {}).get("picks") or {}).values())
            picks.extend([x for x in vals if x])
            used.extend([x for x in vals if x])
        prior_games.append({"game_number":g["game_number"],"blue_team":g["blue_team"],"red_team":g["red_team"],
                            "winner":g["winner"],"champions":picks})
    current=db_one("""SELECT game_number,blue_team,red_team,state,patch
                      FROM riot_games_v10 WHERE event_id=? AND game_number=? LIMIT 1""",
                   (str(event_id),game_number))
    side_a=None
    if current:
        if canonical(current.get("blue_team"))==a or current.get("blue_team")==a:side_a="Blue"
        elif canonical(current.get("red_team"))==a or current.get("red_team")==a:side_a="Red"
    return {
      "event_id":str(event_id),"team_a":a,"team_b":b,"game_number":game_number,
      "score_a":ev.get("score_a"),"score_b":ev.get("score_b"),
      "fearless_used":sorted(set(used)),"previous_games":prior_games,
      "current_game":current,"side_a":side_a,
      "note":"Fearless context includes champions picked by either team in earlier maps of the same series."
    }


# ---------------------------------------------------------------------------
# V15 — Draft Tree / Minimax + Flex Resolver
# ---------------------------------------------------------------------------
def _v15_copy_picks(payload):
    return {"a":dict(payload.get("picks_a") or {}),"b":dict(payload.get("picks_b") or {})}

def _v15_side_for_slot(payload,slot):
    return _v14_slot_target_side(payload,slot)

def _v15_team_for_side(payload,side):
    return str(payload.get("team_a","")).upper() if side=="a" else str(payload.get("team_b","")).upper()

def _v15_unfilled_roles(picks):
    return [r for r in ("top","jng","mid","bot","sup") if not picks.get(r)]

def _v15_used_keys(payload,picks):
    vals=[]
    for side in ("a","b"):
        vals.extend([x for x in picks[side].values() if x])
    vals.extend(payload.get("bans") or [])
    return {_champ_key_v10(x) for x in vals}

def _v15_state_key(payload,picks):
    def norm(d):
        return tuple((r,str(d.get(r) or "")) for r in ("top","jng","mid","bot","sup"))
    return (str(payload.get("team_a")),str(payload.get("team_b")),str(payload.get("side_a")),
            str(payload.get("patch")),norm(picks["a"]),norm(picks["b"]),
            tuple(sorted(_champ_key_v10(x) for x in (payload.get("fearless_used") or []))))

def _v15_eval_cached(payload,picks,cache):
    key=_v15_state_key(payload,picks)
    if key in cache:return cache[key]
    ev=evaluate_draft({
      "team_a":payload.get("team_a"),"team_b":payload.get("team_b"),"side_a":payload.get("side_a","Blue"),
      "patch":payload.get("patch"),"picks_a":picks["a"],"picks_b":picks["b"],
      "fearless_used":payload.get("fearless_used") or []
    })
    cache[key]=ev
    return ev

def _v15_candidate_actions(payload,picks,slot,acting_side,role=None,candidates_per_role=2,branch_width=4,cache=None,evaluate_actions=True):
    cache=cache if cache is not None else {}
    a=str(payload.get("team_a","")).upper(); b=str(payload.get("team_b","")).upper()
    team=a if acting_side=="a" else b
    opponent=b if acting_side=="a" else a
    fearless={_champ_key_v10(x) for x in (payload.get("fearless_used") or [])}
    used=_v15_used_keys(payload,picks)
    roles=[role] if role else _v15_unfilled_roles(picks[acting_side])

    if evaluate_actions:
        current_ev=_v15_eval_cached(payload,picks,cache)
        current_pa=float(current_ev.get("draft_game_probability_team_a") or .5)
        current_target=current_pa if acting_side=="a" else 1-current_pa
    else:
        current_pa=.5
        current_target=.5
    expected_future=_v14_expected_future_maps(payload,current_pa)
    info_weight=_v14_pick_information_weight(slot)

    # Stage 1: cheap shortlist. Do NOT run V8 on every champion.
    shortlist=[]
    pre_per_role=max(2,int(candidates_per_role))
    for r in roles:
        player=_v13_player_for(team,r)
        if not player:continue
        pool=_v13_candidate_pool(player,r,18)
        cheap=[]
        for item in pool:
            champ=item["champion"]; ck=_champ_key_v10(champ)
            if ck in used or ck in fearless:continue
            pr=item.get("player_row") or {}; mr=item.get("meta_row") or {}
            pg=int(pr.get("games") or 0); mg=int(mr.get("games") or 0)
            pe=float(pr.get("smoothed_winrate") or .5); me=float(mr.get("smoothed_winrate") or .5)
            p_support=min(1,pg/8); m_support=min(1,mg/18)
            flex=float((_v14_flex_profile(champ) or {}).get("flex_score") or 0)
            cheap_score=.58*(pe-.5)*p_support + .27*(me-.5)*m_support + .015*flex + .002*min(pg,12)
            cheap.append((cheap_score,item,player))
        cheap.sort(key=lambda x:x[0],reverse=True)
        shortlist.extend([(r,*x) for x in cheap[:pre_per_role]])

    # If multiple roles are still open, keep only the most plausible actions before expensive evaluation.
    shortlist.sort(key=lambda x:x[1],reverse=True)
    expensive_cap=max(int(branch_width)*2,pre_per_role) if role is None else max(int(branch_width),pre_per_role)
    shortlist=shortlist[:expensive_cap]

    actions=[]
    for r,cheap_score,item,player in shortlist:
        champ=item["champion"]
        pr=item.get("player_row") or {}; mr=item.get("meta_row") or {}
        pg=int(pr.get("games") or 0); mg=int(mr.get("games") or 0)
        flex=_v14_flex_profile(champ)
        flex_bonus=float(flex.get("flex_score") or 0)*1.25*info_weight

        if not evaluate_actions:
            # Beam ordering only. V8 is intentionally deferred to leaves.
            heuristic=.5 + cheap_score + .004*flex_bonus
            actions.append({
              "slot":slot,"side":acting_side,"team":team,"role":r,"player":player,"champion":champ,
              "probability_team_a":None,"probability_acting_team":None,
              "decision_delta_pp":None,"strategic_delta_pp_equiv":None,
              "action_utility":heuristic,"evidence_confidence":round(30+min(35,pg*4)+min(25,mg)),
              "player_games":pg,"meta_games":mg,"flex_score":float(flex.get("flex_score") or 0),
              "flex_bonus_pp_equiv":flex_bonus,"denial_bonus_pp_equiv":None,
              "future_pool_cost_pp_equiv":None,"cheap_score":cheap_score,"beam_heuristic_only":True
            })
            continue

        np={"a":dict(picks["a"]),"b":dict(picks["b"])}
        np[acting_side][r]=champ
        ev=_v15_eval_cached(payload,np,cache)
        if ev.get("error"):continue
        pa=float(ev["draft_game_probability_team_a"])
        target=pa if acting_side=="a" else 1-pa
        confidence=int(ev.get("evidence_confidence") or 0)
        familiarity=min(pg,12)/12
        meta_support=min(mg,20)/20
        policy_conf=min(1.0,max(.25,.35+.30*familiarity+.20*meta_support+.15*(confidence/100)))
        decision_delta=(target-current_target)*100*policy_conf
        denial=_v14_opponent_denial(opponent,champ,used|fearless)
        own_fam=.20+.80*min(1,pg/8)
        denial_bonus=min(1.5,float(denial.get("denial_pp_equiv") or 0)*.25*own_fam)
        future=_v14_future_pool_cost(player,r,champ,used,fearless,expected_future)
        strategic_delta=decision_delta+flex_bonus+denial_bonus-float(future["cost_pp_equiv"])
        action_utility=max(.01,min(.99,current_target+strategic_delta/100))
        actions.append({
          "slot":slot,"side":acting_side,"team":team,"role":r,"player":player,"champion":champ,
          "probability_team_a":pa,"probability_acting_team":target,
          "decision_delta_pp":decision_delta,"strategic_delta_pp_equiv":strategic_delta,
          "action_utility":action_utility,"evidence_confidence":confidence,
          "player_games":pg,"meta_games":mg,"flex_score":float(flex.get("flex_score") or 0),
          "flex_bonus_pp_equiv":flex_bonus,"denial_bonus_pp_equiv":denial_bonus,
          "future_pool_cost_pp_equiv":float(future["cost_pp_equiv"]),"cheap_score":cheap_score
        })
    actions.sort(key=lambda x:(x["action_utility"],x["evidence_confidence"]),reverse=True)
    return actions[:int(branch_width)]

def _v15_apply_action(picks,action):
    out={"a":dict(picks["a"]),"b":dict(picks["b"])}
    out[action["side"]][action["role"]]=action["champion"]
    return out

def _v15_leaf(payload,picks,root_side,cache=None):
    cache=cache if cache is not None else {}
    ev=_v15_eval_cached(payload,picks,cache)
    pa=float(ev.get("draft_game_probability_team_a") or .5)
    return {
      "probability_team_a":pa,
      "probability_root_team":pa if root_side=="a" else 1-pa,
      "evidence_confidence":int(ev.get("evidence_confidence") or 0)
    }

def _v15_next_slot(root_slot,offset):
    i=PICK_ORDER_V14.index(root_slot)+offset
    return PICK_ORDER_V14[i] if 0<=i<len(PICK_ORDER_V14) else None

def _v15_minimax(payload,picks,root_side,root_slot,offset,depth,branch_width,candidates_per_role,stats,cache):
    stats["nodes"]+=1
    if offset>=depth:
        leaf=_v15_leaf(payload,picks,root_side,cache)
        return leaf["probability_root_team"],[],leaf
    slot=_v15_next_slot(root_slot,offset)
    if not slot:
        leaf=_v15_leaf(payload,picks,root_side,cache)
        return leaf["probability_root_team"],[],leaf
    acting=_v15_side_for_slot(payload,slot)
    actions=_v15_candidate_actions(payload,picks,slot,acting,None,candidates_per_role,branch_width,cache,False)
    if not actions:
        leaf=_v15_leaf(payload,picks,root_side,cache)
        return leaf["probability_root_team"],[],leaf

    maximizing=(acting==root_side)
    best_val=None;best_path=None;best_leaf=None
    for act in actions:
        np=_v15_apply_action(picks,act)
        val,path,leaf=_v15_minimax(payload,np,root_side,root_slot,offset+1,depth,branch_width,candidates_per_role,stats,cache)
        if best_val is None or (maximizing and val>best_val) or ((not maximizing) and val<best_val):
            best_val=val;best_path=[act]+path;best_leaf=leaf
    return best_val,best_path,best_leaf

def draft_tree_v15(payload):
    import time
    t0=time.perf_counter()
    root_slot=str(payload.get("root_slot") or "").upper()
    if root_slot not in PICK_ORDER_V14:return {"error":"root_slot inválido."}
    root_role=str(payload.get("root_role") or "").lower()
    if root_role not in ("top","jng","mid","bot","sup"):return {"error":"root_role inválida."}
    depth=max(2,min(4,int(payload.get("depth") or 3)))
    branch=max(2,min(5,int(payload.get("branch_width") or 2)))
    per_role=max(1,min(4,int(payload.get("candidates_per_role") or 2)))
    estimated_leaves=max(4,branch)*(branch**max(0,depth-1))
    if estimated_leaves>80:
        return {"error":f"Árvore estimada em {estimated_leaves} leaves. Reduza beam/profundidade; limite seguro desta build = 80."}
    root_side=_v15_side_for_slot(payload,root_slot)
    root_team=_v15_team_for_side(payload,root_side)
    picks=_v15_copy_picks(payload)

    cache={}
    current=_v15_leaf(payload,picks,root_side,cache)
    root_count=max(4,branch)
    root_actions=_v15_candidate_actions(payload,picks,root_slot,root_side,root_role,root_count,root_count,cache,True)
    if not root_actions:return {"error":"Nenhuma ação legal encontrada para a raiz."}

    results=[];stats={"nodes":0}
    for act in root_actions:
        np=_v15_apply_action(picks,act)
        # Root action is action 1; recursion starts at the next slot.
        val,path,leaf=_v15_minimax(payload,np,root_side,root_slot,1,depth,branch,per_role,stats,cache)
        immediate=act["probability_acting_team"]
        results.append({
          "root_action":act,
          "immediate_probability_root":immediate,
          "minimax_probability_root":val,
          "robust_delta_vs_current_pp":(val-current["probability_root_team"])*100,
          "response_penalty_pp":(immediate-val)*100,
          "principal_variation":[act]+path,
          "leaf":leaf
        })

    results.sort(key=lambda x:(x["minimax_probability_root"],x["root_action"]["evidence_confidence"]),reverse=True)
    elapsed=(time.perf_counter()-t0)*1000
    out={
      "team_a":str(payload.get("team_a","")).upper(),"team_b":str(payload.get("team_b","")).upper(),
      "root_slot":root_slot,"root_role":root_role,"root_side":root_side,"root_team":root_team,
      "depth":depth,"branch_width":branch,"candidates_per_role":per_role,"estimated_leaf_budget":estimated_leaves,
      "current_probability_root":current["probability_root_team"],
      "nodes_evaluated":stats["nodes"],"model_states_evaluated":len(cache),"elapsed_ms":elapsed,
      "status":"EXPERIMENTAL_MINIMAX",
      "note":"Minimax probability is a model-based robustness score under the modeled best-response tree. It is not independently calibrated as a new probability product.",
      "results":results[:int(payload.get("limit") or 6)]
    }
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO draft_tree_runs_v15
              (created_at,team_a,team_b,side_a,patch,game_number,root_slot,root_role,depth,branch_width,
               candidates_per_role,root_team,current_probability_root,result_json,nodes_evaluated,elapsed_ms,status,model_version)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (datetime.now(timezone.utc).isoformat(),out["team_a"],out["team_b"],payload.get("side_a","Blue"),
               payload.get("patch"),int(payload.get("game_number") or 1),root_slot,root_role,depth,branch,per_role,
               root_team,out["current_probability_root"],json.dumps(out["results"],ensure_ascii=False,separators=(",",":")),
               out["nodes_evaluated"],elapsed,out["status"],"V15 beam/minimax over V8"))
            con.commit()
    except Exception:pass
    return out

def _v15_role_allowed(champion,role,player=None):
    flex=_v14_flex_profile(champion)
    role_games=int((flex.get("roles") or {}).get(role,0))
    pr=_v14_player_mastery(player,champion) if player else None
    player_games=int((pr or {}).get("games") or 0)
    return role_games>0 or player_games>0

def flex_resolve_v15(payload):
    team=str(payload.get("team","")).upper()
    champs=[canonical_champion_v10(x) for x in (payload.get("champions") or []) if x]
    if not team or not champs:return {"error":"Informe time e champions."}
    if len(champs)>5:return {"error":"Máximo de 5 champions."}
    fixed=dict(payload.get("fixed_roles") or {})
    roster={r["role"]:r["player"] for r in db_rows("SELECT role,player FROM draft_rosters WHERE team=?",(team,))}
    roles=["top","jng","mid","bot","sup"]
    solutions=[]

    def rec(i,assign,used_roles,score,evidence):
        if i>=len(champs):
            solutions.append({"assignment":dict(assign),"score":score,"evidence":evidence})
            return
        champ=champs[i]
        forced=fixed.get(champ)
        candidates=[forced] if forced else [r for r in roles if r not in used_roles]
        for role in candidates:
            if not role or role in used_roles:continue
            player=roster.get(role)
            if not player:continue
            if not _v15_role_allowed(champ,role,player):continue
            pr=_v14_player_mastery(player,champ) or {}
            meta=_v14_role_meta(champ,role) or {}
            pg=int(pr.get("games") or 0); mg=int(meta.get("games") or 0)
            mastery=float(pr.get("smoothed_winrate") or .5)
            meta_wr=float(meta.get("smoothed_winrate") or .5)
            support=min(1,pg/8)
            m_support=min(1,mg/15)
            local_score=.70*(mastery-.5)*support+.30*(meta_wr-.5)*m_support
            local_evidence=min(100,30+pg*5+min(25,mg))
            assign[role]={"champion":champ,"player":player,"player_games":pg,"meta_games":mg,
                          "mastery":mastery,"meta_wr":meta_wr}
            rec(i+1,assign,used_roles|{role},score+local_score,evidence+[local_evidence])
            assign.pop(role,None)

    rec(0,{},set(),0,[])
    solutions.sort(key=lambda x:(x["score"],sum(x["evidence"])/max(1,len(x["evidence"]))),reverse=True)
    for x in solutions:
        x["evidence_confidence"]=round(sum(x["evidence"])/max(1,len(x["evidence"])))
        x["score_pp_equiv"]=x["score"]*100
        x.pop("evidence",None)
    out={
      "team":team,"champions":champs,"status":"EXPERIMENTAL_FLEX_RESOLVER",
      "assignment_count":len(solutions),
      "note":"Resolver enumerates plausible role assignments from observed player/meta usage. Score is relative assignment support, not win probability.",
      "assignments":solutions[:int(payload.get("limit") or 8)]
    }
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO flex_resolution_log_v15
              (created_at,team,champions_json,used_json,result_json,assignment_count,status)
              VALUES(?,?,?,?,?,?,?)""",
              (datetime.now(timezone.utc).isoformat(),team,json.dumps(champs,ensure_ascii=False),
               json.dumps(fixed,ensure_ascii=False),json.dumps(out["assignments"],ensure_ascii=False,separators=(",",":")),
               len(solutions),out["status"]))
            con.commit()
    except Exception:pass
    return out


# ---------------------------------------------------------------------------
# V16 — Flex-aware Draft Tree
# ---------------------------------------------------------------------------
def _v16_bound_picks(payload):
    return {"a":dict(payload.get("picks_a") or {}),"b":dict(payload.get("picks_b") or {})}

def _v16_unbound(payload):
    return {"a":list(payload.get("unbound_a") or []),"b":list(payload.get("unbound_b") or [])}

def _v16_used_keys(payload,bound,unbound):
    vals=[]
    for side in ("a","b"):
        vals += [x for x in bound[side].values() if x]
        vals += [x for x in unbound[side] if x]
    vals += list(payload.get("bans") or [])
    return {_champ_key_v10(x) for x in vals}

def _v16_possible_roles_for(team,champion,bound_roles=None):
    bound_roles=set(bound_roles or [])
    flex=_v14_flex_profile(champion)
    roles=[]
    for role in ("top","jng","mid","bot","sup"):
        if role in bound_roles: continue
        player=_v13_player_for(team,role)
        if not player: continue
        role_games=int((flex.get("roles") or {}).get(role,0))
        mastery=_v14_player_mastery(player,champion) or {}
        pg=int(mastery.get("games") or 0)
        meta=_v14_role_meta(champion,role) or {}
        mg=int(meta.get("games") or 0)
        if role_games>0 or pg>0 or mg>=3:
            score=.55*min(1,pg/8)+.30*min(1,mg/15)+.15*min(1,role_games/15)
            roles.append({"role":role,"player":player,"player_games":pg,"meta_games":mg,"support":score})
    roles.sort(key=lambda x:x["support"],reverse=True)
    return roles

def _v16_assignment_states(team,bound,unbound,limit=4):
    fixed={r:c for r,c in bound.items() if c}
    states=[]
    def rec(i,assign,score,evidence):
        if i>=len(unbound):
            full=dict(fixed);full.update({r:v["champion"] for r,v in assign.items()})
            states.append({"picks":full,"assign":dict(assign),"score":score,
                           "evidence":round(sum(evidence)/max(1,len(evidence))) if evidence else 100})
            return
        champ=unbound[i]
        occupied=set(fixed)|set(assign)
        candidates=_v16_possible_roles_for(team,champ,occupied)
        for cand in candidates[:4]:
            role=cand["role"]
            assign[role]={"champion":champ,**cand}
            rec(i+1,assign,score+cand["support"],evidence+[round(cand["support"]*100)])
            assign.pop(role,None)
    rec(0,{},0,[])
    states.sort(key=lambda x:(x["score"],x["evidence"]),reverse=True)
    out=[];seen=set()
    for x in states:
        key=tuple((r,x["picks"].get(r)) for r in ("top","jng","mid","bot","sup"))
        if key in seen: continue
        seen.add(key);out.append(x)
        if len(out)>=int(limit): break
    return out

def _v16_leaf(payload,bound,unbound,root_side,cache,assignment_limit=4):
    a=str(payload.get("team_a",""));b=str(payload.get("team_b",""))
    states_a=_v16_assignment_states(a,bound["a"],unbound["a"],assignment_limit)
    states_b=_v16_assignment_states(b,bound["b"],unbound["b"],assignment_limit)
    if not states_a or not states_b:
        return {"error":"Nenhuma combinação de roles plausível no leaf."}
    root_a=(root_side=="a")
    root_states=states_a if root_a else states_b
    opp_states=states_b if root_a else states_a
    best_root=None;evals=0
    for rs in root_states:
        worst=None
        for os in opp_states:
            pa=rs["picks"] if root_a else os["picks"]
            pb=os["picks"] if root_a else rs["picks"]
            ev=_v15_eval_cached(payload,{"a":pa,"b":pb},cache)
            evals+=1
            p_a=float(ev.get("draft_game_probability_team_a") or .5)
            p_root=p_a if root_a else 1-p_a
            row={"probability_root":p_root,"probability_team_a":p_a,
                 "root_assignment":rs,"opponent_assignment":os,
                 "evidence_confidence":int(ev.get("evidence_confidence") or 0)}
            if worst is None or row["probability_root"]<worst["probability_root"]: worst=row
        if best_root is None or worst["probability_root"]>best_root["probability_root"]: best_root=worst
    best_root["assignment_evaluations"]=evals
    best_root["root_assignment_count"]=len(root_states)
    best_root["opponent_assignment_count"]=len(opp_states)
    return best_root

def _v16_candidate_champions(payload,bound,unbound,slot,acting_side,branch_width=2):
    team=_v15_team_for_side(payload,acting_side)
    used=_v16_used_keys(payload,bound,unbound)
    fearless={_champ_key_v10(x) for x in (payload.get("fearless_used") or [])}
    vals={}
    occupied=set(r for r,c in bound[acting_side].items() if c)
    for role in ("top","jng","mid","bot","sup"):
        if role in occupied: continue
        player=_v13_player_for(team,role)
        if not player: continue
        for item in _v13_candidate_pool(player,role,12):
            champ=item["champion"];ck=_champ_key_v10(champ)
            if ck in used or ck in fearless: continue
            pr=item.get("player_row") or {};mr=item.get("meta_row") or {}
            pg=int(pr.get("games") or 0);mg=int(mr.get("games") or 0)
            pe=float(pr.get("smoothed_winrate") or .5);me=float(mr.get("smoothed_winrate") or .5)
            flex=float((_v14_flex_profile(champ) or {}).get("flex_score") or 0)
            role_score=.56*(pe-.5)*min(1,pg/8)+.28*(me-.5)*min(1,mg/18)+.035*flex+.002*min(pg,12)
            v=vals.setdefault(champ,{"champion":champ,"role_options":[],"score":-999,"flex_score":flex})
            v["role_options"].append({"role":role,"player":player,"player_games":pg,"meta_games":mg,"score":role_score})
            v["score"]=max(v["score"],role_score)+(.006 if len(v["role_options"])>1 else 0)
    out=list(vals.values())
    for x in out:
        # Assignment plausibility may be broader than the player-pool shortlist.
        # Surface every role supported by current roster/meta evidence.
        plausible=_v16_possible_roles_for(team,x["champion"],occupied)
        by_role={z["role"]:z for z in x["role_options"]}
        for z in plausible:
            if z["role"] not in by_role:
                x["role_options"].append({"role":z["role"],"player":z["player"],"player_games":z["player_games"],
                                          "meta_games":z["meta_games"],"score":z["support"]*.05})
        x["role_options"].sort(key=lambda y:y["score"],reverse=True)
        x["role_uncertainty"]=len(x["role_options"])
        x["score"] += .018*min(2,max(0,x["role_uncertainty"]-1))*_v14_pick_information_weight(slot)
    out.sort(key=lambda x:(x["score"],x["flex_score"]),reverse=True)
    cap=max(2,int(branch_width))
    chosen=out[:cap]
    # Preserve one genuine flex branch when available so beam pruning does not
    # erase the very uncertainty this engine is designed to study.
    if chosen and not any(x["role_uncertainty"]>1 for x in chosen):
        flexes=[x for x in out[cap:] if x["role_uncertainty"]>1]
        if flexes:
            chosen[-1]=flexes[0]
            chosen.sort(key=lambda x:(x["score"],x["flex_score"]),reverse=True)
    return chosen

def _v16_apply(bound,unbound,side,champion):
    nb={"a":dict(bound["a"]),"b":dict(bound["b"])}
    nu={"a":list(unbound["a"]),"b":list(unbound["b"])}
    nu[side].append(champion)
    return nb,nu

def _v16_minimax(payload,bound,unbound,root_side,root_slot,offset,depth,branch_width,stats,cache,assignment_limit):
    stats["nodes"]+=1
    if offset>=depth:
        leaf=_v16_leaf(payload,bound,unbound,root_side,cache,assignment_limit)
        stats["assignment_states"] += int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    slot=_v15_next_slot(root_slot,offset)
    if not slot:
        leaf=_v16_leaf(payload,bound,unbound,root_side,cache,assignment_limit)
        stats["assignment_states"] += int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    acting=_v15_side_for_slot(payload,slot)
    actions=_v16_candidate_champions(payload,bound,unbound,slot,acting,branch_width)
    if not actions:
        leaf=_v16_leaf(payload,bound,unbound,root_side,cache,assignment_limit)
        stats["assignment_states"] += int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    maximizing=(acting==root_side)
    best=None;best_path=[];best_leaf=None
    for act in actions:
        nb,nu=_v16_apply(bound,unbound,acting,act["champion"])
        val,path,leaf=_v16_minimax(payload,nb,nu,root_side,root_slot,offset+1,depth,branch_width,stats,cache,assignment_limit)
        if best is None or (maximizing and val>best) or ((not maximizing) and val<best):
            best=val;best_path=[{"slot":slot,"side":acting,"team":_v15_team_for_side(payload,acting),**act}]+path;best_leaf=leaf
    return best,best_path,best_leaf

def draft_flex_tree_v16(payload):
    import time
    t0=time.perf_counter()
    root_slot=str(payload.get("root_slot") or "").upper()
    if root_slot not in PICK_ORDER_V14:return {"error":"root_slot inválido."}
    depth=max(2,min(3,int(payload.get("depth") or 3)))
    branch=max(2,min(3,int(payload.get("branch_width") or 2)))
    assignment_limit=max(2,min(4,int(payload.get("assignment_limit") or 2)))
    leaf_budget=max(3,branch)*(branch**max(0,depth-1))*(assignment_limit**2)
    if leaf_budget>180:
        return {"error":f"Flex tree estimada em custo {leaf_budget}. Reduza depth/beam/assignments; limite seguro = 180."}
    root_side=_v15_side_for_slot(payload,root_slot)
    root_team=_v15_team_for_side(payload,root_side)
    bound=_v16_bound_picks(payload);unbound=_v16_unbound(payload)
    cache={};stats={"nodes":0,"assignment_states":0}
    current=_v16_leaf(payload,bound,unbound,root_side,cache,assignment_limit)
    if current.get("error"):return current
    root_actions=_v16_candidate_champions(payload,bound,unbound,root_slot,root_side,max(branch,3))
    results=[]
    for act in root_actions:
        nb,nu=_v16_apply(bound,unbound,root_side,act["champion"])
        imm=_v16_leaf(payload,nb,nu,root_side,cache,assignment_limit)
        stats["assignment_states"] += int(imm.get("assignment_evaluations") or 0)
        val,path,leaf=_v16_minimax(payload,nb,nu,root_side,root_slot,1,depth,branch,stats,cache,assignment_limit)
        results.append({
          "root_action":{"slot":root_slot,"side":root_side,"team":root_team,**act},
          "immediate_flex_probability_root":imm.get("probability_root",.5),
          "minimax_flex_probability_root":val,
          "response_penalty_pp":(imm.get("probability_root",.5)-val)*100,
          "robust_delta_vs_current_pp":(val-current.get("probability_root",.5))*100,
          "principal_variation":[{"slot":root_slot,"side":root_side,"team":root_team,**act}]+path,
          "leaf":leaf
        })
    results.sort(key=lambda x:(x["minimax_flex_probability_root"],x["root_action"]["score"]),reverse=True)
    elapsed=(time.perf_counter()-t0)*1000
    out={"team_a":str(payload.get("team_a","")),"team_b":str(payload.get("team_b","")),
      "root_slot":root_slot,"root_side":root_side,"root_team":root_team,
      "depth":depth,"branch_width":branch,"assignment_limit":assignment_limit,
      "current_probability_root":current.get("probability_root",.5),
      "nodes_evaluated":stats["nodes"],"assignment_states_evaluated":stats["assignment_states"],
      "model_states_evaluated":len(cache),"elapsed_ms":elapsed,"status":"EXPERIMENTAL_FLEX_MINIMAX",
      "note":"Roles of newly picked flex champions remain unresolved until leaf evaluation. Root side chooses its best plausible role assignment while opponent chooses the worst response assignment.",
      "results":results[:int(payload.get("limit") or 6)]}
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO draft_flex_tree_runs_v16
              (created_at,team_a,team_b,side_a,patch,game_number,root_slot,depth,branch_width,root_team,
               current_probability_root,nodes_evaluated,assignment_states_evaluated,result_json,elapsed_ms,status,model_version)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (datetime.now(timezone.utc).isoformat(),out["team_a"],out["team_b"],payload.get("side_a","Blue"),payload.get("patch"),
               int(payload.get("game_number") or 1),root_slot,depth,branch,root_team,out["current_probability_root"],
               out["nodes_evaluated"],out["assignment_states_evaluated"],json.dumps(out["results"],ensure_ascii=False,separators=(",",":")),
               elapsed,out["status"],"V16 flex-aware minimax over V8"))
            con.commit()
    except Exception:pass
    return out


# ---------------------------------------------------------------------------
# V17 — Joint Ban → Pick Planner
# ---------------------------------------------------------------------------
DRAFT_ACTION_SEQUENCE_V17=[
 "B1BAN","R1BAN","B2BAN","R2BAN","B3BAN","R3BAN",
 "B1","R1","R2","B2","B3","R3",
 "R4BAN","B4BAN","R5BAN","B5BAN",
 "R4","B4","B5","R5"
]

def _v17_action_type(slot):
    return "BAN" if str(slot).upper().endswith("BAN") else "PICK"

def _v17_next_slot(root_slot,offset):
    try:i=DRAFT_ACTION_SEQUENCE_V17.index(str(root_slot).upper())+offset
    except ValueError:return None
    return DRAFT_ACTION_SEQUENCE_V17[i] if 0<=i<len(DRAFT_ACTION_SEQUENCE_V17) else None

def _v17_state_payload(payload,bans):
    x=dict(payload);x["bans"]=list(bans);return x

def _v17_ban_actions(payload,bound,unbound,bans,slot,acting_side,branch_width=2):
    # Reuse V14's transparent ban scoring, but make already-picked flex champions unavailable.
    pa=dict(bound["a"]);pb=dict(bound["b"])
    unavailable=list(bans)+list(unbound["a"])+list(unbound["b"])
    q=dict(payload);q.update({"picks_a":pa,"picks_b":pb,"bans":unavailable,"ban_slot":slot,
                              "limit":max(4,int(branch_width)*2)})
    out=draft_ban_strategy_v14(q)
    if out.get("error"):return []
    actions=[]
    for c in out.get("candidates",[]):
        actions.append({
          "action_type":"BAN","slot":slot,"side":acting_side,"team":_v15_team_for_side(payload,acting_side),
          "champion":c["champion"],"relative_priority":float(c.get("relative_priority") or 0),
          "ban_priority_score":float(c.get("ban_priority_score") or 0),
          "target_player":c.get("target_player"),"target_role":c.get("target_role"),
          "evidence_confidence":int(c.get("evidence_confidence") or 0),
          "summary":f"alvo {c.get('target_player') or 'meta'} · {c.get('target_role') or 'flex'}"
        })
    actions.sort(key=lambda x:(x["relative_priority"],x["evidence_confidence"]),reverse=True)
    return actions[:int(branch_width)]

def _v17_pick_actions(payload,bound,unbound,bans,slot,acting_side,branch_width=2):
    q=_v17_state_payload(payload,bans)
    rows=_v16_candidate_champions(q,bound,unbound,slot,acting_side,max(2,int(branch_width)))
    return [{"action_type":"PICK","slot":slot,"side":acting_side,"team":_v15_team_for_side(payload,acting_side),**x} for x in rows[:int(branch_width)]]

def _v17_actions(payload,bound,unbound,bans,slot,acting_side,branch_width):
    if _v17_action_type(slot)=="BAN":
        return _v17_ban_actions(payload,bound,unbound,bans,slot,acting_side,branch_width)
    return _v17_pick_actions(payload,bound,unbound,bans,slot,acting_side,branch_width)

def _v17_apply(bound,unbound,bans,action):
    nb={"a":dict(bound["a"]),"b":dict(bound["b"])}
    nu={"a":list(unbound["a"]),"b":list(unbound["b"])}
    bn=list(bans)
    if action["action_type"]=="BAN":
        bn.append(action["champion"])
    else:
        nu[action["side"]].append(action["champion"])
    return nb,nu,bn

def _v17_leaf(payload,bound,unbound,bans,root_side,cache,assignment_limit):
    return _v16_leaf(_v17_state_payload(payload,bans),bound,unbound,root_side,cache,assignment_limit)

def _v17_minimax(payload,bound,unbound,bans,root_side,root_slot,offset,depth,branch,stats,cache,assignment_limit):
    stats["nodes"]+=1
    if offset>=depth:
        leaf=_v17_leaf(payload,bound,unbound,bans,root_side,cache,assignment_limit)
        stats["assignment_states"]+=int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    slot=_v17_next_slot(root_slot,offset)
    if not slot:
        leaf=_v17_leaf(payload,bound,unbound,bans,root_side,cache,assignment_limit)
        stats["assignment_states"]+=int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    acting=_v15_side_for_slot(payload,slot)
    actions=_v17_actions(payload,bound,unbound,bans,slot,acting,branch)
    if not actions:
        leaf=_v17_leaf(payload,bound,unbound,bans,root_side,cache,assignment_limit)
        stats["assignment_states"]+=int(leaf.get("assignment_evaluations") or 0)
        return leaf.get("probability_root",.5),[],leaf
    maximizing=(acting==root_side)
    best=None;best_path=[];best_leaf=None
    for action in actions:
        nb,nu,bn=_v17_apply(bound,unbound,bans,action)
        val,path,leaf=_v17_minimax(payload,nb,nu,bn,root_side,root_slot,offset+1,depth,branch,stats,cache,assignment_limit)
        if best is None or (maximizing and val>best) or ((not maximizing) and val<best):
            best=val;best_path=[action]+path;best_leaf=leaf
    return best,best_path,best_leaf

def joint_draft_plan_v17(payload):
    import time
    t0=time.perf_counter()
    root_slot=str(payload.get("root_action_slot") or "").upper()
    if root_slot not in DRAFT_ACTION_SEQUENCE_V17:return {"error":"root_action_slot inválido."}
    depth=max(2,min(4,int(payload.get("depth") or 3)))
    branch=max(2,min(3,int(payload.get("branch_width") or 2)))
    assignment_limit=max(2,min(3,int(payload.get("assignment_limit") or 2)))
    estimated=(branch**depth)*(assignment_limit**2)
    if estimated>180:return {"error":f"Plano estimado em custo {estimated}. Reduza depth/beam; limite seguro = 180."}
    root_side=_v15_side_for_slot(payload,root_slot);root_team=_v15_team_for_side(payload,root_side)
    bound=_v16_bound_picks(payload);unbound=_v16_unbound(payload);bans=list(payload.get("bans") or [])
    cache={};stats={"nodes":0,"assignment_states":0}
    current=_v17_leaf(payload,bound,unbound,bans,root_side,cache,assignment_limit)
    if current.get("error"):return current
    root_actions=_v17_actions(payload,bound,unbound,bans,root_slot,root_side,max(branch,3))
    if not root_actions:return {"error":"Nenhuma ação legal encontrada na raiz."}
    results=[]
    for action in root_actions:
        nb,nu,bn=_v17_apply(bound,unbound,bans,action)
        immediate=_v17_leaf(payload,nb,nu,bn,root_side,cache,assignment_limit)
        stats["assignment_states"]+=int(immediate.get("assignment_evaluations") or 0)
        val,path,leaf=_v17_minimax(payload,nb,nu,bn,root_side,root_slot,1,depth,branch,stats,cache,assignment_limit)
        results.append({
          "root_action":action,
          "immediate_probability_root":immediate.get("probability_root",current.get("probability_root",.5)),
          "robust_probability_root":val,
          "robust_delta_vs_current_pp":(val-current.get("probability_root",.5))*100,
          "response_penalty_pp":(immediate.get("probability_root",.5)-val)*100,
          "principal_variation":[action]+path,"leaf":leaf
        })
    results.sort(key=lambda x:(x["robust_probability_root"],x["root_action"].get("relative_priority",0),x["root_action"].get("score",0)),reverse=True)
    elapsed=(time.perf_counter()-t0)*1000
    out={"team_a":str(payload.get("team_a","")),"team_b":str(payload.get("team_b","")),
      "root_action_slot":root_slot,"root_action_type":_v17_action_type(root_slot),"root_side":root_side,"root_team":root_team,
      "depth":depth,"branch_width":branch,"assignment_limit":assignment_limit,
      "current_probability_root":current.get("probability_root",.5),"nodes_evaluated":stats["nodes"],
      "assignment_states_evaluated":stats["assignment_states"],"model_states_evaluated":len(cache),"elapsed_ms":elapsed,
      "status":"EXPERIMENTAL_JOINT_PLANNER",
      "note":"Mixed ban/pick minimax. Bans affect later legal candidate pools; picks preserve flex-role uncertainty. Robust value remains a model-based planning score, not independently calibrated probability.",
      "results":results[:int(payload.get("limit") or 6)]}
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO joint_draft_runs_v17
             (created_at,team_a,team_b,side_a,patch,game_number,root_action_slot,depth,branch_width,assignment_limit,
              root_team,current_probability_root,nodes_evaluated,model_states_evaluated,result_json,elapsed_ms,status,model_version)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (datetime.now(timezone.utc).isoformat(),out["team_a"],out["team_b"],payload.get("side_a","Blue"),payload.get("patch"),
              int(payload.get("game_number") or 1),root_slot,depth,branch,assignment_limit,root_team,out["current_probability_root"],
              out["nodes_evaluated"],out["model_states_evaluated"],json.dumps(out["results"],ensure_ascii=False,separators=(",",":")),
              elapsed,out["status"],"V17 joint ban-pick minimax"))
            con.commit()
    except Exception:pass
    return out


# ---------------------------------------------------------------------------
# V18 — Series-level Strategy Objective
# ---------------------------------------------------------------------------
def _v18_pool_role(team,role,excluded_keys,topn=3):
    player=_v13_player_for(team,role)
    if not player:return {"role":role,"player":None,"score":.5,"options":[]}
    rows=db_rows("""SELECT champion,games,smoothed_winrate,winrate,gd15
                    FROM draft_player_champion
                    WHERE player=? AND scope='2026'
                    ORDER BY games DESC,smoothed_winrate DESC LIMIT 40""",(player,))
    opts=[]
    for r in rows:
        if _champ_key_v10(r["champion"]) in excluded_keys:continue
        games=int(r.get("games") or 0); eb=float(r.get("smoothed_winrate") or .5)
        supported=.5+(eb-.5)*min(1,games/8)
        opts.append({"champion":r["champion"],"games":games,"eb":eb,"supported":supported})
    opts.sort(key=lambda x:(x["supported"],x["games"]),reverse=True)
    weights=[.60,.28,.12]
    vals=opts[:topn]
    if not vals:return {"role":role,"player":player,"score":.5,"options":[]}
    denom=sum(weights[:len(vals)])
    score=sum(v["supported"]*weights[i] for i,v in enumerate(vals))/denom
    return {"role":role,"player":player,"score":score,"options":vals}

def pool_resilience_v18(team,excluded):
    keys={_champ_key_v10(x) for x in (excluded or []) if x}
    roles=[_v18_pool_role(team,r,keys) for r in ("top","jng","mid","bot","sup")]
    vals=[float(x["score"]) for x in roles]
    avg=sum(vals)/len(vals) if vals else .5
    bottleneck=min(vals) if vals else .5
    # Reward breadth but keep weakest lane visible.
    quality=.76*avg+.24*bottleneck
    return {"team":team,"quality":quality,"average":avg,"bottleneck":bottleneck,"roles":roles,
            "excluded_count":len(keys)}

def _v18_neutral_future_map_probability_a(payload,excluded):
    a=str(payload.get("team_a",""));b=str(payload.get("team_b",""))
    ra=db_one("SELECT * FROM current_ratings WHERE team=?",(a,));rb=db_one("SELECT * FROM current_ratings WHERE team=?",(b,))
    if not ra or not rb:return {"probability_team_a":.5,"pool_a":pool_resilience_v18(a,excluded),"pool_b":pool_resilience_v18(b,excluded)}
    pa=pool_resilience_v18(a,excluded);pb=pool_resilience_v18(b,excluded)
    md=float(pa["quality"])-float(pb["quality"])
    elo_ab=float(ra["elo"])-float(rb["elo"])
    p_a_blue=_draft_model_probability(elo_ab,md,0)
    elo_ba=float(rb["elo"])-float(ra["elo"])
    p_a_red=1-_draft_model_probability(elo_ba,-md,0)
    neutral=(p_a_blue+p_a_red)/2
    return {"probability_team_a":neutral,"probability_a_blue":p_a_blue,"probability_a_red":p_a_red,
            "mastery_pool_diff":md,"pool_a":pa,"pool_b":pb,
            "note":"Future-map estimate reuses the audited V8 mastery coefficient on a remaining-pool proxy and averages both side assignments. This extrapolation is experimental."}

def _v18_series_win_prob(score_a,score_b,best_of,current_p_a,future_p_a):
    need=int(best_of)//2+1
    score_a=int(score_a or 0);score_b=int(score_b or 0)
    from functools import lru_cache
    @lru_cache(None)
    def rec(sa,sb,is_current):
        if sa>=need:return 1.0
        if sb>=need:return 0.0
        p=float(current_p_a if is_current else future_p_a)
        return p*rec(sa+1,sb,False)+(1-p)*rec(sa,sb+1,False)
    return rec(score_a,score_b,True)

def _v18_consumed_from_state(payload,result=None):
    vals=list(payload.get("fearless_used") or [])
    for d in (payload.get("picks_a") or {},payload.get("picks_b") or {}):vals += [x for x in d.values() if x]
    vals += list(payload.get("unbound_a") or [])+list(payload.get("unbound_b") or [])
    if result:
        for a in result.get("principal_variation") or []:
            if a.get("action_type")=="PICK" and a.get("champion"):vals.append(a["champion"])
    # Fearless is global in the current product model; dedupe canonically while retaining labels.
    out=[];seen=set()
    for x in vals:
        k=_champ_key_v10(x)
        if k and k not in seen:seen.add(k);out.append(x)
    return out

def series_plan_v18(payload):
    import time
    t0=time.perf_counter()
    score_a=int(payload.get("series_score_a") or 0);score_b=int(payload.get("series_score_b") or 0)
    best_of=int(payload.get("best_of") or 3)
    if best_of not in (3,5):return {"error":"best_of suportado: 3 ou 5."}
    joint=joint_draft_plan_v17(payload)
    if joint.get("error"):return joint
    root_a=(joint["root_side"]=="a")
    current_map_root=float(joint["current_probability_root"])
    current_map_a=current_map_root if root_a else 1-current_map_root
    baseline_excluded=_v18_consumed_from_state(payload)
    future0=_v18_neutral_future_map_probability_a(payload,baseline_excluded)
    baseline_series_a=_v18_series_win_prob(score_a,score_b,best_of,current_map_a,future0["probability_team_a"])
    baseline_series_root=baseline_series_a if root_a else 1-baseline_series_a
    results=[]
    for r in joint.get("results",[]):
        robust_root=float(r["robust_probability_root"])
        robust_a=robust_root if root_a else 1-robust_root
        consumed=_v18_consumed_from_state(payload,r)
        future=_v18_neutral_future_map_probability_a(payload,consumed)
        series_a=_v18_series_win_prob(score_a,score_b,best_of,robust_a,future["probability_team_a"])
        series_root=series_a if root_a else 1-series_a
        results.append({**r,
          "series_probability_root":series_root,
          "series_probability_team_a":series_a,
          "series_delta_vs_baseline_pp":(series_root-baseline_series_root)*100,
          "future_map_probability_team_a":future["probability_team_a"],
          "future_map_probability_root":future["probability_team_a"] if root_a else 1-future["probability_team_a"],
          "future_pool":future,
          "consumed_for_future":consumed,
          "known_consumption_count":len(consumed)
        })
    results.sort(key=lambda x:(x["series_probability_root"],x["robust_probability_root"]),reverse=True)
    elapsed=(time.perf_counter()-t0)*1000
    out={"team_a":joint["team_a"],"team_b":joint["team_b"],"root_team":joint["root_team"],"root_side":joint["root_side"],
      "root_action_slot":joint["root_action_slot"],"root_action_type":joint["root_action_type"],
      "score_a":score_a,"score_b":score_b,"best_of":best_of,
      "current_map_probability_root":current_map_root,"baseline_future_map_probability_team_a":future0["probability_team_a"],
      "baseline_series_probability_root":baseline_series_root,"baseline_future_pool":future0,
      "nodes_evaluated":joint["nodes_evaluated"],"model_states_evaluated":joint["model_states_evaluated"],
      "elapsed_ms":elapsed,"status":"EXPERIMENTAL_SERIES_OBJECTIVE",
      "note":"Current-map robust value comes from V17/V16/V8. Future-map probability is an experimental remaining-pool extrapolation. Series probability is exact conditional math given those map probabilities, but the future-map input is not independently calibrated.",
      "results":results[:int(payload.get("limit") or 6)]}
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO series_strategy_runs_v18
              (created_at,team_a,team_b,score_a,score_b,best_of,root_action_slot,root_team,current_series_probability_root,
               result_json,nodes_evaluated,elapsed_ms,status,model_version)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (datetime.now(timezone.utc).isoformat(),out["team_a"],out["team_b"],score_a,score_b,best_of,out["root_action_slot"],out["root_team"],
               baseline_series_root,json.dumps(out["results"],ensure_ascii=False,separators=(",",":")),out["nodes_evaluated"],elapsed,out["status"],
               "V18 series objective over V17 joint planner"))
            con.commit()
    except Exception:pass
    return out


# ---------------------------------------------------------------------------
# V21 — model governance / prospective lockbox
# ---------------------------------------------------------------------------
GOVERNANCE_DIR = ROOT / "governance"
V21_LOCK_FILE = GOVERNANCE_DIR / "GOVERNANCE_LOCK_V21.json"
V21_FROZEN_FILE = GOVERNANCE_DIR / "V19_FROZEN_CANDIDATES.json"
V21_PROMOTION_FILE = GOVERNANCE_DIR / "PROMOTION_POLICY_V21.json"
V21_LIVE_PROTOCOL_FILE = GOVERNANCE_DIR / "LIVE_TRAINING_PROTOCOL_V21.json"


def _v21_canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def _v21_hash_obj(obj):
    return hashlib.sha256(_v21_canonical(obj).encode("utf-8")).hexdigest()


def _v21_hash_file(path):
    try:return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:return None


def _v21_json_file(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default if default is not None else {}


def v21_ensure_schema():
    with db_connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS experiment_registry_v21(
         experiment_id TEXT PRIMARY KEY, layer TEXT NOT NULL, candidate TEXT, created_at TEXT NOT NULL,
         epoch_start TEXT, status TEXT NOT NULL, definition_hash TEXT NOT NULL, config_hash TEXT,
         source_version TEXT, retrospective_verdict TEXT, gate_policy_hash TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS governance_events_v21(
         id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, severity TEXT NOT NULL,
         event_type TEXT NOT NULL, experiment_id TEXT, game_id TEXT, details_json TEXT);
        CREATE TABLE IF NOT EXISTS prospective_capture_ledger_v21(
         id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT NOT NULL, candidate TEXT NOT NULL,
         prediction_id INTEGER, captured_at TEXT NOT NULL, experiment_id TEXT NOT NULL,
         definition_hash TEXT NOT NULL, feature_hash TEXT, capture_status TEXT, source TEXT,
         UNIQUE(game_id,candidate));
        CREATE TABLE IF NOT EXISTS promotion_reviews_v21(
         candidate TEXT PRIMARY KEY, updated_at TEXT NOT NULL, games INTEGER, series_count INTEGER,
         log_loss REAL, brier REAL, accuracy REAL, ece REAL, delta_log_loss_vs_core REAL,
         delta_brier_vs_core REAL, bootstrap_json TEXT, sample_pass INTEGER, practical_pass INTEGER,
         uncertainty_pass INTEGER, calibration_pass INTEGER, decision TEXT, reasons_json TEXT, policy_hash TEXT);
        CREATE TABLE IF NOT EXISTS live_protocol_registry_v21(
         protocol_id TEXT PRIMARY KEY, frozen_at TEXT NOT NULL, status TEXT NOT NULL,
         protocol_hash TEXT NOT NULL, protocol_json TEXT NOT NULL, note TEXT);
        CREATE TABLE IF NOT EXISTS live_model_experiments_v21(
         run_id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_id TEXT NOT NULL, created_at TEXT NOT NULL,
         protocol_hash TEXT NOT NULL, dataset_hash TEXT, games INTEGER, snapshots INTEGER,
         train_games INTEGER, validation_games INTEGER, test_games INTEGER, selected_family TEXT,
         selected_c REAL, validation_json TEXT, test_metrics_json TEXT, checkpoint_metrics_json TEXT,
         bootstrap_json TEXT, model_json TEXT, decision TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS release_integrity_v21(
         path TEXT PRIMARY KEY, expected_sha256 TEXT NOT NULL, critical INTEGER NOT NULL DEFAULT 1, note TEXT);
        """)
        con.commit()


def v21_log_event(severity,event_type,details=None,experiment_id=None,game_id=None):
    try:
        with db_connect() as con:
            con.execute("""INSERT INTO governance_events_v21
              (occurred_at,severity,event_type,experiment_id,game_id,details_json)
              VALUES(?,?,?,?,?,?)""",(datetime.now(timezone.utc).isoformat(),severity,event_type,experiment_id,game_id,
                                     json.dumps(details or {},ensure_ascii=False,separators=(",",":"))))
            con.commit()
    except Exception:pass


def v21_integrity_report():
    lock=_v21_json_file(V21_LOCK_FILE,{})
    checks=[]
    for rel,expected in (lock.get("artifacts") or {}).items():
        actual=_v21_hash_file(GOVERNANCE_DIR/rel)
        checks.append({"path":f"governance/{rel}","expected":expected,"actual":actual,"ok":actual==expected,"critical":True})
    # V24: release/UI files are allowed to evolve without invalidating the scientific lockbox.
    # Only immutable governance artifacts above can block the prospective experiment.
    for r in db_rows("SELECT * FROM release_integrity_v21 ORDER BY path"):
        actual=_v21_hash_file(ROOT/r["path"])
        scientific= str(r["path"]).startswith("governance/") and str(r["path"]).endswith(".json")
        checks.append({"path":r["path"],"expected":r["expected_sha256"],"actual":actual,
                       "ok":actual==r["expected_sha256"],"critical":bool(scientific),
                       "scope":"scientific_lock" if scientific else "release_history"})
    critical_bad=[x for x in checks if x["critical"] and not x["ok"]]
    return {"status":"OK" if not critical_bad else "DRIFT_DETECTED","ok":not critical_bad,
            "checks":checks,"lock_created_at":lock.get("created_at"),"release":lock.get("release")}


def _v21_db_freeze_definition(row):
    model=_v19_parse_json(row.get("model_json"),{})
    features=_v19_parse_json(row.get("features_json"),[])
    obj={"candidate":row.get("candidate"),"frozen_at":row.get("frozen_at"),"features":features,"model":model}
    return obj,_v21_hash_obj(obj)


def v21_verified_v19_freezes():
    lock=_v21_json_file(V21_LOCK_FILE,{})
    expected=lock.get("candidate_definition_hashes") or {}
    out=[]
    for r in db_rows("SELECT * FROM validation_freeze_v19 WHERE status='FROZEN_AWAITING_PROSPECTIVE' ORDER BY candidate"):
        obj,h=_v21_db_freeze_definition(r)
        exp=expected.get(r["candidate"])
        if exp and h==exp:
            rr=dict(r);rr["definition_hash"]=h;rr["experiment_id"]=f"v19:{r['candidate']}:{r['frozen_at']}";out.append(rr)
        else:
            v21_log_event("ERROR","FROZEN_MODEL_DRIFT",{"candidate":r.get("candidate"),"expected_hash":exp,"actual_hash":h},
                          f"v19:{r.get('candidate')}:{r.get('frozen_at')}")
    return out


def v21_capture_ledger(game_id,candidate,prediction_id,captured_at,experiment_id,definition_hash,features,capture_status):
    try:
        with db_connect() as con:
            con.execute("""INSERT OR IGNORE INTO prospective_capture_ledger_v21
              (game_id,candidate,prediction_id,captured_at,experiment_id,definition_hash,feature_hash,capture_status,source)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              (game_id,candidate,prediction_id,captured_at,experiment_id,definition_hash,_v21_hash_obj(features),capture_status,"V19 frozen prospective via V21 governance"))
            con.commit()
    except Exception:pass


def _v21_gate_policy():
    return _v21_json_file(V21_PROMOTION_FILE,{})


def v21_refresh_promotion_reviews():
    gate=v19_refresh_gate_summary()
    policy=_v21_gate_policy();ph=policy.get("policy_hash")
    core=next((x for x in gate if x.get("candidate")==policy.get("reference_candidate","core")),None)
    lock=_v21_json_file(V21_LOCK_FILE,{})
    expected_hashes=lock.get("candidate_definition_hashes") or {}
    actual_hashes={}
    for fr in db_rows("SELECT * FROM validation_freeze_v19"):
        _,hh=_v21_db_freeze_definition(fr);actual_hashes[fr.get("candidate")]=hh
    now=datetime.now(timezone.utc).isoformat();out=[]
    for g in gate:
        name=g.get("candidate");games=int(g.get("games") or 0);series=int(g.get("series_count") or 0)
        hash_ok=bool(expected_hashes.get(name) and actual_hashes.get(name)==expected_hashes.get(name))
        sample_pass=games>=int(policy.get("minimum_games",100)) and series>=int(policy.get("minimum_series",40))
        reasons=[];practical=False;uncertainty=False;calibration=False;decision="COLLECTING"
        if not hash_ok:
            decision="BLOCKED_INTEGRITY";reasons.append("frozen candidate definition differs from governance lock")
        elif name==policy.get("reference_candidate","core"):
            decision="REFERENCE" if games else "COLLECTING";practical=uncertainty=calibration=True
        elif sample_pass and core:
            dll=g.get("delta_log_loss_vs_core");dbr=g.get("delta_brier_vs_core");boot=g.get("bootstrap") or {}
            th=policy.get("practical_thresholds") or {}
            practical=(dll is not None and dbr is not None and dll<=float(th.get("delta_log_loss_max",-.005)) and dbr<=float(th.get("delta_brier_max",-.002)))
            uncertainty=(boot.get("ll_delta_hi") is not None and boot.get("brier_delta_hi") is not None and float(boot["ll_delta_hi"])<=0 and float(boot["brier_delta_hi"])<=0)
            cal=policy.get("calibration") or {};calibration=(g.get("ece") is not None and core.get("ece") is not None and float(g["ece"])<=float(core["ece"])+float(cal.get("candidate_may_exceed_core_by_at_most",.01)))
            if not practical:reasons.append("practical effect threshold not met")
            if not uncertainty:reasons.append("both 95% bootstrap upper bounds must be <= 0")
            if not calibration:reasons.append("calibration gate not met")
            if practical and uncertainty and calibration:
                decision="ELIGIBLE_FOR_REVIEW"
            else:
                # Strict prospective rejection only when both metrics are worse and both bootstrap lower bounds support harm.
                harm=(dll is not None and dbr is not None and dll>0 and dbr>0 and boot.get("ll_delta_lo") is not None and boot.get("brier_delta_lo") is not None and float(boot["ll_delta_lo"])>=0 and float(boot["brier_delta_lo"])>=0)
                decision="REJECTED_PROSPECTIVE" if harm else "INCONCLUSIVE_CONTINUE"
        elif sample_pass:
            decision="INCONCLUSIVE_CONTINUE";reasons.append("reference metrics unavailable")
        else:
            reasons.append("minimum prospective sample not reached")
        row={**g,"sample_pass":sample_pass,"practical_pass":practical,"uncertainty_pass":uncertainty,"calibration_pass":calibration,
             "decision":decision,"reasons":reasons,"policy_hash":ph}
        out.append(row)
        try:
            with db_connect() as con:
                con.execute("""INSERT OR REPLACE INTO promotion_reviews_v21
                  (candidate,updated_at,games,series_count,log_loss,brier,accuracy,ece,delta_log_loss_vs_core,delta_brier_vs_core,
                   bootstrap_json,sample_pass,practical_pass,uncertainty_pass,calibration_pass,decision,reasons_json,policy_hash)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (name,now,games,series,g.get("log_loss"),g.get("brier"),g.get("accuracy"),g.get("ece"),g.get("delta_log_loss_vs_core"),g.get("delta_brier_vs_core"),
                   json.dumps(g.get("bootstrap"),ensure_ascii=False) if g.get("bootstrap") else None,int(sample_pass),int(practical),int(uncertainty),int(calibration),decision,json.dumps(reasons,ensure_ascii=False),ph))
                con.commit()
        except Exception:pass
    return out


def v21_live_protocol_status():
    protocol=_v21_json_file(V21_LIVE_PROTOCOL_FILE,{})
    reg=db_one("SELECT * FROM live_protocol_registry_v21 WHERE protocol_id=?",(protocol.get("protocol_id"),))
    actual=_v21_hash_obj({k:v for k,v in protocol.items() if k!="protocol_hash"}) if protocol else None
    expected=protocol.get("protocol_hash") if protocol else None
    readiness=v20_live_readiness()
    runs=db_rows("SELECT run_id,created_at,games,snapshots,selected_family,selected_c,test_metrics_json,decision FROM live_model_experiments_v21 ORDER BY run_id DESC LIMIT 5")
    for r in runs:r["test_metrics"]=_v19_parse_json(r.pop("test_metrics_json",None),None)
    return {"protocol_id":protocol.get("protocol_id"),"status":protocol.get("status"),"hash":expected,
            "hash_ok":bool(expected and actual==expected and (not reg or reg.get("protocol_hash")==expected)),
            "readiness":readiness,"split":protocol.get("chronological_split"),"families":protocol.get("families"),
            "primary_evaluation":protocol.get("primary_evaluation"),"promotion_review_gate":protocol.get("promotion_review_gate"),"runs":runs}


def v21_governance_summary():
    v21_ensure_schema()
    v23_ensure_schedule_schema()
    v28_ensure_schema()
    prune_stale_schedule_v23()
    integrity=v21_integrity_report();reviews=v21_refresh_promotion_reviews();live=v21_live_protocol_status()
    return {"integrity":integrity,"experiments":db_rows("SELECT * FROM experiment_registry_v21 ORDER BY layer,candidate"),
            "promotion_policy":_v21_gate_policy(),"promotion_reviews":reviews,"live_protocol":live,
            "ledger":{"captures":int((db_one("SELECT COUNT(*) n FROM prospective_capture_ledger_v21") or {}).get("n") or 0),
                      "events":db_rows("SELECT * FROM governance_events_v21 ORDER BY id DESC LIMIT 10")},
            "rule":"A passing automated gate creates ELIGIBLE_FOR_REVIEW only. Production status is never changed automatically."}


# ---------------------------------------------------------------------------
# V19 — Validation Lab + prospective frozen gate
# ---------------------------------------------------------------------------
def _v19_parse_json(v,default=None):
    try:return json.loads(v) if v else (default if default is not None else {})
    except:return default if default is not None else {}


def _v19_flex_team(champions):
    vals=[]
    for c in champions or []:
        if not c:continue
        vals.append(float((_v14_flex_profile(c) or {}).get("flex_score") or 0))
    return sum(vals)/len(vals) if vals else 0.0


def v19_features_from_live(snap,draft):
    if not snap or not draft:return None
    blue=canonical((snap.get("blue") or {}).get("team")) or (snap.get("blue") or {}).get("team")
    red=canonical((snap.get("red") or {}).get("team")) or (snap.get("red") or {}).get("team")
    rb=db_one("SELECT elo FROM current_ratings WHERE team=?",(blue,)) or {"elo":1500}
    rr=db_one("SELECT elo FROM current_ratings WHERE team=?",(red,)) or {"elo":1500}
    elo_diff=float(rb.get("elo") or 1500)-float(rr.get("elo") or 1500)
    mastery_diff=float(draft.get("mastery_diff") or 0)
    synergy_diff=float(draft.get("team_a_synergy") or .5)-float(draft.get("team_b_synergy") or .5)
    excluded=_prior_fearless(snap.get("event_id"),int(snap.get("game_number") or 1))
    pb=pool_resilience_v18(blue,excluded); pr=pool_resilience_v18(red,excluded)
    bb=pool_resilience_v18(blue,[]); br=pool_resilience_v18(red,[])
    blue_loss=max(0,float(bb.get("quality") or .5)-float(pb.get("quality") or .5))
    red_loss=max(0,float(br.get("quality") or .5)-float(pr.get("quality") or .5))
    roles=draft.get("roles") or []
    blue_champs=[x.get("team_a_champion") for x in roles if x.get("team_a_champion")]
    red_champs=[x.get("team_b_champion") for x in roles if x.get("team_b_champion")]
    return {
      "elo_diff":elo_diff,"mastery_diff":mastery_diff,"synergy_diff":synergy_diff,
      "remaining_pool_diff":float(pb.get("quality") or .5)-float(pr.get("quality") or .5),
      "pool_exhaustion_adv":red_loss-blue_loss,
      "flex_diff":_v19_flex_team(blue_champs)-_v19_flex_team(red_champs),
      "blue_pool_loss":blue_loss,"red_pool_loss":red_loss,
      "fearless_used":excluded,"blue_champions":blue_champs,"red_champions":red_champs
    }


def _v19_frozen_predict(model,features):
    names=model.get("features") or []
    med=model.get("imputer_medians") or []
    means=model.get("means") or []
    scales=model.get("scales") or []
    coef=model.get("coef") or []
    z=float(model.get("intercept") or 0)
    for i,name in enumerate(names):
        v=features.get(name)
        if v is None:
            v=med[i] if i<len(med) else 0
        v=float(v)
        mean=means[i] if i<len(means) else 0
        scale=scales[i] if i<len(scales) and abs(float(scales[i]))>1e-12 else 1
        c=coef[i] if i<len(coef) else 0
        z += float(c)*((v-float(mean))/float(scale))
    return _sigmoid_v10(z)


def v19_capture_prospective(snap,draft):
    """Append-only prospective post-draft predictions from frozen V19 candidates."""
    if not snap or not draft:return {"captured":0,"reason":"draft unavailable"}
    roles=draft.get("roles") or []
    if len(roles)<5:return {"captured":0,"reason":"draft incomplete"}
    features=v19_features_from_live(snap,draft)
    if not features:return {"captured":0,"reason":"features unavailable"}
    freezes=v21_verified_v19_freezes()
    if not freezes:return {"captured":0,"reason":"no frozen candidates"}
    now=str(snap.get("timestamp") or datetime.now(timezone.utc).isoformat())
    gt=float(snap.get("game_time_seconds") or 0)
    capture_status="VALID_EARLY" if gt<=300 else "LATE_CAPTURE"
    event_id=str(snap.get("event_id") or "");game_id=str(snap.get("game_id") or "")
    game_number=int(snap.get("game_number") or 1)
    blue=canonical((snap.get("blue") or {}).get("team")) or (snap.get("blue") or {}).get("team")
    red=canonical((snap.get("red") or {}).get("team")) or (snap.get("red") or {}).get("team")
    series_key=event_id or f"{blue}|{red}"
    epoch=db_one("SELECT value FROM metadata WHERE key='validation_v19_freeze_time'")
    epoch=(epoch or {}).get("value")
    captured=0
    with db_connect() as con:
        for fr in freezes:
            model=_v19_parse_json(fr.get("model_json"),{})
            p=_v19_frozen_predict(model,features)
            cur=con.execute("SELECT id FROM prospective_predictions_v19 WHERE game_id=? AND candidate=?",(game_id,fr["candidate"])).fetchone()
            if cur:continue
            curins=con.execute("""INSERT INTO prospective_predictions_v19
              (game_id,candidate,captured_at,blue_team,red_team,probability_blue,features_json,model_frozen_at,
               outcome_blue,scored_at,event_id,game_number,series_key,game_time_seconds,capture_status,validation_epoch)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (game_id,fr["candidate"],now,blue,red,p,json.dumps(features,ensure_ascii=False,separators=(",",":")),fr["frozen_at"],
               None,None,event_id,game_number,series_key,gt,capture_status,epoch))
            v21_capture_ledger(game_id,fr["candidate"],curins.lastrowid,now,fr.get("experiment_id"),fr.get("definition_hash"),features,capture_status)
            captured+=1
        con.commit()
    return {"captured":captured,"capture_status":capture_status,"features":features}


def _v19_metric_rows(rows):
    if not rows:return None
    ps=[min(.999999,max(.000001,float(r["probability_blue"]))) for r in rows]
    ys=[int(r["outcome_blue"]) for r in rows]
    n=len(rows)
    ll=sum(-(y*math.log(p)+(1-y)*math.log(1-p)) for y,p in zip(ys,ps))/n
    br=sum((p-y)**2 for y,p in zip(ys,ps))/n
    acc=sum((p>=.5)==bool(y) for y,p in zip(ys,ps))/n
    ece=0.0
    for i in range(10):
        lo=i/10;hi=(i+1)/10
        ix=[j for j,p in enumerate(ps) if p>=lo and (p<hi or (i==9 and p<=hi))]
        if ix:
            ece += len(ix)/n*abs(sum(ys[j] for j in ix)/len(ix)-sum(ps[j] for j in ix)/len(ix))
    return {"games":n,"log_loss":ll,"brier":br,"accuracy":acc,"ece":ece}


def v19_score_prospective():
    rows=db_rows("""SELECT p.id,p.game_id,p.blue_team,g.winner
                    FROM prospective_predictions_v19 p JOIN riot_games_v10 g ON g.game_id=p.game_id
                    WHERE p.outcome_blue IS NULL AND g.winner IS NOT NULL AND g.winner<>''""")
    if not rows:return 0
    now=datetime.now(timezone.utc).isoformat();n=0
    with db_connect() as con:
        for r in rows:
            y=1 if canonical(r.get("winner"))==canonical(r.get("blue_team")) else 0
            con.execute("UPDATE prospective_predictions_v19 SET outcome_blue=?,scored_at=? WHERE id=?",(y,now,r["id"]));n+=1
        con.commit()
    return n


def _v19_bootstrap_gate(candidate_rows,core_rows,reps=800):
    import random
    ca={r["game_id"]:r for r in candidate_rows};co={r["game_id"]:r for r in core_rows};games=sorted(set(ca)&set(co))
    if len(games)<20:return None
    by_event={}
    for gid in games:
        ev=ca[gid].get("event_id") or ca[gid].get("series_key") or gid
        by_event.setdefault(ev,[]).append(gid)
    events=list(by_event)
    if len(events)<8:return None
    rng=random.Random(19);dll=[];dbr=[]
    for _ in range(reps):
        samp=[rng.choice(events) for __ in events];ids=[]
        for ev in samp:ids.extend(by_event[ev])
        lc=lb=bc=bb=0.0;n=0
        for gid in ids:
            y=int(ca[gid]["outcome_blue"]);pc=min(.999999,max(.000001,float(ca[gid]["probability_blue"])));pb=min(.999999,max(.000001,float(co[gid]["probability_blue"])))
            lc+=-(y*math.log(pc)+(1-y)*math.log(1-pc));lb+=-(y*math.log(pb)+(1-y)*math.log(1-pb));bc+=(pc-y)**2;bb+=(pb-y)**2;n+=1
        if n:dll.append((lc-lb)/n);dbr.append((bc-bb)/n)
    if not dll:return None
    def q(a,p):
        a=sorted(a);i=max(0,min(len(a)-1,int(round((len(a)-1)*p))));return a[i]
    return {"ll_delta_mean":sum(dll)/len(dll),"ll_delta_lo":q(dll,.025),"ll_delta_hi":q(dll,.975),
            "brier_delta_mean":sum(dbr)/len(dbr),"brier_delta_lo":q(dbr,.025),"brier_delta_hi":q(dbr,.975)}


def v19_refresh_gate_summary():
    v19_score_prospective()
    freezes=db_rows("SELECT * FROM validation_freeze_v19 ORDER BY candidate")
    allrows=db_rows("""SELECT * FROM prospective_predictions_v19
                       WHERE outcome_blue IS NOT NULL AND capture_status='VALID_EARLY' ORDER BY game_id,candidate""")
    by={}
    for r in allrows:by.setdefault(r["candidate"],[]).append(r)
    core=by.get("core",[]);corem=_v19_metric_rows(core)
    now=datetime.now(timezone.utc).isoformat();out=[]
    with db_connect() as con:
        for fr in freezes:
            name=fr["candidate"];rows=by.get(name,[]);m=_v19_metric_rows(rows)
            series_count=len({r.get("event_id") or r.get("series_key") for r in rows}) if rows else 0
            boot=None;dll=dbr=None;status="COLLECTING"
            if name=="core":status="REFERENCE" if m else "COLLECTING"
            elif m and corem:
                dll=m["log_loss"]-corem["log_loss"];dbr=m["brier"]-corem["brier"]
                boot=_v19_bootstrap_gate(rows,core)
                if m["games"]>=int(fr.get("min_future_games") or 100) and series_count>=int(fr.get("min_future_series") or 40):
                    ciok=bool(boot) and boot.get("ll_delta_hi",1)<=0 and boot.get("brier_delta_hi",1)<=0
                    if dll<=-.005 and dbr<=-.002 and m["ece"]<=corem["ece"]+.01 and ciok:status="PASS_CANDIDATE"
                    elif dll>0 and dbr>0:status="FAIL_CANDIDATE"
                    else:status="REVIEW_REQUIRED"
            con.execute("""INSERT OR REPLACE INTO prospective_gate_summary_v19
             (candidate,games,series_count,log_loss,brier,accuracy,ece,delta_log_loss_vs_core,delta_brier_vs_core,bootstrap_json,gate_status,updated_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
             (name,(m or {}).get("games",0),series_count,(m or {}).get("log_loss"),(m or {}).get("brier"),(m or {}).get("accuracy"),(m or {}).get("ece"),dll,dbr,json.dumps(boot) if boot else None,status,now))
            out.append({"candidate":name,**(m or {"games":0}),"series_count":series_count,"delta_log_loss_vs_core":dll,"delta_brier_vs_core":dbr,"bootstrap":boot,"gate_status":status})
        con.commit()
    return out


def v19_validation_summary():
    gate=v19_refresh_gate_summary()
    exps=db_rows("SELECT * FROM validation_experiments_v19 ORDER BY eval2026_log_loss")
    for r in exps:r["bootstrap"]=_v19_parse_json(r.pop("bootstrap_json",None),None)
    return {
      "status":{ "blind":"RETROSPECTIVE_NOT_PRISTINE","prospective":"FROZEN_AWAITING_PROSPECTIVE",
        "message":"2026 was not a pristine project-level holdout. Retrospective results are evidence, not a promotion gate. Frozen candidates now await genuinely future games."},
      "dataset":{"games":int((db_one("SELECT COUNT(*) n FROM validation_dataset_v19") or {}).get("n") or 0),
                 "series":int((db_one("SELECT COUNT(DISTINCT series_key) n FROM validation_dataset_v19") or {}).get("n") or 0),
                 "games_2025":int((db_one("SELECT COUNT(*) n FROM validation_dataset_v19 WHERE year=2025") or {}).get("n") or 0),
                 "games_2026":int((db_one("SELECT COUNT(*) n FROM validation_dataset_v19 WHERE year=2026") or {}).get("n") or 0)},
      "experiments":exps,
      "subgroups":db_rows("SELECT * FROM validation_subgroups_v19 ORDER BY candidate,subgroup"),
      "features":db_rows("SELECT * FROM validation_feature_descriptives_v19 ORDER BY feature"),
      "layers":db_rows("SELECT * FROM validation_layer_status_v19 ORDER BY rowid"),
      "freeze":[{k:v for k,v in r.items() if k!='model_json'} for r in db_rows("SELECT * FROM validation_freeze_v19 ORDER BY candidate")],
      "prospective_gate":gate,
      "captures":{"valid_early":int((db_one("SELECT COUNT(DISTINCT game_id) n FROM prospective_predictions_v19 WHERE capture_status='VALID_EARLY'") or {}).get("n") or 0),
                  "late":int((db_one("SELECT COUNT(DISTINCT game_id) n FROM prospective_predictions_v19 WHERE capture_status='LATE_CAPTURE'") or {}).get("n") or 0)},
      "promotion_rule":"No feature is promoted from V19 retrospective evidence. Prospective gate: >=100 future maps and >=40 series, frozen model, no retuning; improve both Log Loss and Brier vs core with acceptable calibration and uncertainty."
    }


# ---------------------------------------------------------------------------
# V20 — prospective live training dataset + readiness gate
# ---------------------------------------------------------------------------
def v20_capture_live_training(snap,draft):
    if not snap or not draft:return {"captured":False,"reason":"draft unavailable"}
    state=(str(snap.get("game_state") or "")+" "+str(snap.get("event_state") or "")).lower()
    if "complete" in state:return {"captured":False,"reason":"completed snapshots excluded"}
    t=float(snap.get("game_time_seconds") or 0)
    if t<180:return {"captured":False,"reason":"before capture window"}
    checkpoint=int(t//60)*60
    b=snap.get("blue") or {};r=snap.get("red") or {}
    bg=_role_gold(b.get("participants") or []);rg=_role_gold(r.get("participants") or [])
    diffs={role:float(bg.get(role,0)-rg.get(role,0)) for role in ("top","jng","mid","bot","sup")}
    pos=sum(1 for v in diffs.values() if v>250);neg=sum(1 for v in diffs.values() if v<-250);breadth=(pos-neg)/5
    blue=canonical(b.get("team")) or b.get("team");red=canonical(r.get("team")) or r.get("team")
    p0=float(draft.get("draft_game_probability_team_a") or .5)
    now=str(snap.get("timestamp") or datetime.now(timezone.utc).isoformat())
    vals=(str(snap.get("game_id")),str(snap.get("event_id") or ""),int(snap.get("game_number") or 1),checkpoint,
          now,t,str(snap.get("patch") or ""),blue,red,p0,
          float(b.get("gold") or 0)-float(r.get("gold") or 0),float(b.get("kills") or 0)-float(r.get("kills") or 0),
          float(b.get("towers") or 0)-float(r.get("towers") or 0),float(b.get("dragons") or 0)-float(r.get("dragons") or 0),
          float(b.get("barons") or 0)-float(r.get("barons") or 0),float(b.get("inhibitors") or 0)-float(r.get("inhibitors") or 0),
          diffs["top"],diffs["jng"],diffs["mid"],diffs["bot"],diffs["sup"],breadth,None,None,"Riot livestats prospective")
    with db_connect() as con:
        before=con.total_changes
        con.execute("""INSERT OR IGNORE INTO live_training_snapshots_v20
          (game_id,event_id,game_number,checkpoint_second,captured_at,game_time_seconds,patch,blue_team,red_team,draft_probability_blue,
           gold_diff,kill_diff,tower_diff,dragon_diff,baron_diff,inhibitor_diff,top_gold_diff,jng_gold_diff,mid_gold_diff,bot_gold_diff,sup_gold_diff,
           lead_breadth,outcome_blue,scored_at,capture_source)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",vals)
        changed=con.total_changes>before;con.commit()
    return {"captured":bool(changed),"checkpoint_second":checkpoint,"game_time_seconds":t}


def v20_score_live_training():
    rows=db_rows("""SELECT s.id,s.game_id,s.blue_team,g.winner
                    FROM live_training_snapshots_v20 s JOIN riot_games_v10 g ON g.game_id=s.game_id
                    WHERE s.outcome_blue IS NULL AND g.winner IS NOT NULL AND g.winner<>''""")
    if not rows:return 0
    now=datetime.now(timezone.utc).isoformat();n=0
    with db_connect() as con:
        for r in rows:
            y=1 if canonical(r.get("winner"))==canonical(r.get("blue_team")) else 0
            con.execute("UPDATE live_training_snapshots_v20 SET outcome_blue=?,scored_at=? WHERE id=?",(y,now,r["id"]));n+=1
        con.commit()
    return n


def v20_live_readiness():
    v20_score_live_training()
    policy={r["key"]:r["value"] for r in db_rows("SELECT * FROM live_readiness_policy_v20")}
    labeled=db_rows("SELECT * FROM live_training_snapshots_v20 WHERE outcome_blue IS NOT NULL")
    games={r["game_id"] for r in labeled}
    teams=set()
    for r in labeled:teams.update([r.get("blue_team"),r.get("red_team")])
    teams.discard(None)
    checkpoints={m:len({r["game_id"] for r in labeled if int(r.get("checkpoint_second") or -1)==m*60}) for m in (5,10,15,20,25,30)}
    game_outcome={}
    for r in labeled:game_outcome[r["game_id"]]=int(r["outcome_blue"])
    blue_rate=(sum(game_outcome.values())/len(game_outcome)) if game_outcome else None
    thresholds={"maps":int(policy.get("min_completed_maps",120)),"teams":int(policy.get("min_teams",8)),
                **{f"m{m}":int(policy.get(f"checkpoint_{m}",0)) for m in (5,10,15,20,25,30)}}
    checks={"maps":len(games)>=thresholds["maps"],"teams":len(teams)>=thresholds["teams"]}
    for m in (5,10,15,20,25,30):checks[f"m{m}"]=checkpoints[m]>=thresholds[f"m{m}"]
    balance_ok=blue_rate is None or (.35<=blue_rate<=.65);checks["class_balance"]=balance_ok
    ready=bool(games) and all(checks.values())
    status="READY_FOR_TRAINING" if ready else ("COLLECTING" if labeled or db_one("SELECT id FROM live_training_snapshots_v20 LIMIT 1") else "EMPTY")
    raw=int((db_one("SELECT COUNT(*) n FROM riot_live_snapshots_v10") or {}).get("n") or 0)
    unlabeled=int((db_one("SELECT COUNT(*) n FROM live_training_snapshots_v20 WHERE outcome_blue IS NULL") or {}).get("n") or 0)
    return {"status":status,"ready":ready,"completed_maps":len(games),"labeled_snapshots":len(labeled),"unlabeled_snapshots":unlabeled,
            "raw_snapshots":raw,"teams":len(teams),"blue_win_rate":blue_rate,"checkpoints":checkpoints,"thresholds":thresholds,"checks":checks,
            "policy":policy,"note":"Only in-progress snapshots are admitted. One compact row per game-minute is kept; terminal completed-state snapshots are excluded from live training."}


def v20_live_dataset_summary():
    ready=v20_live_readiness()
    latest=db_rows("""SELECT game_id,event_id,game_number,checkpoint_second,captured_at,blue_team,red_team,draft_probability_blue,
                      gold_diff,tower_diff,dragon_diff,baron_diff,outcome_blue
                      FROM live_training_snapshots_v20 ORDER BY id DESC LIMIT 12""")
    return {"readiness":ready,"latest":latest,
      "features":["draft_probability_blue","game_time/checkpoint","gold_diff","kill_diff","tower_diff","dragon_diff","baron_diff","inhibitor_diff",
                  "role_gold_diff(top/jng/mid/bot/sup)","lead_breadth"],
      "training_rule":"Training is blocked until the readiness gate passes. When it does, the first model must use chronological splits by game/event; random snapshot-level splitting is forbidden because snapshots from one map are highly correlated."}


# ---------------------------------------------------------------------------
# V28 — Automatic Draft Watcher
# ---------------------------------------------------------------------------
def v28_ensure_schema():
    with db_connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS riot_draft_captures_v28(
          event_id TEXT NOT NULL, game_id TEXT NOT NULL, game_number INTEGER,
          captured_at TEXT NOT NULL, blue_team TEXT, red_team TEXT,
          blue_picks_json TEXT, red_picks_json TEXT, locked_count INTEGER,
          complete INTEGER, patch TEXT, game_state TEXT, source TEXT, raw_json TEXT,
          PRIMARY KEY(event_id,game_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS riot_draft_watch_v28(
          event_id TEXT PRIMARY KEY, game_id TEXT, last_attempt TEXT, last_success TEXT,
          status TEXT, locked_count INTEGER, error TEXT
        )""")
        con.commit()

def _normalize_probe_side_v28(side):
    roles=["top","jng","mid","bot","sup"];picks={};parts=[]
    for i,p in enumerate(side.get("picks") or []):
        role=str(p.get("role") or "").lower()
        if role in ("jungle","jg"):role="jng"
        elif role in ("adc","bottom"):role="bot"
        elif role=="support":role="sup"
        elif role in ("middle","midlane"):role="mid"
        if role not in roles:role=roles[i] if i<len(roles) else None
        champ=canonical_champion_v10(p.get("champion")) if p.get("champion") else None
        if role and champ:picks[role]=champ
        parts.append({**p,"role":role,"champion":champ})
    return {"team":canonical(side.get("team")) or side.get("team"),"picks":picks,"participants":parts}

def _store_draft_probe_v28(probe):
    now=datetime.now(timezone.utc).isoformat()
    blue=_normalize_probe_side_v28(probe.get("blue") or {})
    red=_normalize_probe_side_v28(probe.get("red") or {})
    norm={**probe,"blue":blue,"red":red}
    draft_json=json.dumps({
      "blue":{"team":blue.get("team"),"picks":blue.get("picks") or {}},
      "red":{"team":red.get("team"),"picks":red.get("picks") or {}}
    },ensure_ascii=False,separators=(",",":"))
    with db_connect() as con:
        con.execute("""INSERT OR REPLACE INTO riot_draft_captures_v28
          (event_id,game_id,game_number,captured_at,blue_team,red_team,
           blue_picks_json,red_picks_json,locked_count,complete,patch,game_state,source,raw_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
          str(probe["event_id"]),str(probe["game_id"]),int(probe.get("game_number") or 1),now,
          blue.get("team"),red.get("team"),
          json.dumps(blue,ensure_ascii=False,separators=(",",":")),
          json.dumps(red,ensure_ascii=False,separators=(",",":")),
          int(probe.get("locked_count") or 0),1 if probe.get("complete") else 0,
          probe.get("patch"),probe.get("game_state"),probe.get("source"),
          json.dumps(norm,ensure_ascii=False,separators=(",",":"))
        ))
        con.execute("""INSERT OR IGNORE INTO riot_games_v10
          (game_id,event_id,game_number,state,patch,blue_team,red_team,draft_json,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",(
          str(probe["game_id"]),str(probe["event_id"]),int(probe.get("game_number") or 1),
          probe.get("game_state"),probe.get("patch"),blue.get("team"),red.get("team"),draft_json,now
        ))
        con.execute("""UPDATE riot_games_v10 SET event_id=?,game_number=?,
          state=COALESCE(?,state),patch=COALESCE(?,patch),
          blue_team=COALESCE(?,blue_team),red_team=COALESCE(?,red_team),
          draft_json=?,updated_at=? WHERE game_id=?""",(
          str(probe["event_id"]),int(probe.get("game_number") or 1),probe.get("game_state"),
          probe.get("patch"),blue.get("team"),red.get("team"),draft_json,now,str(probe["game_id"])
        ))
        con.execute("""INSERT OR REPLACE INTO riot_draft_watch_v28
          (event_id,game_id,last_attempt,last_success,status,locked_count,error)
          VALUES(?,?,?,?,?,?,?)""",(
          str(probe["event_id"]),str(probe["game_id"]),now,now,
          "CAPTURED" if probe.get("complete") else "PARTIAL",
          int(probe.get("locked_count") or 0),None
        ))
        con.commit()
    return norm

def _latest_draft_capture_v28(event_id=None):
    row=db_one("""SELECT raw_json FROM riot_draft_captures_v28
                  WHERE event_id=? ORDER BY game_number DESC,captured_at DESC LIMIT 1""",(str(event_id),)) if event_id else \
        db_one("SELECT raw_json FROM riot_draft_captures_v28 ORDER BY captured_at DESC LIMIT 1")
    if not row:return None
    try:return json.loads(row["raw_json"])
    except:return None

def _auto_eval_draft_v28(cap):
    if not cap or int(cap.get("locked_count") or 0)<10:return None
    blue=cap.get("blue") or {};red=cap.get("red") or {}
    a=canonical(blue.get("team")) or blue.get("team");b=canonical(red.get("team")) or red.get("team")
    if a not in FULL_NAMES or b not in FULL_NAMES:return None
    fearless=_prior_fearless(cap.get("event_id"),cap.get("game_number") or 1)
    out=evaluate_draft({"team_a":a,"team_b":b,"side_a":"Blue","patch":cap.get("patch"),
                        "picks_a":blue.get("picks") or {},"picks_b":red.get("picks") or {},
                        "fearless_used":fearless})
    if out.get("error"):return None
    return {"team_a":a,"team_b":b,"probability_team_a":out.get("draft_game_probability_team_a"),
            "evidence_confidence":out.get("evidence_confidence"),"model":"V8 audited draft core"}

def draft_status_v28(event_id=None,force=False):
    v28_ensure_schema()
    eid=str(event_id) if event_id else None;sync=None
    if not eid:
        live=[x for x in _riot_event_items_v11() if x.get("status")=="live"]
        if live:eid=str(live[0].get("event_id"))
        if not eid:
            sync=sync_live_now_v27()
            if sync.get("event_id"):eid=str(sync["event_id"])
    if not eid:
        return {"ok":False,"status":"SEARCHING_EVENT","event_id":None,"locked_count":0,
                "fallback":(sync or {}).get("fallback") or _fallback_live_candidate_v27(),
                "note":"Partida detectada; procurando Riot Event ID/Game ID."}

    cap=_latest_draft_capture_v28(eid);err=None
    if force:
        now=datetime.now(timezone.utc).isoformat()
        try:
            cap=_store_draft_probe_v28(riot_fetch_draft_probe(eid))
        except Exception as e:
            err=f"{type(e).__name__}: {e}"
            with db_connect() as con:
                con.execute("""INSERT OR REPLACE INTO riot_draft_watch_v28
                  (event_id,game_id,last_attempt,last_success,status,locked_count,error)
                  VALUES(?,?,?,?,?,?,?)""",(eid,(cap or {}).get("game_id"),now,None,"WAITING_METADATA",
                    int((cap or {}).get("locked_count") or 0),err))
                con.commit()
    if cap:
        return {"ok":True,"status":"CAPTURED" if cap.get("complete") else "PARTIAL",
                "event_id":eid,"game_id":cap.get("game_id"),"game_number":cap.get("game_number"),
                "locked_count":int(cap.get("locked_count") or 0),"complete":bool(cap.get("complete")),
                "blue":cap.get("blue"),"red":cap.get("red"),"patch":cap.get("patch"),
                "auto_evaluation":_auto_eval_draft_v28(cap),"source":cap.get("source"),"error":err}
    return {"ok":False,"status":"WAITING_METADATA","event_id":eid,"locked_count":0,"error":err,
            "note":"Event/Game ID encontrado; aguardando champion metadata da Riot."}

def auto_draft_watch_v28(event_id):
    try:return draft_status_v28(event_id,True)
    except Exception:return None


# ---------------------------------------------------------------------------
# Live game drafts (multi-league discovery + draft capture)
# ---------------------------------------------------------------------------
RIOT_TEAM_ALIASES = {
    "gen.g esports": "GEN",
    "nongshim red force": "NS",
    "nongshim redforce": "NS",
    "dplus kia": "DK",
    "hanwha life esports": "HLE",
}
RIOT_CONTEXT_ONLY_LEAGUES = {"lck challengers", "lck challengers league"}

def _fold_name(x):
    s = unicodedata.normalize("NFKD", str(x or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


_TEAM_CODE_INDEX = None
def _team_code_index():
    global _TEAM_CODE_INDEX
    if _TEAM_CODE_INDEX is None:
        idx = {}
        for code, full in FULL_NAMES.items():
            idx[_fold_name(code)] = code
            idx[_fold_name(full)] = code
        for name, code in ALIASES.items():
            idx.setdefault(_fold_name(name), code)
        for name, code in RIOT_TEAM_ALIASES.items():
            idx[_fold_name(name)] = code
        _TEAM_CODE_INDEX = idx
    return _TEAM_CODE_INDEX


def match_team_code(name, code=None):
    c = canonical(name) or canonical(code)
    if c:
        return c
    idx = _team_code_index()
    for raw in (name, code):
        if raw:
            c2 = idx.get(_fold_name(raw))
            if c2:
                return c2
    return None


_PLAYER_ROSTER_INDEX = None
def _player_roster_index():
    global _PLAYER_ROSTER_INDEX
    if _PLAYER_ROSTER_INDEX is None:
        idx = {}
        for r in db_rows("SELECT DISTINCT player FROM draft_rosters WHERE player IS NOT NULL"):
            idx.setdefault(_fold_name(r["player"]), r["player"])
        for r in db_rows("SELECT DISTINCT player FROM draft_player_overall WHERE player IS NOT NULL"):
            idx.setdefault(_fold_name(r["player"]), r["player"])
        _PLAYER_ROSTER_INDEX = idx
    return _PLAYER_ROSTER_INDEX


def canonical_player(raw, team_code=None):
    if not raw:
        return None
    raw = " ".join(str(raw).split())
    candidates = [raw]
    if team_code:
        if raw.lower().startswith(team_code.lower()):
            rest = raw[len(team_code):].strip()
            if rest:
                candidates.append(rest)
    if " " in raw:
        candidates.append(raw.split(" ", 1)[1].strip())
    idx = _player_roster_index()
    for c in candidates:
        canon = idx.get(_fold_name(c))
        if canon:
            return canon
    return raw


def live_games_api(league_ids=None):
    try:
        games = riot_discover_live_games(league_ids=league_ids)
    except Exception as e:
        return {"ok": False, "games": [], "error": f"{type(e).__name__}: {e}"}
    for g in games:
        league = _fold_name(g.get("league"))
        context_only = league in {_fold_name(x) for x in RIOT_CONTEXT_ONLY_LEAGUES}
        g["blueLocal"] = None if context_only else match_team_code(g.get("blueTeam"), g.get("blueCode"))
        g["redLocal"] = None if context_only else match_team_code(g.get("redTeam"), g.get("redCode"))
    return {"ok": True, "games": games, "count": len(games)}


def live_draft_api(game_id):
    if not game_id:
        return {"ok": False, "error": "gameId obrigatório"}
    try:
        d = riot_fetch_live_draft(game_id)
    except riot_DraftNotReady as e:
        return {"ok": False, "error": "DRAFT_NOT_READY", "detail": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    for side in ("blue", "red"):
        team_code=(d.get("team_codes") or {}).get(side)
        for p in d.get(side) or []:
            p["champion"] = canonical_champion_v10(p.get("champion")) or p.get("champion")
            p["player"] = canonical_player(p.get("player"), team_code)
    return {"ok": True, **d}


class Handler(BaseHTTPRequestHandler):
    server_version="LCKPredictorPortable/1.0"

    def log_message(self, fmt, *args):
        # Keep the console clean.
        pass

    def send_json(self,obj,status=200):
        body=json_bytes(obj)
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self,path):
        path=path.resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            self.send_error(404); return
        ctype=mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body=path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma","no-cache")
        self.send_header("Expires","0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        path=parsed.path

        if path=="/api/v21/governance":
            self.send_json(v21_governance_summary()); return
        if path=="/api/v20/live-readiness":
            self.send_json(v20_live_dataset_summary()); return
        if path=="/api/v19/validation":
            self.send_json(v19_validation_summary()); return
        if path=="/api/health":
            self.send_json({"ok":True,"portable":True,"database":DB.name,
                            "app_version":APP_VERSION,"port":PORT,
                            "server_time":datetime.now(timezone.utc).isoformat(),
                            "primary_match_feed":"Riot LoL Esports",
                            "live_model":"experimental / not calibrated"}); return
        if path=="/api/v24/qa":
            self.send_json({"schedule":v24_schedule_audit(),"integrity":v21_integrity_report(),
                            "version":"V24 QA Review"}); return
        if path=="/api/v14/series-context":
            qs=urllib.parse.parse_qs(parsed.query)
            event_id=(qs.get("event_id") or [""])[0]
            game=(qs.get("game_number") or [None])[0]
            out=series_context_v14(event_id,int(game) if game else None)
            self.send_json(out,400 if out.get("error") else 200); return
        if path=="/api/v14/draft/sequence":
            qs=urllib.parse.parse_qs(parsed.query)
            payload={"team_a":(qs.get("team_a") or [""])[0],
                     "team_b":(qs.get("team_b") or [""])[0],
                     "side_a":(qs.get("side_a") or ["Blue"])[0]}
            self.send_json(draft_sequence_v14(payload)); return
        if path=="/api/v13/history/coverage":
            self.send_json(history_coverage_v13()); return
        if path=="/api/v12/home":
            self.send_json(v12_home()); return
        if path=="/api/v12/team_assets":
            self.send_json(v23_team_assets()); return
        if path=="/api/v12/matches":
            qs=urllib.parse.parse_qs(parsed.query)
            status=(qs.get("status") or ["all"])[0]
            limit=int((qs.get("limit") or ["500"])[0])
            self.send_json(v12_match_items(status,limit)); return
        if path=="/api/v12/match":
            qs=urllib.parse.parse_qs(parsed.query)
            ident=(qs.get("id") or [""])[0]
            obj=v12_unified_match(ident)
            self.send_json(obj or {"error":"Partida não encontrada"},200 if obj else 404); return
        if path=="/api/v12/players":
            qs=urllib.parse.parse_qs(parsed.query)
            self.send_json(v12_player_list((qs.get("team") or [None])[0],(qs.get("role") or [None])[0],
                                           (qs.get("q") or [None])[0],int((qs.get("limit") or ["200"])[0]))); return
        if path=="/api/v12/player":
            qs=urllib.parse.parse_qs(parsed.query)
            self.send_json(v12_player_detail((qs.get("name") or [""])[0])); return
        if path=="/api/v12/champions":
            qs=urllib.parse.parse_qs(parsed.query)
            self.send_json(v12_champion_list((qs.get("role") or [None])[0],(qs.get("q") or [None])[0],
                                             int((qs.get("limit") or ["250"])[0]))); return
        if path=="/api/v12/champion":
            qs=urllib.parse.parse_qs(parsed.query)
            self.send_json(v12_champion_detail((qs.get("name") or [""])[0],(qs.get("role") or [None])[0])); return
        if path=="/api/v12/team":
            qs=urllib.parse.parse_qs(parsed.query)
            self.send_json(v12_team_detail((qs.get("name") or [""])[0])); return
        if path=="/api/match-center":
            qs=urllib.parse.parse_qs(parsed.query)
            status=(qs.get("status") or ["all"])[0]
            team=(qs.get("team") or [None])[0]
            year=(qs.get("year") or [None])[0]
            limit=int((qs.get("limit") or ["500"])[0])
            self.send_json(match_center_v11(status,team,year,limit)); return
        if path=="/api/match-center/detail":
            qs=urllib.parse.parse_qs(parsed.query)
            ident=(qs.get("id") or [""])[0]
            if ident.startswith("hist:"):
                obj=historical_detail_v11(ident[5:])
            elif ident.startswith("riot:"):
                obj=riot_detail_v11(ident[5:])
            else: obj=None
            self.send_json(obj or {"error":"Partida não encontrada"},200 if obj else 404); return
        if path=="/api/riot/events":
            self.send_json(riot_events_api_v10()); return
        if path=="/api/riot/source-health":
            self.send_json(db_rows("SELECT * FROM riot_source_health_v10 ORDER BY source")); return
        if path=="/api/riot/models":
            self.send_json(db_rows("SELECT * FROM model_registry_v10 ORDER BY rowid")); return
        if path=="/api/riot/case-studies":
            self.send_json(db_rows("SELECT * FROM live_case_studies_v10 ORDER BY event_id,game_number")); return
        if path=="/api/v28/draft/status":
            qs=urllib.parse.parse_qs(parsed.query)
            event=(qs.get("event_id") or [None])[0]
            force=(qs.get("refresh") or ["0"])[0]!="0"
            self.send_json(draft_status_v28(event,force)); return
        if path=="/api/live-games":
            qs=urllib.parse.parse_qs(parsed.query)
            league_ids=[x for x in qs.get("leagueId",[]) if x]
            self.send_json(live_games_api(league_ids or None)); return
        if path=="/api/live-draft":
            qs=urllib.parse.parse_qs(parsed.query)
            game=(qs.get("gameId") or qs.get("game_id") or [""])[0]
            out=live_draft_api(game)
            self.send_json(out,404 if out.get("error")=="DRAFT_NOT_READY" else 200); return
        if path=="/api/riot/live":
            qs=urllib.parse.parse_qs(parsed.query)
            event=(qs.get("event_id") or [None])[0]
            force=(qs.get("refresh") or ["1"])[0]!="0"
            self.send_json(live_response_v10(event,force)); return
        if path=="/api/riot/timeline":
            qs=urllib.parse.parse_qs(parsed.query)
            game=(qs.get("game_id") or [""])[0]
            self.send_json(live_timeline_v10(game,500) if game else []); return
        if path=="/api/bootstrap":
            self.send_json(api_bootstrap()); return
        if path=="/api/rankings":
            self.send_json(db_rows("SELECT * FROM current_ratings ORDER BY rank")); return
        if path=="/api/upcoming":
            try: out=db_rows("SELECT * FROM upcoming_matches ORDER BY date,team_a")
            except sqlite3.OperationalError: out=[]
            self.send_json(out); return
        if path=="/api/statistics/audit":
            self.send_json({
                "audit":db_rows("SELECT * FROM statistical_audit_v8"),
                "confidence_intervals":db_rows("SELECT * FROM statistical_ci_v8"),
                "reliability":db_rows("SELECT * FROM statistical_reliability_v8 ORDER BY bin"),
                "patch_holdout":db_rows("SELECT * FROM statistical_patch_holdout_v8 ORDER BY patch"),
                "scoreline":db_rows("SELECT * FROM scoreline_validation_v9"),
                "calibration":{"slope":float(db_one("SELECT value FROM metadata WHERE key='calibration_slope'")["value"]),
                               "intercept":float(db_one("SELECT value FROM metadata WHERE key='calibration_intercept'")["value"]),
                               "ece":float(db_one("SELECT value FROM metadata WHERE key='ece_10bin'")["value"])}
            }); return
        if path=="/api/patch/bootstrap":
            self.send_json(patch_bootstrap()); return
        if path.startswith("/api/patch/") and path!="/api/patch/bootstrap":
            p=urllib.parse.unquote(path.split("/",3)[3])
            self.send_json(patch_detail(p)); return
        if path=="/api/draft/bootstrap":
            self.send_json(draft_bootstrap()); return
        if path=="/api/model":
            self.send_json({"evaluation":db_rows("SELECT * FROM model_evaluation"),
                            "metadata":{x["key"]:x["value"] for x in db_rows("SELECT key,value FROM metadata")}}); return
        if path.startswith("/api/team/"):
            team=urllib.parse.unquote(path.split("/",3)[3]).upper()
            rating=db_one("SELECT * FROM current_ratings WHERE team=?",(team,))
            if not rating: self.send_json({"detail":"Team not found"},404); return
            hist=db_rows("""SELECT date,team1,team2,winner,wins1,wins2,n_games,source
                            FROM series_history WHERE team1=? OR team2=?
                            ORDER BY date DESC LIMIT 30""",(team,team))
            self.send_json({"rating":rating,"history":hist}); return
        if path.startswith("/api/match/"):
            parts=path.split("/")
            if len(parts)>=5:
                out=api_match(urllib.parse.unquote(parts[3]),urllib.parse.unquote(parts[4]))
                if out: self.send_json(out); return
            self.send_json({"detail":"Match not found"},404); return

        if path=="/manifest.webmanifest":
            self.send_file(STATIC/"manifest.webmanifest"); return
        if path=="/sw.js":
            self.send_file(STATIC/"sw.js"); return
        if path.startswith("/static/"):
            rel=path[len("/static/"):]
            self.send_file(STATIC/rel); return
        # SPA fallback
        self.send_file(STATIC/"index.html")



    def do_POST(self):
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path=="/api/v18/draft/series-plan":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=series_plan_v18(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v17/draft/joint-plan":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=joint_draft_plan_v17(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v16/draft/flex-tree":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=draft_flex_tree_v16(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v15/draft/tree":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=draft_tree_v15(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v15/draft/flex-resolve":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=flex_resolve_v15(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v14/draft/strategy-pick":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=draft_strategy_pick_v14(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v14/draft/ban":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=draft_ban_strategy_v14(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v13/draft/recommend":
            try:
                n=int(self.headers.get("Content-Length","0"))
                payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                out=draft_recommend_v13(payload)
                self.send_json(out,400 if out.get("error") else 200)
            except Exception as e:
                self.send_json({"detail":f"{type(e).__name__}: {e}"},500)
            return
        if parsed.path=="/api/v27/live/refresh":
            try:
                out=sync_live_now_v27()
                out["live_items"]=v12_match_items("live",10)
                self.send_json(out,200 if out.get("ok") else 503)
            except Exception as e:
                self.send_json({"ok":False,"detail":f"{type(e).__name__}: {e}",
                                "live_items":v12_match_items("live",10)},500)
            return
        if parsed.path=="/api/v23/schedule/refresh":
            try:
                sched=refresh_riot_schedule_v10()
                try:added=archive_completed_series_v10()
                except Exception:added=0
                removed=prune_stale_schedule_v23()
                self.send_json({"ok":bool(sched.get("ok")),"schedule":sched,
                                "completed_series_added":added,"stale_rows_removed":removed,
                                "status":v23_schedule_status()})
            except Exception as e:
                self.send_json({"ok":False,"detail":f"{type(e).__name__}: {e}",
                                "status":v23_schedule_status()},500)
            return
        if parsed.path=="/api/riot/refresh":
            sched=refresh_riot_schedule_v10()
            live=live_response_v10(None,True)
            added=archive_completed_series_v10()
            backfill=backfill_recent_riot_games_v10(6)
            try:
                v19_score_prospective()
                v20_score_live_training()
                v21_refresh_promotion_reviews()
            except Exception:pass
            self.send_json({"schedule":sched,"live":live,"completed_series_added":added,
                            "game_backfill":backfill}); return
        if parsed.path=="/api/draft/refresh":
            self.send_json(refresh_draft_web_cache()); return
        if parsed.path!="/api/draft/evaluate":
            self.send_json({"detail":"Not found"},404); return
        try:
            n=int(self.headers.get("Content-Length","0"))
            payload=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            out=evaluate_draft(payload)
            if out.get("error"):
                self.send_json(out,400)
            else:
                self.send_json(out)
        except Exception as e:
            self.send_json({"detail":f"{type(e).__name__}: {e}"},500)


def background_updater():
    time.sleep(3)
    last_schedule=0.0
    last_discover=0.0
    last_gol=0.0
    last_draft=0.0
    last_draft_watch=0.0
    last_backfill=0.0
    active_event=None
    while True:
        now=time.time()
        if now-last_schedule>=RIOT_SCHEDULE_SECONDS:
            refresh_riot_schedule_v10()
            try:archive_completed_series_v10()
            except Exception:pass
            last_schedule=now
        if now-last_discover>=RIOT_DISCOVER_SECONDS or not active_event:
            ev=discover_lck_live_event_v10()
            active_event=str(ev["id"]) if ev else None
            if not active_event and _fallback_live_candidate_v27():
                try:
                    synced=sync_live_now_v27()
                    active_event=str(synced.get("event_id")) if synced.get("event_id") else None
                except Exception:pass
            last_discover=now
        if active_event and now-last_draft_watch>=DRAFT_WATCH_SECONDS:
            auto_draft_watch_v28(active_event)
            last_draft_watch=now
        if active_event:
            result=live_response_v10(active_event,True)
            # A feed between games may be unavailable; keep the event and retry.
            if result.get("snapshot") and str((result["snapshot"].get("event_state") or "")).lower()=="completed":
                active_event=None
        if now-last_gol>=3600:
            try:try_auto_update()
            except Exception:pass
            last_gol=now
        if now-last_backfill>=1800:
            try:
                backfill_recent_riot_games_v10(3)
                v19_score_prospective()
                v20_score_live_training()
                v21_refresh_promotion_reviews()
            except Exception:pass
            last_backfill=now
        if now-last_draft>=21600:
            try:refresh_draft_web_cache()
            except Exception:pass
            last_draft=now
        time.sleep(5 if (active_event or _fallback_live_candidate_v27()) else 20)


def main():
    if not DB.exists():
        print("ERRO: banco de dados não encontrado:", DB)
        input("Pressione ENTER para fechar...")
        return 2
    _enable_wal_once()
    v21_ensure_schema()
    v23_ensure_schedule_schema()
    prune_stale_schedule_v23()
    integrity=v21_integrity_report()
    if not integrity.get("ok"):
        v21_log_event("ERROR","RELEASE_INTEGRITY_DRIFT",integrity)
        print("AVISO: drift detectado nos arquivos de governança. Capturas V19 divergentes serão bloqueadas.")
    threading.Thread(target=background_updater,daemon=True).start()
    collector_only=os.environ.get("LCK_COLLECTOR_ONLY","0")=="1"
    url=f"http://localhost:{PORT}/?build=V28_AUTO_DRAFT#home"
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    print("="*58)
    print(" LCK PREDICTOR V28 - AUTO DRAFT" + (" - COLLECTOR" if collector_only else ""))
    print("="*58)
    print()
    print("Servidor iniciado com sucesso.")
    print("Endereco:",url)
    if collector_only:
        print("Modo coletor: o navegador nao sera aberto.")
        print("Deixe esta janela rodando durante partidas LCK para acumular snapshots prospectivos.")
    else:
        print("App iniciado com interface web.")
    print()
    print("Esta janela mantém o servidor ligado.")
    print("Para fechar, feche esta janela ou pressione Ctrl+C.")
    print()
    if not collector_only:
        threading.Timer(1.0,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        server.server_close()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
