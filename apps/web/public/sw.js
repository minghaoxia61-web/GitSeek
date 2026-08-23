const CACHE = "gitseek-shell-v2";
const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, "");
const assetPath = (path) => `${BASE_PATH}${path}`;
const APP_SHELL = assetPath("/");
const SHELL = [APP_SHELL, assetPath("/manifest.webmanifest"), assetPath("/favicon.svg"), assetPath("/icon-192.png"), assetPath("/icon-512.png")];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith(assetPath("/api/")) || url.pathname === assetPath("/health")) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(APP_SHELL, copy));
      return response;
    }).catch(() => caches.match(APP_SHELL)));
    return;
  }

  event.respondWith(caches.match(request).then((cached) => {
    const fresh = fetch(request).then((response) => {
      if (response.ok) caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    });
    return cached || fresh;
  }));
});
