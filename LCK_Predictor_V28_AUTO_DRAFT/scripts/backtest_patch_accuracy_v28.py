"""Backtest cronologico do modelo de producao (Series Elo K=64) por patch.

Replica exatamente recalc_ratings/elo_prob do server.py: percorre
series_history em ordem cronologica, registra a probabilidade pre-jogo
(antes de atualizar o Elo) e compara com o vencedor real.

Mapeamento de patch:
- Ate o ultimo jogo rotulado em team_games, o patch vem do proprio dado.
- Depois disso, o patch e derivado do calendario da Riot (ciclos de 14
  dias, lancamento na quarta-feira), ancorado no ultimo patch rotulado.
  A regra "primeira quarta apos o fim do patch anterior" reproduz todos
  os inicios de patch observados em team_games e e validada contra o
  patch do feed Riot capturado em riot_games_v10.

Avalia os ultimos 4 patches reais do LoL (serie 16.13-16.16) e mantem o
recorte dos ultimos 4 patches rotulados na base (16.08-16.11) como contexto.
"""
from datetime import date,timedelta
from pathlib import Path
import json,math,sqlite3
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"data"/"lck_data_v1.sqlite"
BASE_ELO=1500.0
ELO_K=64.0
SEASON_DECAY=0.65


def elo_prob(a,b):
    return 1.0/(1.0+10.0**(-(float(a)-float(b))/400.0))


def parse_patch(p):
    x=float(p)
    major=int(x)
    return (major,round((x-major)*100))


def patch_label(pm):
    if isinstance(pm,str):return pm
    return f"{pm[0]}.{pm[1]:02d}"


def first_wednesday_after(d):
    off=(2-d.weekday())%7
    return d+timedelta(days=off if off else 7)


def build_patch_calendar(con,last_labeled):
    """Releases por patch: rotulados via team_games, futuro por ciclos de 14 dias."""
    win={}
    for r in con.execute("""SELECT patch,MIN(substr(date,1,10)) d0,MAX(substr(date,1,10)) d1
                            FROM team_games GROUP BY patch"""):
        win[parse_patch(r["patch"])]=(r["d0"],r["d1"])
    ordered=sorted(win)
    releases={}
    for i,pm in enumerate(ordered):
        if i==0:
            releases[pm]=date.fromisoformat(win[pm][0])
            continue
        releases[pm]=first_wednesday_after(date.fromisoformat(win[ordered[i-1]][1]))
    anchor=releases[last_labeled]
    k=1
    while True:
        pm=(last_labeled[0],last_labeled[1]+k)
        releases[pm]=anchor+timedelta(days=14*k)
        if releases[pm]>date.today():break
        k+=1
    return win,releases


def calendar_patch_for_day(releases,day):
    d=date.fromisoformat(day)
    best=None
    for pm,rel in releases.items():
        if rel<=d and (best is None or pm>best):best=pm
    return best


def main():
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    series=con.execute("""SELECT date,year,team1,team2,winner,wins1,wins2
                          FROM series_history ORDER BY date,series_key""").fetchall()
    # day+teams -> patch rotulado (moda dos games da serie)
    patch_of={}
    last_labeled_day="";last_labeled_patch=None
    for r in con.execute("""SELECT substr(date,1,10) day,team,patch FROM team_games"""):
        patch_of.setdefault(r["day"],defaultdict(list))[r["team"]].append(float(r["patch"]))
        if r["day"]>last_labeled_day:
            last_labeled_day=r["day"];last_labeled_patch=parse_patch(r["patch"])
    # day -> games, uma linha por game usando somente o lado Blue
    games_by_day=defaultdict(list)
    seen=set()
    for r in con.execute("""SELECT gameid,substr(date,1,10) day,team,side,result
                            FROM team_games WHERE side='Blue'"""):
        if r["gameid"] in seen: continue
        seen.add(r["gameid"])
        games_by_day[r["day"]].append({"gameid":r["gameid"],"team":r["team"],
                                        "win":int(r["result"] or 0)})
    win_days,releases=build_patch_calendar(con,last_labeled_patch)
    # Validacao do calendario: feed Riot capturado (game de 20/08 = patch 16.16)
    anchor_checks=[]
    for r in con.execute("""SELECT substr(updated_at,1,10) day,patch FROM riot_games_v10
                            WHERE patch IS NOT NULL AND patch!=''"""):
        try:
            riot_pm=parse_patch(float(".".join(str(r["patch"]).split(".")[:2])))
        except Exception:
            riot_pm=None
        cal=calendar_patch_for_day(releases,r["day"])
        anchor_checks.append({"day":r["day"],"riot_patch":patch_label(riot_pm) if riot_pm else str(r["patch"]),
                              "calendar_patch":patch_label(cal),"match":cal==riot_pm})

    elo=defaultdict(lambda:BASE_ELO)
    cy=None
    preds=[]
    for s in series:
        yr=int(s["year"])
        if cy is None: cy=yr
        elif yr!=cy:
            for t in list(elo.keys()):
                elo[t]=BASE_ELO+SEASON_DECAY*(elo[t]-BASE_ELO)
            cy=yr
        t1,t2,winner=s["team1"],s["team2"],s["winner"]
        p1=elo_prob(elo[t1],elo[t2])
        day=str(s["date"])[:10]
        patches=(patch_of.get(day) or {}).get(t1) or (patch_of.get(day) or {}).get(t2) or []
        if patches:
            pm=parse_patch(max(set(patches),key=patches.count));estimated=False
        else:
            pm=calendar_patch_for_day(releases,day);estimated=True
        preds.append({"day":day,"team1":t1,"team2":t2,"winner":winner,
                      "p_team1":p1,"patch":pm,"patch_estimated":estimated,
                      "wins1":s["wins1"],"wins2":s["wins2"]})
        y=1 if winner==t1 else 0
        delta=ELO_K*(y-p1)
        elo[t1]+=delta; elo[t2]-=delta

    def metrics(rows):
        n=len(rows)
        if not n: return None
        correct=0;brier=0.0;ll=0.0;conf=0.0
        for r in rows:
            y=1 if r["winner"]==r["team1"] else 0
            p=r["p_team1"]
            correct+=int((p>=.5)==bool(y))
            brier+=(p-y)**2
            ll-=y*math.log(max(p,1e-9))+(1-y)*math.log(max(1-p,1e-9))
            conf+=max(p,1-p)
        return {"series":n,"accuracy":round(correct/n,4),"brier":round(brier/n,4),
                "log_loss":round(ll/n,4),"avg_confidence":round(conf/n,4)}

    # Ultimos 4 patches reais (calendario) a partir do patch atual
    current=calendar_patch_for_day(releases,date.today().isoformat())
    last4=[(current[0],current[1]-i) for i in range(3,-1,-1)]
    by_patch=defaultdict(list)
    for p in preds:by_patch[p["patch"]].append(p)
    labeled_ordered=sorted(pm for pm in by_patch if pm in win_days)
    labeled_last4=labeled_ordered[-4:]

    out={"model":"Series Elo (K=64) - replica exata de recalc_ratings",
         "total_series":len(preds),
         "overall":metrics(preds),
         "patch_calendar":{
            "last_labeled_day":last_labeled_day,
            "anchor_patch":patch_label(last_labeled_patch),
            "releases":{patch_label(pm):rel.isoformat() for pm,rel in sorted(releases.items())
                        if pm[1]>=last_labeled_patch[1]-2},
            "anchor_checks":anchor_checks},
         "current_patch":patch_label(current),
         "last4_real_patches":[patch_label(pm) for pm in last4],
         "last4_real_per_patch":{patch_label(pm):metrics(by_patch.get(pm,[])) for pm in last4},
         "last4_real_combined":metrics([p for pm in last4 for p in by_patch.get(pm,[])]),
         "labeled_last4_patches":[patch_label(pm) for pm in labeled_last4],
         "labeled_last4_combined":metrics([p for pm in labeled_last4 for p in by_patch[pm]]),
         "labeled_per_patch":{patch_label(pm):metrics(by_patch[pm]) for pm in labeled_ordered}}

    # Nivel de game nos ultimos 4 patches rotulados (team_games)
    games=[]
    for p in preds:
        if p["patch"] not in labeled_last4 or p["patch_estimated"]: continue
        for g in games_by_day.get(p["day"],[]):
            if g["team"] not in (p["team1"],p["team2"]): continue
            pblue=p["p_team1"] if p["team1"]==g["team"] else 1-p["p_team1"]
            games.append({"p_blue":pblue,"win_blue":g["win"]})
    if games:
        n=len(games);correct=0;brier=0.0;ll=0.0
        for g in games:
            y=g["win_blue"];p=g["p_blue"]
            correct+=int((p>=.5)==bool(y))
            brier+=(p-y)**2
            ll-=y*math.log(max(p,1e-9))+(1-y)*math.log(max(1-p,1e-9))
        out["labeled_last4_game_level"]={"games":n,"accuracy":round(correct/n,4),
                                         "brier":round(brier/n,4),"log_loss":round(ll/n,4)}

    # Calibracao (serie inteira)
    buckets={"50-60":[0,0],"60-70":[0,0],"70-80":[0,0],"80-90":[0,0],"90+":[0,0]}
    for r in preds:
        y=1 if r["winner"]==r["team1"] else 0
        fav=max(r["p_team1"],1-r["p_team1"])
        win_fav=y if r["p_team1"]>=.5 else 1-y
        b=("90+" if fav>=.9 else "80-90" if fav>=.8 else "70-80" if fav>=.7
           else "60-70" if fav>=.6 else "50-60")
        buckets[b][0]+=1;buckets[b][1]+=win_fav
    out["calibration"]={k:{"n":v[0],"observed_winrate":round(v[1]/v[0],4) if v[0] else None}
                        for k,v in buckets.items()}

    out["series_detail"]=[{**{k:p[k] for k in ("day","team1","team2","winner","p_team1","patch_estimated")},
                           "patch":patch_label(p["patch"]) if p["patch"] else None,
                           "predicted_winner":p["team1"] if p["p_team1"]>=.5 else p["team2"],
                           "correct":(p["p_team1"]>=.5)==(p["winner"]==p["team1"])}
                          for p in preds]
    (ROOT/"BACKTEST_PATCH_ACCURACY_V28.json").write_text(
        json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    shown={k:v for k,v in out.items() if k!="series_detail"}
    print(json.dumps(shown,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
