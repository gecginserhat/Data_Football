export { auth as proxy } from "@/auth";

export const config = {
  // Statik dosyalar, PWA dosyaları ve Auth.js uçları hariç tüm sayfalar oturum ister.
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|robots.txt|sw.js|manifest.webmanifest|icons/).*)",
  ],
};
