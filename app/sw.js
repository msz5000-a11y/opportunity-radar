// Service worker: la app abre sin conexión, pero siempre intenta la red primero para no enseñar datos viejos.
const CACHE = "radar-v3-8";
const SHELL = ["./", "index.html", "style.css?v=14", "app.js?v=14", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  const key = url.pathname.includes("/data/") ? url.pathname : req.url;
  const fresh = req.mode === "navigate" ? fetch(url.href, {cache: "no-cache", credentials: "same-origin"}) : fetch(req, {cache: "no-cache"});
  e.respondWith(fresh.then((r) => {
    if (r && r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(key, copy)); }
    return r;
  }).catch(() => caches.match(key).then((m) => m || (req.mode === "navigate" ? caches.match("index.html") : undefined))));
});
