// MedX Scribe service worker (slice v2c T11): installability only.
// No storage of any kind and no request handling, so transcripts and API responses never persist on the phone.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
