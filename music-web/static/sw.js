/* TuneBox service worker — caches static assets and the player shell for
   offline loading. Dynamic pages (/admin, invite links) are NEVER cached so
   the admin panel always shows the live library. Track downloads are managed
   by the app itself (Cache API "tunebox-tracks-*") and played via blob URLs,
   so audio requests are intentionally NOT intercepted here. */
const SHELL_CACHE = "tunebox-shell-v2";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(SHELL_CACHE)
      .then((c) => c.addAll(["/", "/static/manifest.json"]))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && !k.startsWith("tunebox-tracks"))
          .map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // app handles audio itself
  // Admin panel and invite links must always be fresh — never cache them.
  if (url.pathname.startsWith("/admin") || url.pathname.startsWith("/i/")) return;
  if (url.pathname.startsWith("/static/")) {
    // Cache-first for static assets (immutable-ish).
    e.respondWith(
      caches.match(e.request).then(
        (hit) =>
          hit ||
          fetch(e.request).then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(SHELL_CACHE).then((c) => c.put(e.request, copy));
            }
            return res;
          })
      )
    );
    return;
  }
  // Network-first for pages: always fresh when online, cached copy when offline.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(e.request).then((hit) => hit || caches.match("/"))
      )
  );
});
