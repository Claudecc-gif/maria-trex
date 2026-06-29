# Firebase rules — lock the leaderboard so it can never be wiped again

**Why:** the `maria_trex_profiles` node is the "everyone" store behind both score
boards. A buggy/old client could PUT the *whole* node with only its own profile and
wipe every other player (this happened 2026‑06‑29, 19:18). These rules make that
**structurally impossible**: a client may only write its OWN profile child, never the
whole collection. They also **replace the 30‑day TEST‑mode rules** that expire around
**2026‑07‑08** (after which the leaderboard/chat would go permission‑denied).

## How to deploy (2 minutes, needs the Firebase console — no local admin key here)

1. Open <https://console.firebase.google.com/> → project **kush-rush-864ed**.
2. Left menu → **Realtime Database** → **Rules** tab.
3. Replace everything in the editor with the contents of `firebase_rules.json`
   (in this folder).
4. Click **Publish**.

## What the rules do

| Path | read | write |
|------|------|-------|
| `maria_trex_scores` / `stats` / `chat` | ✅ | ✅ (merge‑based, self‑healing) |
| `maria_trex_profiles` (whole node) | ✅ | ❌ **can't be replaced/wiped** |
| `maria_trex_profiles/profiles` (whole collection) | ✅ | ❌ **can't be replaced/wiped** |
| `maria_trex_profiles/profiles/<NAME>` (one player) | ✅ | ✅ per‑child only |

After publishing, even an **old cached client** running the buggy whole‑node write
gets **permission‑denied** and cannot clobber anyone — its save just fails quietly
until that device picks up the new game version.

> Note: the on‑disk helper scripts `restore_highscores.sh` and the one‑off
> `restore_profiles.py` use whole‑node PUTs and would be rejected once these rules are
> live. The **daily backup** (read‑only) and the **profiles guardian**
> (`profiles_guardian.py`, per‑child writes) keep working fine. If you ever need a full
> restore after the rules are live, run it from the console or temporarily relax the
> `profiles` rule.
