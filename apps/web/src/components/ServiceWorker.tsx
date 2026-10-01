"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const ENABLED = process.env.NODE_ENV === "production";

/**
 * Hizmet çalışanını kaydeder (yalnız üretim derlemesinde). Her sayfa değişiminde açılan sayfayı
 * ve yüklenen dosyaları bildirir; canlı kayıt ekranı bir kez açıldıktan sonra çevrimdışı açılır.
 */
export function ServiceWorker() {
  const pathname = usePathname();

  useEffect(() => {
    if (!ENABLED || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!ENABLED || !("serviceWorker" in navigator)) return;
    let cancelled = false;
    // Sayfanın istemci tarafında yüklediği parçalar da listeye girsin diye kısa bir bekleme.
    const timer = window.setTimeout(() => {
      navigator.serviceWorker.ready
        .then((registration) => {
          if (cancelled) return;
          const urls = [
            pathname,
            ...performance
              .getEntriesByType("resource")
              .map((entry) => entry.name)
              .filter((name) => name.startsWith(window.location.origin)),
          ];
          registration.active?.postMessage({ type: "warm", urls });
        })
        .catch(() => undefined);
    }, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [pathname]);

  return null;
}
