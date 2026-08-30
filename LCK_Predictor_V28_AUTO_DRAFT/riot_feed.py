
from __future__ import annotations
import json, os, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

PERSISTED="https://esports-api.lolesports.com/persisted/gw"
LIVE="https://feed.lolesports.com/livestats/v1"
PUBLIC_CLIENT_KEY="0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
FIRST_FRAME_BY_GAME_ID={}

def _get(url, params=None, with_key=True, timeout=12):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers={"User-Agent":"Mozilla/5.0 LCKPredictor/10","Accept":"application/json"}
    if with_key: headers["x-api-key"]=PUBLIC_CLIENT_KEY
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read()
        if r.status == 204 or not body:
            return None
        return json.loads(body.decode("utf-8","replace"))

def get_live(hl="en-US"):
    return _get(PERSISTED+"/getLive",{"hl":hl})

def get_schedule(hl="en-US", league_id=None, page_token=None):
    p={"hl":hl}
    if league_id:p["leagueId"]=league_id
    if page_token:p["pageToken"]=page_token
    return _get(PERSISTED+"/getSchedule",p)

def get_event_details(event_id,hl="en-US"):
    return _get(PERSISTED+"/getEventDetails",{"hl":hl,"id":str(event_id)})

def feed_time(delay_seconds=60):
    now=datetime.now(timezone.utc).replace(microsecond=0)
    now=now.replace(second=now.second-now.second%10)-timedelta(seconds=delay_seconds)
    return now.isoformat().replace("+00:00","Z")

def get_window(game_id, starting_time=None):
    p={}
    if starting_time:p["startingTime"]=starting_time
    return _get(f"{LIVE}/window/{game_id}",p,with_key=False)

def get_details(game_id, starting_time=None, participant_ids=None):
    p={}
    if starting_time:p["startingTime"]=starting_time
    if participant_ids:p["participantIds"]="_".join(map(str,participant_ids))
    return _get(f"{LIVE}/details/{game_id}",p,with_key=False)

def events_from(payload):
    try:return payload["data"]["schedule"]["events"] or []
    except:return []

def event_from_details(payload):
    try:return payload["data"]["event"]
    except:return None

def is_lck_event(ev):
    league=ev.get("league") or {}
    text=" ".join(str(x or "") for x in [league.get("name"),league.get("slug")]).lower()
    return "lck" in text and "challenger" not in text and "cl" not in text.split()

def current_game(event):
    match=(event or {}).get("match") or {}
    games=match.get("games") or []
    for g in games:
        if str(g.get("state","")).lower() in {"inprogress","in_progress","in progress"}:
            return g
    for g in games:
        if str(g.get("state","")).lower() not in {"completed","unneeded"}:
            return g
    return games[-1] if games else None

def _count_objective(v):
    if isinstance(v,list): return len(v)
    try:return int(v or 0)
    except:return 0

def _latest(payload):
    f=(payload or {}).get("frames") or []
    return f[-1] if f else {}

def _team_frame(frame, side):
    d=(frame or {}).get(side+"Team") or {}
    return {
      "gold":int(d.get("totalGold") or 0),
      "kills":int(d.get("totalKills") or d.get("kills") or 0),
      "towers":int(d.get("towers") or 0),
      "dragons":_count_objective(d.get("dragons")),
      "barons":int(d.get("barons") or 0),
      "inhibitors":int(d.get("inhibitors") or 0),
      "participants":d.get("participants") or [],
    }

def _meta_team(meta,side):
    return (meta or {}).get(side+"TeamMetadata") or {}

def _resolve_side_teams(event, sides):
    if not event: return
    """O feed de livestats normalmente não traz teamName, deixando o lado azul/
    vermelho sem identificação. Os nomes de jogador vêm prefixados com o código
    do time ('BRO GIDEON'), então casamos esse prefixo com os times do evento.
    Fallback: ordem dos times no evento."""
    teams=(event.get("match") or {}).get("teams") or []
    opts=[]
    for t in teams:
        cd=(t.get("code") or "").strip()
        nm=(t.get("name") or "").strip()
        if cd or nm: opts.append({"code":cd,"name":nm or cd})
    if not opts: return
    for s in sides:
        if s.get("team"): continue
        prefixes={str(p.get("player") or "").split(" ")[0].strip().upper()
                  for p in (s.get("participants") or []) if p.get("player")}
        prefixes.discard("")
        hit=next((o for o in opts if o["code"] and o["code"].upper() in prefixes),None)
        if hit: s["team"]=hit["name"] or hit["code"]
    used={s.get("team") for s in sides if s.get("team")}
    left=[o for o in opts if (o["name"] or o["code"]) not in used]
    for s in sides:
        if not s.get("team") and left:
            o=left.pop(0); s["team"]=o["name"] or o["code"]

def normalize(event_id,event,window,details,game_override=None):
    game=game_override or current_game(event)
    if not game: raise RuntimeError("Evento sem game disponível")
    # O window pode vir vazio/None nos primeiros segundos de um mapa novo. Isso
    # é estado normal, não erro de programação: sinalizamos com uma mensagem
    # clara para o chamador manter o último snapshot bom.
    if not (window or {}).get("frames"):
        raise RuntimeError("Feed do mapa ainda não publicou frames")
    meta=(window or {}).get("gameMetadata") or {}
    wf=_latest(window); df=_latest(details)
    blue=_team_frame(wf,"blue"); red=_team_frame(wf,"red")
    # Details normally has a flat participant array; index by participantId.
    detail_parts={}
    for p in (df.get("participants") or []):
        if p.get("participantId") is not None: detail_parts[int(p["participantId"])]=p
    teams=[]
    for side,teamframe in [("blue",blue),("red",red)]:
        tm=_meta_team(meta,side); pm=tm.get("participantMetadata") or []
        team_name=tm.get("teamName") or tm.get("name")
        participants=[]
        for i,m in enumerate(pm):
            pid=int(m.get("participantId") or (i+1 if side=="blue" else i+6))
            w=next((x for x in teamframe["participants"] if int(x.get("participantId") or -1)==pid),None)
            if w is None and i<len(teamframe["participants"]): w=teamframe["participants"][i]
            w=w or {}; d=detail_parts.get(pid,{})
            participants.append({
              "participant_id":pid,
              "player":m.get("summonerName") or m.get("playerName") or m.get("name"),
              "champion_key":m.get("championId"),
              "champion":m.get("championName") or m.get("championId"),
              "role":m.get("role"),
              "level":int(w.get("level") or d.get("level") or 0),
              "kills":int(w.get("kills") or 0),"deaths":int(w.get("deaths") or 0),
              "assists":int(w.get("assists") or 0),
              "cs":int(w.get("creepScore") or w.get("cs") or 0),
              "gold":int(w.get("totalGold") or 0),
              "current_health":int(d.get("currentHealth") or 0),
              "max_health":int(d.get("maxHealth") or 0),
              "items":d.get("items") or [],
              "runes":d.get("runes") or [],
            })
        teams.append({"side":side,"team":team_name,**{k:v for k,v in teamframe.items() if k!="participants"},
                      "participants":participants})
    _resolve_side_teams(event,teams)
    game_time=wf.get("gameTime") or wf.get("gameTimeSeconds")
    if isinstance(game_time,str) and ":" in game_time:
        try:
            a,b=game_time.split(":")[-2:]; game_time=float(a)*60+float(b)
        except:game_time=None
    return {
      "event_id":str(event_id),"game_id":str(game.get("id")),"game_number":int(game.get("number") or 1),
      "game_state":game.get("state"),"event_state":event.get("state"),
      "patch":meta.get("patchVersion"),"timestamp":wf.get("rfc460Timestamp"),
      "game_time_seconds":game_time,
      "blue":teams[0],"red":teams[1],
      "streams":event.get("streams") or [],
      "series":{"teams":(event.get("match") or {}).get("teams") or [],
                "games":(event.get("match") or {}).get("games") or [],
                "strategy":(event.get("match") or {}).get("strategy")},
      "source":"Riot LoL Esports web feeds"
    }


def fetch_draft_probe(event_id, delays=(0,10,30,60)):
    """Capture champion metadata without requiring the full live Details feed."""
    ep=get_event_details(event_id)
    event=event_from_details(ep)
    if not event: raise RuntimeError("EventDetails não retornou evento")
    game=current_game(event)
    if not game or not game.get("id"): raise RuntimeError("Game ID indisponível")

    best=None;last_error=None
    for delay in delays:
        try:
            w=get_window(game["id"],feed_time(int(delay)))
            meta=(w or {}).get("gameMetadata") or {}
            sides=[]
            for side in ("blue","red"):
                tm=meta.get(side+"TeamMetadata") or {}
                pm=tm.get("participantMetadata") or []
                picks=[]
                for i,m in enumerate(pm):
                    picks.append({
                      "participant_id":m.get("participantId"),
                      "player":m.get("summonerName") or m.get("playerName") or m.get("name"),
                      "champion":m.get("championName") or m.get("championId"),
                      "champion_id":m.get("championId"),
                      "role":m.get("role"),
                      "index":i
                    })
                sides.append({"side":side,"team":tm.get("teamName") or tm.get("name"),
                              "picks":picks,"participants":picks})
            _resolve_side_teams(event,sides)
            for sd in sides: sd.pop("participants",None)
            locked=sum(1 for sd in sides for p in sd["picks"] if p.get("champion"))
            out={
              "event_id":str(event_id),"game_id":str(game["id"]),
              "game_number":int(game.get("number") or 1),
              "game_state":game.get("state"),"event_state":event.get("state"),
              "patch":meta.get("patchVersion"),
              "blue":sides[0],"red":sides[1],
              "locked_count":locked,"complete":locked>=10,
              "delay_seconds":int(delay),
              "source":"Riot LoL Esports Window gameMetadata"
            }
            if best is None or locked>best["locked_count"]:best=out
            if locked>=10:return out
        except Exception as e:
            last_error=e
    if best is not None:return best
    raise RuntimeError(f"Draft metadata indisponível: {type(last_error).__name__}: {last_error}")

def fetch_event_live(event_id,delay_seconds=60):
    ep=get_event_details(event_id)
    event=event_from_details(ep)
    if not event: raise RuntimeError("EventDetails não retornou evento")
    game=current_game(event)
    if not game or not game.get("id"): raise RuntimeError("Game ID indisponível")
    t=feed_time(delay_seconds)
    w=get_window(game["id"],t)
    d=get_details(game["id"],t)
    return normalize(event_id,event,w,d,game)

def locate_completed_game(game_id, around_iso, span_hours=10, step_minutes=10):
    """Descobre o instante do último frame de um mapa já encerrado.

    A window API só responde para um startingTime dentro da janela em que o
    jogo foi transmitido; para um mapa antigo, 'agora' devolve HTTP 400. Varre o
    dia a passos largos e devolve o timestamp do frame final — é o que permite
    recuperar draft e resultado de partidas passadas."""
    base=_parse_iso(around_iso)
    if not base: return None
    base=base.astimezone(timezone.utc).replace(tzinfo=timezone.utc)-timedelta(minutes=10)
    last=None; seen=False
    t=base; end=base+timedelta(hours=span_hours)
    while t<end:
        try:
            w=get_window(game_id,t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception:
            t+=timedelta(minutes=step_minutes); continue
        frames=(w or {}).get("frames") or []
        if frames:
            seen=True
            for f in frames:
                ts=f.get("rfc460Timestamp")
                if ts and (last is None or ts>last): last=ts
        elif seen:
            break
        t+=timedelta(minutes=step_minutes)
    if not last: return None
    # A window API exige startingTime alinhado em 10 s e sem milissegundos; o
    # rfc460Timestamp do frame traz ambos e seria recusado com HTTP 400.
    dt=_parse_iso(last)
    if not dt: return None
    dt=dt.astimezone(timezone.utc).replace(microsecond=0)
    dt=dt-timedelta(seconds=dt.second%10)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_game_snapshot(event_id,game_id,delay_seconds=0,starting_time=None):
    """Fetch one specific game, including a completed map from a prior series.

    `starting_time` (ISO Z) fixa o instante consultado; sem ele a janela é
    'agora menos delay', que só funciona enquanto o mapa está no ar."""
    ep=get_event_details(event_id)
    event=event_from_details(ep)
    if not event: raise RuntimeError("EventDetails não retornou evento")
    games=((event.get("match") or {}).get("games") or [])
    game=next((g for g in games if str(g.get("id"))==str(game_id)),None)
    if not game: raise RuntimeError("Game ID não pertence ao evento")
    t=starting_time or feed_time(delay_seconds)
    w=get_window(game_id,t)
    d=get_details(game_id,t)
    return normalize(event_id,event,w,d,game)

def ddragon_patch(full_patch):
    if not full_patch:return None
    parts=str(full_patch).split(".")
    return ".".join(parts[:2])+".1" if len(parts)>=2 else str(full_patch)

def champion_image(champion,full_patch):
    p=ddragon_patch(full_patch)
    if not p or not champion:return None
    safe=str(champion).replace(" ","")
    aliases={"Wukong":"MonkeyKing","RenataGlasc":"Renata"}
    safe=aliases.get(safe,safe)
    return f"https://ddragon.leagueoflegends.com/cdn/{p}/img/champion/{safe}.png"

def item_image(item_id,full_patch):
    p=ddragon_patch(full_patch)
    return f"https://ddragon.leagueoflegends.com/cdn/{p}/img/item/{item_id}.png" if p and item_id else None


# ---------------------------------------------------------------------------
# Live-game discovery + live-draft capture (single client module)
# ---------------------------------------------------------------------------
COVERED_LEAGUE_IDS = [
    "98767991310872058",   # LCK
    "98767991314006698",   # LPL
    "98767991332355509",   # CBLOL
]

ROLE_ORDER = ["top", "jng", "mid", "bot", "sup"]


class DraftNotReady(Exception):
    pass


def _parse_iso(x):
    if not x:
        return None
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None


def _window_team_ids(window):
    meta = (window or {}).get("gameMetadata") or {}
    out = {}
    for side in ("blue", "red"):
        tm = meta.get(side + "TeamMetadata") or {}
        out[side] = tm.get("esportsTeamId")
    return out


def _window_is_live(window, game_id=None):
    """A game is truly live if the latest frame is in_game with any gold on board,
    or the first frame opened less than 15 minutes ago (champ select / loading)."""
    frames = (window or {}).get("frames") or []
    meta = (window or {}).get("gameMetadata") or {}
    if not frames:
        return False
    first_ts = _parse_iso(frames[0].get("rfc460Timestamp"))
    if game_id and first_ts is not None:
        FIRST_FRAME_BY_GAME_ID.setdefault(str(game_id), first_ts)
    last = frames[-1]
    gs = str(last.get("gameState") or "").lower()
    gold = int((last.get("blueTeam") or {}).get("totalGold") or 0) + int(
        (last.get("redTeam") or {}).get("totalGold") or 0)
    if gs == "in_game" and gold > 0:
        return True
    first_ts = FIRST_FRAME_BY_GAME_ID.get(str(game_id)) if game_id else first_ts
    if first_ts is not None:
        age = (datetime.now(timezone.utc) - first_ts).total_seconds()
        if 0 <= age < 15 * 60:
            return True
    return False


def discover_live_games(league_ids=None, window_hours=8):
    """Robust live game discovery: getLive plus a ±window_hours schedule scan,
    verified against the window feed. Teams are oriented by the esportsTeamId in
    gameMetadata (blue/red) matched back to getEventDetails teams. Returns a list
    of {gameId,eventId,gameNum,league,blueTeam,redTeam,blueCode,redCode}."""
    ids = league_ids or COVERED_LEAGUE_IDS
    candidates = {}
    try:
        for e in events_from(get_live("en-US")):
            mid = e.get("id") or ((e.get("match") or {}).get("id"))
            if mid:
                candidates.setdefault(str(mid), {"league": (e.get("league") or {}).get("name")})
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    for lid in ids:
        try:
            for e in events_from(get_schedule("en-US", league_id=lid)):
                if (e.get("type") or "") != "match":
                    continue
                mt = e.get("match") or {}
                teams = mt.get("teams") or []
                if any("tbd" in ((t.get("name") or "") + " " + (t.get("code") or "")).lower() for t in teams):
                    continue
                t = _parse_iso(e.get("startTime"))
                if t is None or abs((now - t).total_seconds()) > window_hours * 3600:
                    continue
                mid = e.get("id") or mt.get("id")
                if mid:
                    candidates.setdefault(str(mid), {"league": (e.get("league") or {}).get("name")})
        except Exception:
            pass

    out = []
    for mid, info in candidates.items():
        try:
            ep = get_event_details(mid)
            ev = event_from_details(ep)
            if not ev:
                continue
            match = ev.get("match") or {}
            teams_by_id = {str(t.get("id")): t for t in (match.get("teams") or [])}
            games = match.get("games") or []
            for g in sorted(games, key=lambda x: int(x.get("number") or 0), reverse=True):
                gid = g.get("id")
                if not gid:
                    continue
                w = get_window(str(gid))
                if not _window_is_live(w, gid):
                    continue
                side_ids = _window_team_ids(w)
                blue = teams_by_id.get(str(side_ids.get("blue")))
                red = teams_by_id.get(str(side_ids.get("red")))
                out.append({
                    "gameId": str(gid),
                    "eventId": str(mid),
                    "gameNum": int(g.get("number") or 1),
                    "league": (ev.get("league") or {}).get("name") or info.get("league"),
                    "blueTeam": (blue or {}).get("name"),
                    "redTeam": (red or {}).get("name"),
                    "blueCode": (blue or {}).get("code"),
                    "redCode": (red or {}).get("code"),
                })
                break
        except Exception:
            continue
    return out


def _norm_role(role, idx):
    r = str(role or "").lower()
    if r in ("jungle", "jg"):
        return "jng"
    if r in ("adc", "bottom"):
        return "bot"
    if r in ("support", "utility"):
        return "sup"
    if r in ("middle", "midlane"):
        return "mid"
    if r == "top":
        return "top"
    return ROLE_ORDER[idx] if idx < len(ROLE_ORDER) else None


def fetch_live_draft(game_id):
    """Return the draft captured from the window gameMetadata, ordered top→support
    for each side: {blue:[{champion,player,role}], red:[...]}. Raises DraftNotReady
    when the feed has not published champion metadata yet."""
    try:
        w = get_window(str(game_id))
    except Exception as e:
        raise DraftNotReady(f"window indisponível: {type(e).__name__}")
    meta = (w or {}).get("gameMetadata") or {}
    sides = {}
    for side in ("blue", "red"):
        tm = meta.get(side + "TeamMetadata") or {}
        picks = []
        for i, m in enumerate(tm.get("participantMetadata") or []):
            champ = m.get("championId") or m.get("championName")
            if not champ:
                continue
            picks.append({
                "champion": champ,
                "champion_id": m.get("championId"),
                "player": m.get("summonerName") or m.get("playerName") or m.get("name"),
                "role": _norm_role(m.get("role"), i),
                "participant_id": m.get("participantId"),
                "esports_player_id": m.get("esportsPlayerId"),
            })
        picks.sort(key=lambda p: ROLE_ORDER.index(p["role"]) if p["role"] in ROLE_ORDER else 99)
        sides[side] = picks
    if not any(sides.get(s) for s in ("blue", "red")):
        raise DraftNotReady("gameMetadata sem champion metadata")
    return {
        "gameId": str(game_id),
        "patch": meta.get("patchVersion"),
        "blue": sides["blue"],
        "red": sides["red"],
        "team_codes": {
            side: ((meta.get(side + "TeamMetadata") or {}).get("teamCode")
                   or (meta.get(side + "TeamMetadata") or {}).get("code"))
            for side in ("blue", "red")
        },
    }


# ---------------------------------------------------------------------------
# V28.1 — Near-real-time capture
# ---------------------------------------------------------------------------
# Findings from controlled probes (see REVIEW_V28_1_REALTIME.md):
#  - The public gateway has NO dedicated real-time draft endpoint (fake-op
#    control returned the same 400 as candidate names; OpenAPI catalog confirms
#    only window/details are live). Drafts surface only via window gameMetadata
#    after picks lock — true real-time draft requires an official partner (GRID).
#  - SEM startingTime a resposta começa do INÍCIO do jogo (janela retida), NÃO
#    do frame mais fresco — validado contra a API real. Por isso o consumo em
#    tempo real deve usar always startingTime explícito.
#  - fetch_event_live(delay_seconds=60) já retorna o frame mais fresco: o "60"
#    é janela de lookback (garante frames existentes), não latência adicional.
#  - O feed live é efêmero; paginação incremental por cursor (startingTime =
#    último rfc460Timestamp) consome sem duplicatas durante a partida.

def fetch_event_live_incremental(event_id, cursor_state, lookback_seconds=90):
    """Snapshot mais fresco via paginação incremental com cursor.

    Sempre usa startingTime (primeira chamada semeia com lookback curto; as
    seguintes pedem só frames novos desde o cursor). O último frame retornado
    é o mais fresco publicado pela Riot — mesma frescura do caminho legado,
    sem re-buscar a janela de 60s a cada poll.
    """
    ep = get_event_details(event_id)
    event = event_from_details(ep)
    if not event:
        raise RuntimeError("EventDetails não retornou evento")
    game = current_game(event)
    if not game or not game.get("id"):
        raise RuntimeError("Game ID indisponível")
    w, d, _frames = fetch_incremental(game["id"], cursor_state, lookback_seconds)
    return normalize(event_id, event, w, d, game)


class RealtimeCursor:
    """Cursor de paginação incremental por game_id (startingTime)."""

    def __init__(self):
        self._last = {}

    def get(self, game_id):
        return self._last.get(str(game_id))

    def advance(self, game_id, frames):
        ts = None
        for f in frames or []:
            t = f.get("rfc460Timestamp")
            if t and (ts is None or t > ts):
                ts = t
        if ts:
            self._last[str(game_id)] = ts
        return ts

    def reset(self, game_id=None):
        if game_id is None:
            self._last.clear()
        else:
            self._last.pop(str(game_id), None)


def fetch_incremental(game_id, cursor_state, lookback_seconds=90):
    """Novos frames Window/Details desde o último cursor.

    Sem cursor ainda, semeia com um lookback curto. Se o cursor ficar fora da
    janela retida (HTTP 400), re-semeia com lookback fresco — nunca consulta
    sem startingTime (que retorna o início do jogo, não o estado atual).
    Retorna (window, details, frames_novos).
    """
    gid = str(game_id)
    start = cursor_state.get(gid) if cursor_state else None
    if not start:
        start = feed_time(int(lookback_seconds))
    w = d = None
    try:
        w = get_window(gid, start)
        d = get_details(gid, start)
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) == 400:
            fresh = feed_time(int(lookback_seconds))
            w = get_window(gid, fresh)
            d = get_details(gid, fresh)
        else:
            raise
    frames = (w or {}).get("frames") or []
    if cursor_state is not None:
        cursor_state.advance(gid, frames)
    return w, d, frames

