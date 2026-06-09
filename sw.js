/* Maria T-Rex — service worker: works offline, but stays update-friendly */
const CACHE = "kush-rush-v11";
const ASSETS = [
  "./", "index.html", "manifest.json",
  "icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png"
];
self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS).catch(() => {})));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Never intercept cross-origin requests (e.g. the leaderboard API) — keep them live.
  if (url.origin !== self.location.origin) return;

  // HTML / navigation: network-first so new deploys are picked up; cache is the offline fallback.
  const isDoc = req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  if (isDoc) {
    e.respondWith(
      fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put("index.html", copy)).catch(() => {});
        return resp;
      }).catch(() => caches.match("index.html").then((r) => r || caches.match("./")))
    );
    return;
  }

  // Static assets: serve from cache fast, refresh in the background (stale-while-revalidate).
  e.respondWith(
    caches.match(req).then((cached) => {
      const net = fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return resp;
      }).catch(() => cached);
      return cached || net;
    })
  );
});
