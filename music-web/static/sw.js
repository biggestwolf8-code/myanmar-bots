/* TuneBox service worker — caches the app shell for offline loading.
   Track downloads are managed by the app itself (Cache API "tunebox-tracks-*")
   and played via blob URLs, so audio requests are intentionally NOT
   intercepted here. */
const SHELL_CACHE = "tunebox-shell-v1";

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
  e.respondWith(
    caches.match(e.request).then(
      (hit) =>
        hit ||
        fetch(e.request)
          .then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(SHELL_CACHE).then((c) => c.put(e.request, copy));
            }
            return res;
          })
          .catch(() => caches.match("/"))
    )
  );
});
