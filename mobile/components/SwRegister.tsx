"use client";

import { useEffect } from "react";

/** Registers the minimal service worker (installability only: no caching, no fetch handling). */
export function SwRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);
  return null;
}
