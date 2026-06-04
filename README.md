# 🦖 Maria the T-Rex — Most Wanted: Kush Run

A single-file, installable browser game. Maria the T-Rex collects weed and outruns
the police across Kuala Lumpur, the desert, a volcano and neon nights.

**Play:** https://claudecc-gif.github.io/maria-trex/

- Tap / click to play — works on phones (Add to Home Screen for an app icon) and desktop.
- Runs offline once loaded (PWA + service worker).
- 🏆 High-score list with name entry.

### Controls
← → run · SPACE / ⤒ jump · F / 🚬 shoot · M mute · N music · P pause

### Leaderboard
Out of the box the high-score list is saved **per-device**. To make it a single list
**shared by everyone** with the link, set `BOARD.provider = "pantry"` and paste a free
[Pantry](https://getpantry.cloud) ID into `BOARD.pantryId` (top of the `<script>` in
`index.html`), then redeploy.
