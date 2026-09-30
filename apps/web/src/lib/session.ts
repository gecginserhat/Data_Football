import "server-only";
import { headers } from "next/headers";
import { getToken } from "next-auth/jwt";

const SECURE = (process.env.AUTH_URL ?? "").startsWith("https://");
const COOKIE = SECURE ? "__Secure-authjs.session-token" : "authjs.session-token";

/** Sunucu tarafında şifreli oturum çerezinden erişim token'ını okur. */
export async function getAccessToken(): Promise<string | null> {
  const token = await getToken({
    req: { headers: await headers() },
    secret: process.env.AUTH_SECRET,
    secureCookie: SECURE,
    cookieName: COOKIE,
    salt: COOKIE,
  });
  return token?.accessToken ?? null;
}
