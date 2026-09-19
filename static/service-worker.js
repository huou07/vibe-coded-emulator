// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// app.py replaces this static template marker at request time. Keeping the
// template itself hashable avoids a circular asset-version calculation while
// giving every deployment an isolated PWA shell cache.
const CACHE = "an3-arcade-pwa-v31-__ASSET_VERSION__";
const CORE_CACHE = "an3-arcade-cores-v1";
const APP_SHELL = [
  "/", "/offline", "/download-app", "/static/site.css", "/static/site.js",
  "/static/v/__ASSET_VERSION__/site.css", "/static/v/__ASSET_VERSION__/offline.js", "/static/v/__ASSET_VERSION__/player-ui.js", "/static/v/__ASSET_VERSION__/player-runtime.js", "/static/v/__ASSET_VERSION__/renderer-worker.js", "/static/v/__ASSET_VERSION__/nds-touch.js", "/static/v/__ASSET_VERSION__/player.js",
  "/static/default-cover.webp", "/static/manifest.webmanifest",
  "/static/ui-arrow-left.svg", "/static/ui-maximize.svg", "/static/ui-save.svg", "/static/ui-more.svg",
  "/static/ui-chevron-up.svg", "/static/ui-chevron-down.svg", "/static/ui-chevron-left.svg", "/static/ui-chevron-right.svg",
  "/static/ui-library-search.svg", "/static/ui-library-wifi-off.svg", "/static/ui-library-menu.svg",
  "/static/ui-library-star.svg", "/static/ui-library-star-filled.svg", "/static/ui-library-gamepad-2.svg", "/static/ui-library-play.svg",
  "/static/ui-library-download.svg", "/static/ui-library-chevron-right.svg",
  "/static/ui-ref-download.svg", "/static/ui-ref-monitor-down.svg", "/static/ui-ref-gamepad-2.svg",
  "/static/ui-ref-hard-drive.svg", "/static/ui-ref-eye-off.svg",
  "/static/fonts/pixelify-sans-latin.woff2", "/static/fonts/pixelify-sans-latin-ext.woff2",
  "/static/fonts/roboto-condensed-latin.woff2", "/static/fonts/roboto-condensed-latin-ext.woff2",
  "/static/fonts/roboto-condensed-vietnamese.woff2"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    // Older workers stored large EmulatorJS assets in the versioned app-shell
    // cache. Preserve them before removing stale shells so a normal site update
    // does not silently delete cores downloaded for offline play.
    const coreCache=await caches.open(CORE_CACHE);
    const keys=await caches.keys();
    for (const key of keys.filter(name=>name.startsWith("an3-arcade-pwa-") && name!==CACHE)) {
      const oldCache=await caches.open(key);
      for (const request of await oldCache.keys()) {
        const url=new URL(request.url);
        if (url.hostname!=="cdn.emulatorjs.org" && !url.pathname.startsWith("/emulatorjs/")) continue;
        if (!await coreCache.match(request)) {
          const response=await oldCache.match(request);
          if (response) await coreCache.put(request,response);
        }
      }
      await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const sameOrigin = url.origin === self.location.origin;
  const emulatorCdn = url.hostname === "cdn.emulatorjs.org";
  const emulatorAsset = emulatorCdn || (sameOrigin && url.pathname.startsWith("/emulatorjs/"));
  if (!sameOrigin && !emulatorCdn) return;
  // ROM downloads belong to the user's browser/download manager, never to
  // Cache Storage. Caching them duplicates large files and can evict the
  // private offline shell or downloaded emulator cores.
  if (sameOrigin && (url.pathname.startsWith("/game-file/") || url.pathname.startsWith("/download/") || url.pathname.startsWith("/download-app/release/") || url.pathname === "/download-app/source")) return;
  // API responses include live user/admin data. Cache Storage ignores a page
  // fetch's cache mode, so these must always go to the network.
  if (sameOrigin && (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin/api/") || url.pathname === "/download-app/artifacts.json")) {
    event.respondWith(fetch(event.request, {cache: "no-store"}));
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).then(async response => {
      if (response.ok) await caches.open(CACHE).then(cache => cache.put(event.request, response.clone())).catch(() => {});
      return response;
    }).catch(() => {
      const pathname = new URL(event.request.url).pathname || "/";
      return caches.match(pathname).then(response => response || caches.match("/")).then(response => response || caches.match("/offline"));
    }));
    return;
  }
  const cacheName=emulatorAsset ? CORE_CACHE : CACHE;
  // Legacy page assets use ?v=<asset>; the pathname-versioned player boot
  // assets above deliberately bypass this lookup. That means an old worker
  // with a queryless player cache cannot serve an incompatible new runtime.
  // Never relax matching for emulator binaries.
  const shellMatchOptions=sameOrigin && !emulatorAsset && url.pathname.startsWith("/static/") ? {ignoreSearch:true} : undefined;
  event.respondWith(caches.open(cacheName).then(cache=>cache.match(event.request,shellMatchOptions).then(cached => cached || fetch(event.request).then(async response => {
    if (response.ok || response.type === "opaque") {
      await cache.put(event.request, response.clone()).catch(() => {});
    }
    return response;
  }))));
});
