import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { buildCsp, makeNonce } from "@/lib/csp";

/**
 * Oturum denetimi ve istek başına nonce'lu CSP (ADR-0005, ADR-0016). Oturumsuz istek giriş
 * sayfasına yönlenir.
 */
export const proxy = auth((request) => {
  const nonce = makeNonce();
  const csp = buildCsp({
    nonce,
    dev: process.env.NODE_ENV !== "production",
    mediaOrigins: [
      process.env.KURGU_PUBLIC_API_URL ?? "http://localhost:8000",
      process.env.S3_PUBLIC_ENDPOINT_URL ?? "",
    ],
    issuer: process.env.OIDC_ISSUER,
    https: (process.env.AUTH_URL ?? "").startsWith("https://"),
  });

  const { pathname } = request.nextUrl;
  let response: NextResponse;
  if (!request.auth?.user && !pathname.startsWith("/signin")) {
    const signIn = request.nextUrl.clone();
    signIn.pathname = "/signin";
    signIn.search = "";
    signIn.searchParams.set("callbackUrl", request.nextUrl.href);
    response = NextResponse.redirect(signIn);
  } else {
    // Next.js nonce'u istek başlığındaki CSP'den okur ve kendi betiklerine ekler.
    const headers = new Headers(request.headers);
    headers.set("x-nonce", nonce);
    headers.set("Content-Security-Policy", csp);
    response = NextResponse.next({ request: { headers } });
  }
  response.headers.set("Content-Security-Policy", csp);
  return response;
});

export const config = {
  // Statik dosyalar, PWA dosyaları ve Auth.js uçları hariç tüm sayfalar oturum ister.
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|robots.txt|sw.js|manifest.webmanifest|icons/).*)",
  ],
};
