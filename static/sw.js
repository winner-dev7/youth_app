const CACHE_NAME = "youth_app-v2";

const urlsToCache = [
  "/",
  "/membres",
  "/collecte",
  "/collectes",
  "/dettes",
  "/static/style.css",
  "/static/icons/etk_youth.jpeg"
];

// INSTALL
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// FETCH STRATEGY (SMART)
self.addEventListener("fetch", event => {
    // On ne gère que les requêtes GET — POST passe directement au réseau
    if (event.request.method !== "GET") {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(response => {
                let responseClone = response.clone();
                caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, responseClone);
                });
                return response;
            })
            .catch(() => {
                return caches.match(event.request);
            })
    );
});