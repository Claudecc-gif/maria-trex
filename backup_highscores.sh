#!/bin/zsh
# ---------------------------------------------------------------------------
# Kush Rush — daily high-score backup.
# Snapshots the Firebase RTDB docs (scores, profiles, stats) to disk, and ALSO
# splits the score doc into:
#   - alltime_<ts>.json     : the all-time best-per-name board (the `scores` array)
#   - season3_<ts>.json ...  : each weekly season bucket, saved SEPARATELY
# so a corrupted board can be restored from a known-good day. Lossless raw copy
# is always kept under backups/raw/. Retention: keep RETAIN_DAYS of snapshots.
#
# Scheduled by ~/Library/LaunchAgents/com.kushrush.highscore_backup.plist (daily
# + on login). Restore with restore_highscores.sh.
# ---------------------------------------------------------------------------
set -u
FB="https://kush-rush-864ed-default-rtdb.europe-west1.firebasedatabase.app"
ROOT="$HOME/maria-trex-game/backups"
RETAIN_DAYS=120
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DAY="$(date -u +%Y-%m-%d)"
mkdir -p "$ROOT/raw" "$ROOT/alltime" "$ROOT/seasons"

ok=1
for doc in scores profiles stats; do
  tmp="$(mktemp)"
  if curl -fsS --max-time 30 "$FB/maria_trex_${doc}.json" -o "$tmp" 2>/dev/null \
     && [ -s "$tmp" ] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$tmp" 2>/dev/null; then
    mv "$tmp" "$ROOT/raw/${doc}_${TS}.json"
  else
    rm -f "$tmp"; ok=0
    echo "$(date -u) WARN: could not fetch/validate $doc — skipping this doc" >> "$ROOT/backup.log"
  fi
done

# Split the scores doc into all-time + per-season files (only if we got a good one).
SCORES_RAW="$ROOT/raw/scores_${TS}.json"
if [ -s "$SCORES_RAW" ]; then
  python3 - "$SCORES_RAW" "$ROOT" "$TS" <<'PY'
import json, sys, os
raw, root, ts = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(raw))
scores = d.get("scores", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
# all-time board (best-per-name array as stored)
json.dump({"savedAt": ts, "count": len(scores), "scores": scores},
          open(os.path.join(root, "alltime", f"alltime_{ts}.json"), "w"), indent=1)
# per-season buckets — saved SEPARATELY, named by human season label (idx+1)
seasons = d.get("seasons", {}) if isinstance(d, dict) else {}
items = enumerate(seasons) if isinstance(seasons, list) else seasons.items()
for k, bucket in items:
    if not isinstance(bucket, list):
        continue
    try: idx = int(k)
    except Exception: continue
    label = idx + 1  # internal index 2 == "Season 3"
    json.dump({"savedAt": ts, "seasonIndex": idx, "seasonLabel": f"Season {label}",
               "count": len(bucket), "scores": bucket},
              open(os.path.join(root, "seasons", f"season{label}_{ts}.json"), "w"), indent=1)
print(f"split ok: alltime={len(scores)} names, seasons={[ (int(k)+1) for k,b in (list(enumerate(seasons)) if isinstance(seasons,list) else seasons.items()) if isinstance(b,list)]}")
PY
fi

# Retention: delete snapshots older than RETAIN_DAYS (raw + split).
find "$ROOT/raw" "$ROOT/alltime" "$ROOT/seasons" -type f -name '*.json' -mtime +${RETAIN_DAYS} -delete 2>/dev/null

[ "$ok" = "1" ] && echo "$(date -u) OK backup ${TS}" >> "$ROOT/backup.log"
exit 0
