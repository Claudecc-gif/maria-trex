#!/bin/zsh
# ---------------------------------------------------------------------------
# Kush Rush — restore the high-score board from a backup snapshot.
#
#   ./restore_highscores.sh list                 # list available raw snapshots
#   ./restore_highscores.sh show  <raw-file>     # preview a snapshot (names + season buckets)
#   ./restore_highscores.sh scores <raw-file>    # OVERWRITE maria_trex_scores with this snapshot
#   ./restore_highscores.sh profiles <raw-file>  # OVERWRITE maria_trex_profiles with this snapshot
#
# Always takes a fresh safety snapshot of the live doc before overwriting.
# ---------------------------------------------------------------------------
set -u
FB="https://kush-rush-864ed-default-rtdb.europe-west1.firebasedatabase.app"
ROOT="$HOME/maria-trex-game/backups"
cmd="${1:-list}"; arg="${2:-}"

case "$cmd" in
  list)
    echo "Raw snapshots in $ROOT/raw:"; ls -1t "$ROOT/raw"/scores_*.json 2>/dev/null | head -30 ;;
  show)
    [ -s "$arg" ] || { echo "usage: $0 show <raw-scores-file>"; exit 1; }
    python3 - "$arg" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
sc=d.get("scores",[]) if isinstance(d,dict) else d
print("all-time names:",len(sc))
ss=d.get("seasons",{}) if isinstance(d,dict) else {}
items=enumerate(ss) if isinstance(ss,list) else ss.items()
for k,b in items:
    if isinstance(b,list): print(f"  Season {int(k)+1}: {len(b)} -> {[e.get('name') for e in b]}")
PY
    ;;
  scores|profiles)
    [ -s "$arg" ] || { echo "usage: $0 $cmd <raw-file>"; exit 1; }
    python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$arg" || { echo "not valid JSON"; exit 1; }
    doc="maria_trex_${cmd}"
    safe="$ROOT/raw/${cmd}_PRE_RESTORE_$(date -u +%Y%m%dT%H%M%SZ).json"
    curl -fsS --max-time 30 "$FB/${doc}.json" -o "$safe" && echo "safety snapshot -> $safe"
    echo "About to OVERWRITE $doc with $arg"
    read "?Type YES to proceed: " confirm
    [ "$confirm" = "YES" ] || { echo "aborted"; exit 1; }
    curl -fsS --max-time 30 -X PUT "$FB/${doc}.json" --data-binary @"$arg" >/dev/null \
      && echo "restored $doc from $arg" || { echo "restore FAILED"; exit 1; } ;;
  *) echo "usage: $0 {list|show|scores|profiles} [file]"; exit 1 ;;
esac
