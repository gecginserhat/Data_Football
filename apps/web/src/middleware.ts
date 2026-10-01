export { auth as middleware } from "@/auth";

export const config = {
  // Statik dosyalar ve Auth.js uçları hariç tüm sayfalar oturum ister.
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
