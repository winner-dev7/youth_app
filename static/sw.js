const CACHE_NAME = "youth_app-v2";

const urlsToCache = [
  "/",
  "/dashboard",
  "/collectes",
    "/collecte",
    "/members",
    "/dettes",
  "/static/style.css",
    "/static/etk_youth.jpeg"

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
    event.respondWith(
        fetch(event.request)
            .then(response => {
                // clone pour le cache
                let responseClone = response.clone();

                caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, responseClone);
                });

                return response;
            })
            .catch(() => {
                // si offline → cache
                return caches.match(event.request);
            })
    );
});