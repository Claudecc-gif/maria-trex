#!/usr/bin/env python3
"""KushRush leaderboard guardian — auto-heals a clobbered board AND keeps a fresh
high-water-mark backup of BOTH stores (profiles + scores) every few minutes.

Background: the Firebase nodes `maria_trex_profiles` (every player's account) and
`maria_trex_scores` (all-time list + per-week season buckets) feed the leaderboards.
A buggy/old PWA client could read a stale/partial copy and PUT the WHOLE node back,
wiping other players (happened 2026-06-29 19:18 — it erased PREM's Season-5 run, which
the once-a-day backup never captured). This watchdog runs every 10 min and:

  PROFILES  – per-child heal: any KNOWN name now missing from live is re-added with a
              per-child PUT (siblings never touched; a player's progress never reverted).
  SCORES    – union snapshot every cycle (frequent backup, never loses a run) + heal:
              if the all-time list or any season bucket SHRANK below the snapshot, the
              missing best-per-name runs are merged back (superset-guarded whole-node
              write, re-read just before writing to shrink the race window).

It NEVER deletes and NEVER lowers a score — it only restores what vanished and absorbs
new highs into the snapshot, so it can't fight a player's real updates.
"""
import json, os, sys, time, urllib.request
from urllib.parse import quote

FB        = "https://kush-rush-864ed-default-rtdb.europe-west1.firebasedatabase.app"
HOME      = os.path.expanduser("~/maria-trex-game")
PROF_HWM  = os.path.join(HOME, "backups", "profiles_hwm.json")
SCORE_HWM = os.path.join(HOME, "backups", "scores_hwm.json")
LOG       = os.path.join(HOME, "backups", "guardian.log")
BOARD_MAX = 100

def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "  " + msg
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f: f.write(line + "\n")
    print(line)

def get(url):
    with urllib.request.urlopen(url, timeout=20) as r: return json.load(r)

def put(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r: return r.status

def rank(e):
    if not isinstance(e, dict): return -1
    return 0.66*(float(e.get("score") or 0)) + 0.33*(float(e.get("dist") or 0)) + 5*(float(e.get("hidden") or 0))

# ---------------------------------------------------------------- profiles ----
def merge_season_best(a, b):
    a = a if isinstance(a, dict) else {}; b = b if isinstance(b, dict) else {}
    out = {}
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        e = x if rank(x) >= rank(y) else y
        if isinstance(e, dict) and isinstance(e.get("score"), (int, float)): out[k] = e
    return out

def merge_profile(base, other):
    if not isinstance(base, dict): return dict(other) if isinstance(other, dict) else {}
    if not isinstance(other, dict): return dict(base)
    m = dict(base)
    for fld in ("best", "bestDist", "passXP", "passTier", "bank"):
        m[fld] = max(int(base.get(fld) or 0), int(other.get(fld) or 0))
    owned = list(dict.fromkeys(["classic"] + list(base.get("owned") or []) + list(other.get("owned") or [])))
    m["owned"] = owned
    for cand in (other.get("skin"), base.get("skin")):
        if cand and cand in owned: m["skin"] = cand; break
    else: m["skin"] = owned[-1] if owned else "classic"
    m["cc"]  = (other.get("cc") or base.get("cc") or "")
    m["pet"] = bool(base.get("pet")) or bool(other.get("pet"))
    lt = max(int(base.get("lastTs") or 0), int(base.get("ts") or 0),
             int(other.get("lastTs") or 0), int(other.get("ts") or 0))
    m["lastTs"] = lt; m["ts"] = lt
    m["seasonBest"] = merge_season_best(base.get("seasonBest"), other.get("seasonBest"))
    return m

def guard_profiles():
    try:
        live = get(f"{FB}/maria_trex_profiles.json")
    except Exception as e:
        log(f"profiles SKIP — read failed: {e}"); return
    live_p = (live or {}).get("profiles", {}) if isinstance(live, dict) else {}
    if not isinstance(live_p, dict): log("profiles SKIP — not an object"); return

    snap_p = {}
    if os.path.exists(PROF_HWM):
        try: snap_p = (json.load(open(PROF_HWM)) or {}).get("profiles", {}) or {}
        except Exception: snap_p = {}

    if not snap_p:
        json.dump({"profiles": {k: merge_profile({}, v) for k, v in live_p.items()}},
                  open(PROF_HWM, "w"), indent=2)
        log(f"profiles seeded snapshot ({len(live_p)} profiles)"); return

    missing = [n for n in snap_p if n not in live_p]
    if missing:
        log(f"⚠ PROFILES DROP — live {len(live_p)}, snapshot {len(snap_p)}; missing {sorted(missing)}")
        healed = []
        for n in missing:
            try: put(f"{FB}/maria_trex_profiles/profiles/{quote(n, safe='')}.json", snap_p[n]); healed.append(n)
            except Exception as e: log(f"   profile heal FAILED {n}: {e}")
        log(f"✅ profiles healed {len(healed)}/{len(missing)}: {sorted(healed)}")

    new_snap = {n: merge_profile(snap_p.get(n), live_p.get(n)) for n in set(snap_p) | set(live_p)}
    json.dump({"profiles": new_snap}, open(PROF_HWM, "w"), indent=2)

# ------------------------------------------------------------------ scores ----
def normalize(arr):
    """best-per-name by rank, sorted, capped — mirrors the game's Board.normalize."""
    best = {}
    for e in arr or []:
        if not isinstance(e, dict) or not isinstance(e.get("score"), (int, float)): continue
        nm = str(e.get("name", "???")).upper()[:10] or "???"
        ent = {"name": nm, "score": max(0, int(e["score"])), "dist": max(0, int(e.get("dist") or 0)),
               "hidden": max(0, int(e.get("hidden") or 0)), "ts": int(e.get("ts") or 0)}
        cc = e.get("cc")
        if isinstance(cc, str) and cc: ent["cc"] = cc[:2].upper()
        if isinstance(e.get("season"), (int, float)): ent["season"] = int(e["season"])
        cur = best.get(nm)
        if cur is None or rank(ent) > rank(cur):
            if not ent.get("cc") and cur and cur.get("cc"): ent["cc"] = cur["cc"]
            best[nm] = ent
    return sorted(best.values(), key=lambda x: -rank(x))[:BOARD_MAX]

def buckets_of(node):
    """return season buckets as {str_key: [entries]} from a scores node (list or dict form)."""
    ss = node.get("seasons") if isinstance(node, dict) else None
    out = {}
    if isinstance(ss, list):
        for i, b in enumerate(ss):
            if isinstance(b, list): out[str(i)] = b
    elif isinstance(ss, dict):
        for k, b in ss.items():
            if isinstance(b, list): out[str(k)] = b
    return out

def guard_scores():
    try:
        live = get(f"{FB}/maria_trex_scores.json")
    except Exception as e:
        log(f"scores SKIP — read failed: {e}"); return
    if not isinstance(live, dict): log("scores SKIP — not an object"); return

    live_list = live.get("scores") if isinstance(live.get("scores"), list) else []
    live_bk   = buckets_of(live)

    snap = {"scores": [], "seasons": {}}
    if os.path.exists(SCORE_HWM):
        try: snap = json.load(open(SCORE_HWM)) or {"scores": [], "seasons": {}}
        except Exception: pass
    snap_list = snap.get("scores", []) if isinstance(snap.get("scores"), list) else []
    snap_bk   = snap.get("seasons", {}) if isinstance(snap.get("seasons"), dict) else {}

    # union (high-water-mark) — best-per-name everywhere
    union_list = normalize(live_list + snap_list)
    union_bk = {}
    for k in set(live_bk) | set(snap_bk):
        union_bk[k] = normalize((live_bk.get(k) or []) + (snap_bk.get(k) or []))

    # did LIVE lose anything vs the union? (a name dropped, or a score lowered)
    def name_rank_map(arr):
        m = {}
        for e in arr:
            if isinstance(e, dict): m[str(e.get("name","")).upper()[:10]] = max(m.get(str(e.get("name","")).upper()[:10], -1), rank(e))
        return m
    live_all = name_rank_map(live_list); union_all = name_rank_map(union_list)
    lost_alltime = [n for n, r in union_all.items() if r > live_all.get(n, -1) + 1e-9]
    lost_bucket = {}
    for k in union_bk:
        lr = name_rank_map(live_bk.get(k) or []); ur = name_rank_map(union_bk[k])
        miss = [n for n, r in ur.items() if r > lr.get(n, -1) + 1e-9]
        if miss: lost_bucket[k] = miss

    if lost_alltime or lost_bucket:
        log(f"⚠ SCORES DROP — all-time lost {sorted(lost_alltime)}; buckets lost { {k:sorted(v) for k,v in lost_bucket.items()} }")
        # re-read fresh right before writing to shrink the race window, re-union with the fresh live
        try: fresh = get(f"{FB}/maria_trex_scores.json")
        except Exception as e: log(f"   scores heal abort — re-read failed: {e}"); fresh = live
        f_list = fresh.get("scores") if isinstance(fresh.get("scores"), list) else live_list
        f_bk = buckets_of(fresh) or live_bk
        heal_list = normalize(f_list + union_list)
        heal_bk = {}
        for k in set(f_bk) | set(union_bk):
            heal_bk[k] = normalize((f_bk.get(k) or []) + (union_bk.get(k) or []))
        # SUPERSET GUARD: every fresh-live entry must survive in the healed result, else abort
        def superset_ok():
            fl = name_rank_map(f_list); hl = name_rank_map(heal_list)
            if any(hl.get(n, -1) + 1e-9 < r for n, r in fl.items()): return False
            for k in f_bk:
                fr = name_rank_map(f_bk.get(k) or []); hr = name_rank_map(heal_bk.get(k) or [])
                if any(hr.get(n, -1) + 1e-9 < r for n, r in fr.items()): return False
            return True
        if not superset_ok():
            log("   scores heal ABORTED — superset guard tripped (would not preserve a live entry)")
        else:
            body = {"scores": heal_list, "season": fresh.get("season", live.get("season")), "seasons": heal_bk}
            try:
                put(f"{FB}/maria_trex_scores.json", body)
                log(f"✅ scores healed — all-time {len(heal_list)} names; buckets { {k:len(v) for k,v in heal_bk.items()} }")
                union_list, union_bk = heal_list, heal_bk
            except Exception as e:
                log(f"   scores heal write FAILED: {e}")

    # persist the high-water-mark snapshot (frequent backup)
    json.dump({"scores": union_list, "seasons": union_bk, "season": live.get("season")},
              open(SCORE_HWM, "w"), indent=2)

def main():
    guard_profiles()
    guard_scores()
    return 0

if __name__ == "__main__":
    sys.exit(main())
