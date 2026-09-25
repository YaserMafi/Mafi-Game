/* MAFI PWA — cache audio only; never cache HTML/CSS/JS (layout updates must apply instantly) */
const CACHE = "mafi-v25-audio-only";
const ASSETS = [
  "/manifest.webmanifest",
  "/assets/icon-192.png",
  "/assets/music/lobby.wav",
  "/assets/music/night.wav",
  "/assets/music/day.wav",
  "/assets/music/vote.wav",
  "/assets/music/end.wav",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((k) => (k === CACHE ? null : caches.delete(k)))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (u.origin !== self.location.origin) return;
  if (e.request.method !== "GET") return;

  // Never intercept app shell — always hit network (no stale layout)
  const path = u.pathname;
  if (
    path === "/" ||
    path.endsWith(".html") ||
    path.endsWith(".js") ||
    path.endsWith(".css") ||
    path === "/sw.js" ||
    path.startsWith("/api/") ||
    path.startsWith("/socket.io") ||
    path.startsWith("/tts")
  ) {
    return;
  }

  // Cache only static media under /assets/
  if (!path.startsWith("/assets/")) return;

  e.respondWith(
    caches.match(e.request).then(
      (hit) =>
        hit ||
        fetch(e.request).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          }
          return res;
        })
    )
  );
});
