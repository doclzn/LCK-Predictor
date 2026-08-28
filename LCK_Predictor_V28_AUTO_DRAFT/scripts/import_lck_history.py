from __future__ import annotations
import argparse,csv,sqlite3,json,re,sys
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=ROOT/"data"/"lck_data_v1.sqlite"

ROLES={"top":"top","jng":"jng","jungle":"jng","mid":"mid","middle":"mid",
       "bot":"bot","bottom":"bot","adc":"bot","sup":"sup","support":"sup"}

def n(v,default=None):
    if v is None or str(v).strip()=="":
        return default
    try:
        x=float(str(v).replace(",",""))
        return int(x) if x.is_integer() else x
    except:
        return default

def text(row,*names):
    for k in names:
        if k in row and row[k] not in (None,""):
            return str(row[k]).strip()
    return ""

def day_of(x):
    return str(x or "")[:10]

def is_lck(row):
    league=text(row,"league").upper()
    return league=="LCK" or league.startswith("LCK ")

def source_year(path,row=None):
    if row:
        y=n(row.get("year"))
        if y:return int(y)
    m=re.search(r"(20\d{2})",path.name)
    return int(m.group(1)) if m else None

def game_key(row,path):
    gid=text(row,"gameid")
    league=text(row,"league")
    year=source_year(path,row)
    if gid:return f"{league}:{gid}"
    return f"{league}:{year}:{text(row,'date')}:{text(row,'game')}:{text(row,'teamname','team')}"

def normalize_role(v):
    return ROLES.get(str(v or "").strip().lower(),str(v or "").strip().lower())

def read_file(path):
    raw=0;lck=0
    games={}
    players=[]
    with path.open("r",encoding="utf-8-sig",errors="replace",newline="") as f:
        rd=csv.DictReader(f)
        for row in rd:
            raw+=1
            if not is_lck(row):continue
            lck+=1
            gk=game_key(row,path)
            pos=normalize_role(text(row,"position"))
            side=text(row,"side").lower()
            team=text(row,"teamname","team")
            result=int(n(row.get("result"),0) or 0)
            year=source_year(path,row)
            date=text(row,"date")
            game_num=n(row.get("game"))
            patch=text(row,"patch","patchno")
            gl=n(row.get("gamelength"))
            # Modern OE uses seconds; old files may use minutes. Normalize cautiously.
            gl_sec=float(gl) if gl is not None else None
            if gl_sec is not None and gl_sec<300:
                gl_sec*=60

            if pos=="team":
                g=games.setdefault(gk,{
                    "game_key":gk,"gameid":text(row,"gameid"),"year":year,"date":date,
                    "league":text(row,"league"),"split":text(row,"split"),"playoffs":int(n(row.get("playoffs"),0) or 0),
                    "game_number":int(game_num) if game_num is not None else None,"patch":patch,
                    "blue_team":None,"red_team":None,"winner":None,
                    "blue_kills":None,"red_kills":None,"blue_gold":None,"red_gold":None,
                    "blue_towers":None,"red_towers":None,"blue_dragons":None,"red_dragons":None,
                    "blue_barons":None,"red_barons":None,"game_length_seconds":gl_sec,
                    "source_file":path.name
                })
                prefix="blue" if side=="blue" else "red"
                g[prefix+"_team"]=team
                g[prefix+"_kills"]=n(row.get("kills") or row.get("teamkills"))
                g[prefix+"_gold"]=n(row.get("totalgold"))
                g[prefix+"_towers"]=n(row.get("towers"))
                g[prefix+"_dragons"]=n(row.get("dragons"))
                g[prefix+"_barons"]=n(row.get("barons"))
                if result:g["winner"]=team
            elif pos in ("top","jng","mid","bot","sup"):
                players.append({
                    "game_key":gk,"year":year,"date":date,"team":team,"side":side,"role":pos,
                    "player":text(row,"playername","player"),"champion":text(row,"champion"),
                    "result":result,"kills":int(n(row.get("kills") or row.get("k"),0) or 0),
                    "deaths":int(n(row.get("deaths") or row.get("d"),0) or 0),
                    "assists":int(n(row.get("assists") or row.get("a"),0) or 0),
                    "gold":n(row.get("totalgold")),"cs":n(row.get("total cs") or row.get("totalcs")),
                    "dpm":n(row.get("dpm")),"gd10":n(row.get("golddiffat10") or row.get("gdat10")),
                    "gd15":n(row.get("golddiffat15") or row.get("gdat15")),
                    "xp10":n(row.get("xpdiffat10") or row.get("xpdat10")),
                    "xp15":n(row.get("xpdiffat15") or row.get("xpdat15")),
                    "csd10":n(row.get("csdiffat10") or row.get("csdat10")),
                    "csd15":n(row.get("csdiffat15") or row.get("csdat15")),
                    "source_file":path.name
                })
    # Remove malformed games missing one side.
    games=[g for g in games.values() if g["blue_team"] and g["red_team"] and g["winner"]]
    game_keys={g["game_key"] for g in games}
    players=[p for p in players if p["game_key"] in game_keys]
    return raw,lck,games,players

def rebuild_series(con):
    rows=[dict(zip([d[0] for d in cur.description],r)) for cur in [con.execute(
        """SELECT game_key,year,date,split,playoffs,game_number,blue_team,red_team,winner,source_file
           FROM lck_alltime_games_v13 ORDER BY year,date,game_number,game_key""")] for r in cur.fetchall()]
    # Group day/pair/split; split a new series whenever game number returns to 1.
    buckets={}
    for g in rows:
        teams=tuple(sorted([g["blue_team"],g["red_team"]]))
        base=(g["year"],day_of(g["date"]),g["split"],g["playoffs"],teams)
        buckets.setdefault(base,[]).append(g)

    con.execute("DELETE FROM lck_alltime_series_v13")
    for base,gs in buckets.items():
        gs.sort(key=lambda x:(x["date"] or "",x["game_number"] or 999,x["game_key"]))
        segments=[];cur=[]
        for g in gs:
            if cur and g.get("game_number")==1:
                segments.append(cur);cur=[]
            cur.append(g)
        if cur:segments.append(cur)
        for idx,seg in enumerate(segments,1):
            year,day,split,playoffs,teams=base
            wins={teams[0]:0,teams[1]:0}
            for g in seg:
                if g["winner"] in wins:wins[g["winner"]]+=1
            if wins[teams[0]]==wins[teams[1]]:
                continue
            winner=teams[0] if wins[teams[0]]>wins[teams[1]] else teams[1]
            suffix=f":{idx}" if len(segments)>1 else ""
            key=f"{year}:{day}:{teams[0]}|{teams[1]}:{split}:{playoffs}{suffix}"
            con.execute("""INSERT OR REPLACE INTO lck_alltime_series_v13
              (series_key,year,date,team_a,team_b,winner,wins_a,wins_b,games,source_files)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (key,year,day,teams[0],teams[1],winner,wins[teams[0]],wins[teams[1]],len(seg),
               json.dumps(sorted({g["source_file"] for g in seg}),ensure_ascii=False)))

def import_one(path,db):
    raw,lck,games,players=read_file(path)
    if not games:
        return {"file":path.name,"raw":raw,"lck":lck,"games":0,"status":"NO_LCK_GAMES"}
    with sqlite3.connect(db) as con:
        con.row_factory=sqlite3.Row
        for g in games:
            cols=list(g); con.execute(
                f"""INSERT OR REPLACE INTO lck_alltime_games_v13({','.join(cols)})
                    VALUES({','.join('?' for _ in cols)})""",[g[c] for c in cols])
        for p in players:
            cols=list(p); con.execute(
                f"""INSERT OR REPLACE INTO lck_alltime_player_games_v13({','.join(cols)})
                    VALUES({','.join('?' for _ in cols)})""",[p[c] for c in cols])
        rebuild_series(con)
        year=source_year(path)
        series=con.execute("SELECT COUNT(*) FROM lck_alltime_series_v13 WHERE year=?",(year,)).fetchone()[0] if year else 0
        teams=con.execute("""SELECT COUNT(DISTINCT team) FROM (
            SELECT blue_team team FROM lck_alltime_games_v13 WHERE year=?
            UNION SELECT red_team team FROM lck_alltime_games_v13 WHERE year=?)""",(year,year)).fetchone()[0] if year else 0
        pls=con.execute("SELECT COUNT(DISTINCT player) FROM lck_alltime_player_games_v13 WHERE year=?",(year,)).fetchone()[0] if year else 0
        con.execute("""INSERT OR REPLACE INTO history_import_manifest_v13
          (source_file,source_year,imported_at,raw_rows,lck_rows,lck_games,lck_series,players,teams,status,note)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (path.name,year,datetime.now(timezone.utc).isoformat(),raw,lck,len(games),series,pls,teams,
           "OK","Imported locally; historical data is kept separate from the current predictive model."))
        con.commit()
    return {"file":path.name,"year":year,"raw":raw,"lck":lck,"games":len(games),"players_rows":len(players),"series":series,"status":"OK"}

def main():
    ap=argparse.ArgumentParser(description="Import locally obtained Oracle's Elixir-style CSVs into the LCK all-time archive.")
    ap.add_argument("paths",nargs="+",help="CSV file(s) or directory/directories")
    ap.add_argument("--db",default=str(DEFAULT_DB))
    args=ap.parse_args()
    db=Path(args.db)
    files=[]
    for raw in args.paths:
        p=Path(raw).expanduser()
        if p.is_dir():files.extend(sorted(p.glob("*.csv")))
        elif p.suffix.lower()==".csv":files.append(p)
    if not files:
        print("No CSV files found.");return 2
    print("LCK historical importer")
    print("Database:",db)
    print("Files:",len(files))
    results=[]
    for i,p in enumerate(files,1):
        print(f"[{i}/{len(files)}] {p.name}")
        try:
            r=import_one(p,db);results.append(r)
            print(" ",r)
        except Exception as e:
            print("  ERROR",type(e).__name__,e)
            results.append({"file":p.name,"status":"ERROR","error":f"{type(e).__name__}: {e}"})
    ok=sum(r.get("status")=="OK" for r in results)
    print()
    print(f"Done: {ok}/{len(results)} files imported.")
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
