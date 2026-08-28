# -*- coding: utf-8 -*-

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_os.path.dirname(_HERE))   # raiz do app (LCK_Predictor_V28_AUTO_DRAFT)
DB = _os.path.join(_ROOT, "data", "lck_data_v1.sqlite")
# Pasta com os CSVs do Oracle's Elixir. Ajuste com a variavel de ambiente OE_DIR
# ou coloque os CSVs em data/oracles_elixir/
OE_DIR = _os.environ.get("OE_DIR") or _os.path.join(_ROOT, "data", "oracles_elixir")

import sqlite3, math, itertools, json, os

# DB definido no header portatil acima
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

def logit(p):
    p = min(max(p, 1e-6), 1-1e-6)
    return math.log(p/(1-p))
def sig(x):
    return 1/(1+math.exp(-x))

# GAME 2: lados invertidos
BLUE = [("Kingen","Ambessa","top"),("Sponge","Nocturne","jng"),("Scout","Locke","mid"),
        ("Diable","Yunara","bot"),("Lehends","Lulu","sup")]
RED  = [("Clear","Rumble","top"),("Raptor","Vi","jng"),("VicLa","Ahri","mid"),
        ("Taeyoon","Ezreal","bot"),("Kellin","Karma","sup")]
BLUE_TEAM, RED_TEAM = "NS", "BFX"

rows = con.execute("""SELECT gameid, side, playername, champion, result, year
                      FROM player_games WHERE league='LCK' AND result IS NOT NULL""").fetchall()

games = {}
for r in rows:
    games.setdefault((r["gameid"], r["side"]), []).append(r)

def wr(sel):
    n = len(sel); w = sum(x["result"] for x in sel)
    return n, w, (w/n if n else None)

by_player, by_player_champ, by_player_champ_side = {}, {}, {}
for r in rows:
    by_player.setdefault(r["playername"], []).append(r)
    by_player_champ.setdefault((r["playername"], r["champion"]), []).append(r)
    by_player_champ_side.setdefault((r["playername"], r["champion"], r["side"]), []).append(r)

blue_recent = [r for r in rows if r["side"]=="Blue" and r["year"]>=2025]
nb2, wb2, blue_wr_recent = wr(blue_recent)

elo_b = con.execute("SELECT elo FROM current_ratings WHERE team=?",(BLUE_TEAM,)).fetchone()["elo"]
elo_r = con.execute("SELECT elo FROM current_ratings WHERE team=?",(RED_TEAM,)).fetchone()["elo"]
p_elo_blue = 1/(1+10**((elo_r-elo_b)/400))

K_BASE, K_CHAMP, K_SIDE, K_SYN = 20, 8, 6, 6

def player_baseline(p, year_min=None):
    sel = by_player.get(p, [])
    if year_min: sel = [x for x in sel if x["year"]>=year_min]
    n, w, _ = wr(sel)
    return n, (w + K_BASE*0.5)/(n + K_BASE)

def champ_stat(p, c, year_min=None):
    sel = by_player_champ.get((p,c), [])
    if year_min: sel = [x for x in sel if x["year"]>=year_min]
    n, w, raw = wr(sel)
    _, base = player_baseline(p, year_min)
    return n, w, raw, base, (w + K_CHAMP*base)/(n + K_CHAMP)

def side_stat(p, c, side, year_min=None):
    sel = by_player_champ_side.get((p,c,side), [])
    if year_min: sel = [x for x in sel if x["year"]>=year_min]
    n, w, raw = wr(sel)
    _,_,_,_, cs = champ_stat(p, c, year_min)
    return n, w, raw, (w + K_SIDE*cs)/(n + K_SIDE)

teamsets = {k: {"pc": {(x["playername"], x["champion"]) for x in lst},
                "ch": {x["champion"] for x in lst},
                "res": lst[0]["result"], "year": lst[0]["year"]}
            for k, lst in games.items()}

def pair_players(p1,c1,p2,c2, year_min=None):
    n=w=0
    for v in teamsets.values():
        if year_min and v["year"]<year_min: continue
        if (p1,c1) in v["pc"] and (p2,c2) in v["pc"]: n+=1; w+=v["res"]
    return n,w

def pair_champs(c1,c2, year_min=None):
    n=w=0
    for v in teamsets.values():
        if year_min and v["year"]<year_min: continue
        if c1 in v["ch"] and c2 in v["ch"]: n+=1; w+=v["res"]
    return n,w

def analyze(roster, side, teamname, year_min=None):
    res = {"players":[], "pairs":[], "team":teamname, "side":side}
    deltas=[]; side_deltas=[]
    for p,c,role in roster:
        n,w,raw,base,shrunk = champ_stat(p,c,year_min)
        ns,ws,raws,shrunk_s = side_stat(p,c,side,year_min)
        d = logit(shrunk)-logit(base); ds = logit(shrunk_s)-logit(shrunk)
        deltas.append(d); side_deltas.append(ds)
        res["players"].append(dict(player=p,champ=c,role=role,n=n,wins=w,raw=raw,
                                   baseline=base,shrunk=shrunk,delta=d,
                                   n_side=ns,raw_side=raws,delta_side=ds))
    res["fit_mean_delta"]=sum(deltas)/len(deltas)
    res["side_mean_delta"]=sum(side_deltas)/len(side_deltas)
    lifts=[]
    for (p1,c1,_),(p2,c2,_) in itertools.combinations(roster,2):
        n_pp,w_pp = pair_players(p1,c1,p2,c2,year_min)
        n_cc,w_cc = pair_champs(c1,c2,year_min)
        _,_,_,_,s1 = champ_stat(p1,c1,year_min); _,_,_,_,s2 = champ_stat(p2,c2,year_min)
        expected = sig((logit(s1)+logit(s2))/2)
        cc_shrunk = (w_cc + 10*0.5)/(n_cc + 10) if n_cc else 0.5
        prior = sig(logit(expected)+logit(cc_shrunk)-logit(0.5))
        pp_shrunk = (w_pp + K_SYN*prior)/(n_pp + K_SYN)
        lift = logit(pp_shrunk)-logit(expected)
        lifts.append(lift)
        res["pairs"].append(dict(a=f"{p1} {c1}", b=f"{p2} {c2}", n_pp=n_pp, w_pp=w_pp,
                                 wr_pp=(w_pp/n_pp if n_pp else None), n_cc=n_cc,
                                 wr_cc=(w_cc/n_cc if n_cc else None), lift=lift))
    res["syn_mean_lift"]=sum(lifts)/len(lifts)
    return res

OUT={}
for ymin,label in [(None,"career"),(2025,"since2025")]:
    OUT[label]={"blue":analyze(BLUE,"Blue",BLUE_TEAM,ymin),
                "red":analyze(RED,"Red",RED_TEAM,ymin)}

L_ELO = logit(p_elo_blue)
L_SIDE_GLOBAL = logit(blue_wr_recent)

for label in ("since2025","career"):
    b,r = OUT[label]["blue"], OUT[label]["red"]
    print("="*74); print(f"GAME 2  ESCOPO {label}  (perspectiva NS/azul)"); print("="*74)
    for sd,t in (("NS(azul)",b),("BFX(verm)",r)):
        print(f"\n-- {t['team']} ({t['side']}) --")
        for p in t["players"]:
            raw = f"{p['raw']:.3f}" if p['raw'] is not None else "  -  "
            print(f"  {p['player']:9s} {p['champ']:9s} N={p['n']:3d} raw={raw:>6s} base={p['baseline']:.3f} shrunk={p['shrunk']:.3f} d={p['delta']:+.3f} | Nside={p['n_side']:2d} dSide={p['delta_side']:+.3f}")
        print(f"  fit={t['fit_mean_delta']:+.4f} side={t['side_mean_delta']:+.4f} syn={t['syn_mean_lift']:+.4f}")
    fit = b["fit_mean_delta"]-r["fit_mean_delta"]
    sided = b["side_mean_delta"]-r["side_mean_delta"]
    syn = b["syn_mean_lift"]-r["syn_mean_lift"]
    print(f"\n  diffs NS-BFX: fit={fit:+.4f} side={sided:+.4f} syn={syn:+.4f}")
    print(f"  {'escala':>7s} | {'1)Elo':>8s} {'2)+fit':>8s} {'3)+side':>8s} {'4)+syn':>8s}   (prob NS)")
    for S in (1.0,2.5):
        p1=sig(L_ELO); p2=sig(L_ELO+S*fit)
        p3=sig(L_ELO+S*fit+L_SIDE_GLOBAL+S*sided)
        p4=sig(L_ELO+S*fit+L_SIDE_GLOBAL+S*sided+S*syn)
        print(f"  {S:6.1f}x | {p1*100:7.1f}% {p2*100:7.1f}% {p3*100:7.1f}% {p4*100:7.1f}%")
    print()

print("\nPARES com co-ocorrencia (since2025):")
for sd in ("blue","red"):
    t=OUT["since2025"][sd]; print(f"-- {t['team']} --")
    for pr in sorted(t["pairs"],key=lambda x:-x["n_pp"])[:6]:
        w=f"{pr['wr_pp']:.2f}" if pr['wr_pp'] is not None else " - "
        wc=f"{pr['wr_cc']:.2f}" if pr['wr_cc'] is not None else " - "
        print(f"   {pr['a']:18s}+{pr['b']:18s} Npp={pr['n_pp']:2d} wr={w} | Ncc={pr['n_cc']:3d} wr={wc} lift={pr['lift']:+.3f}")
