import type { MetadataRoute } from "next";

/** Web uygulama bildirimi (PWA, SPEC §13.1). Tablette ana ekrana eklenip tam ekran açılır. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Kurgu",
    short_name: "Kurgu",
    description: "Duran top analiz ve hazırlık platformu",
    lang: "tr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#F2F4F1",
    theme_color: "#0E3B2E",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icons/icon.svg", sizes: "any", type: "image/svg+xml" },
    ],
    shortcuts: [{ name: "Canlı kayıt", url: "/live" }],
  };
}
