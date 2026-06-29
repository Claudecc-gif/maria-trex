#!/usr/bin/env python3
# One-time restore: seed the current Season bucket (and each active profile's per-season best)
# with every active account's best run, so players who already played the season but were never
# recorded as a season run (profiles carried no timestamp) appear on the Season board.
# Reversible: backups/ holds pre-write snapshots.
#   python3 restore_season3_backfill.py --dry                 # preview the merged Season 3 board
#   python3 restore_season3_backfill.py                       # write all active profiles
#   python3 restore_season3_backfill.py --names "PREM,WES"    # write only these names
import json, sys, urllib.request, urllib.parse, time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

FB="https://kush-rush-864ed-default-rtdb.europe-west1.firebasedatabase.app"
CUR_SEASON=2                     # internal index for "Season 3"
AMS=ZoneInfo("Europe/Amsterdam")
WEEK=7*86400*1000
REF_END=int(datetime(2026,6,7,19,0,0,tzinfo=timezone.utc).timestamp()*1000)   # Sun 2026-06-07 21:00 CEST

def season_end_at(t_ms):
    dt=datetime.fromtimestamp(t_ms/1000, AMS)
    js_dow=(dt.weekday()+1)%7    # JS getDay(): Sun=0..Sat=6
    past=(dt.hour>21) or (dt.hour==21 and (dt.minute>0 or dt.second>0 or dt.microsecond>0))
    add=(7-js_dow)%7
    if add==0 and past: add=7
    target=dt.replace(hour=21,minute=0,second=0,microsecond=0)+timedelta(days=add)
    return int(target.timestamp()*1000)
def season_of(t_ms):
    t_ms=int(t_ms or 0)
    if not t_ms: return None
    return round((season_end_at(t_ms)-REF_END)/WEEK)
def entry_season(e):
    if isinstance(e.get("season"),(int,float)): return int(e["season"])
    return season_of(e.get("ts"))
def rank(e): return 0.66*(e.get("score") or 0)+0.33*(e.get("dist") or 0)+5*(e.get("hidden") or 0)

def get(path):
    with urllib.request.urlopen(f"{FB}/{path}.json", timeout=30) as r: return json.load(r)
def put(path, obj):
    req=urllib.request.Request(f"{FB}/{path}.json", data=json.dumps(obj).encode(), method="PUT", headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)

args=sys.argv[1:]
dry="--dry" in args
names_arg=None
if "--names" in args:
    i=args.index("--names")
    if i+1 < len(args): names_arg=args[i+1]

profiles=get("maria_trex_profiles").get("profiles",{})
only={n.strip().upper() for n in names_arg.split(",")} if names_arg else None
roster=[n for n in profiles if (only and n.upper() in only) or (not only and (profiles[n].get("best") or 0)>0)]
print("Active profiles:", list(profiles.keys()))
print("Roster to seed into Season 3:", roster)

now=int(time.time()*1000)
scores=get("maria_trex_scores")
seasons=scores.get("seasons")
if isinstance(seasons,list): cur=seasons[CUR_SEASON] if len(seasons)>CUR_SEASON and isinstance(seasons[CUR_SEASON],list) else []
else: cur=(seasons or {}).get(str(CUR_SEASON),[]) or []

best={}
def add(e):
    n=(e.get("name") or "").upper()[:10]
    if not n or not isinstance(e.get("score"),(int,float)): return
    if n not in best or rank(e)>rank(best[n]): best[n]=e
for e in cur: add(e)                                              # existing bucket
for e in scores.get("scores",[]):                                 # real runs already timestamped this season
    if entry_season(e)==CUR_SEASON: add(e)
for n in roster:                                                  # active accounts' best (the restore)
    pr=profiles[n]
    add({"name":n.upper()[:10],"cc":pr.get("cc",""),"score":int(pr.get("best") or 0),"dist":int(pr.get("bestDist") or 0),"hidden":0,"ts":now,"season":CUR_SEASON})

bucket=sorted(best.values(), key=rank, reverse=True)
print("\nMerged Season 3 board would be:")
for e in bucket: print(f"  {e['name']:<11} {round(rank(e)):>5} pts  (score {e['score']}, {e.get('dist',0)}m)")
if dry: print("\nDRY RUN — nothing written."); sys.exit(0)

put(f"maria_trex_scores/seasons/{CUR_SEASON}", bucket)
for n in roster:
    pr=profiles[n]; key=urllib.parse.quote(n, safe="")
    put(f"maria_trex_profiles/profiles/{key}/seasonBest/s{CUR_SEASON}",
        {"score":int(pr.get('best') or 0),"dist":int(pr.get('bestDist') or 0),"hidden":0,"ts":now})
back=get(f"maria_trex_scores/seasons/{CUR_SEASON}")
print("\nVERIFY — Season 3 bucket now:", [(e['name'],e['score']) for e in (back or [])])
