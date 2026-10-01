"use client";

import dynamic from "next/dynamic";

/**
 * Kayıt ekranı yalnızca tarayıcıda çizilir: cihaz kimliği, maç saati ve kayıtlar tarayıcı
 * deposundan (localStorage, IndexedDB) okunur.
 */
export const LiveTaggerClient = dynamic(() => import("./LiveTagger").then((m) => m.LiveTagger), {
  ssr: false,
  loading: () => <div className="h-96 animate-pulse rounded-lg bg-surface" />,
});
