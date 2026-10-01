/**
 * Auth.js v5 + OIDC (ADR-0005). Yerelde Keycloak, canlıda kulübün IdP'si.
 * Erişim token'ı yalnızca şifreli oturum çerezinde durur; tarayıcı JS'ine verilmez.
 */
import NextAuth, { type NextAuthConfig } from "next-auth";
import type { JWT } from "next-auth/jwt";
import Keycloak from "next-auth/providers/keycloak";

const issuer = process.env.OIDC_ISSUER ?? "http://keycloak.localhost:8080/realms/kurgu";
const clientId = process.env.OIDC_CLIENT_ID ?? "kurgu-web";
const clientSecret = process.env.OIDC_CLIENT_SECRET ?? "";

/** Token süresi dolmadan bu kadar saniye önce yenilenir. */
const REFRESH_MARGIN_S = 30;

interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
}

/**
 * Çıkışta Keycloak oturumunu da kapatır (ASVS V3.3.1). Yalnız yerel çerez silinirse bir sonraki
 * "Giriş yap" parolasız geri döner. Başarısızlık çıkışı engellemez.
 */
async function endIdpSession(token: JWT | null | undefined): Promise<void> {
  if (!token?.refreshToken) return;
  try {
    await fetch(`${issuer}/protocol/openid-connect/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: token.refreshToken,
      }),
    });
  } catch {
    // Keycloak'a ulaşılamazsa yerel oturum yine de kapanır.
  }
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const response = await fetch(`${issuer}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: token.refreshToken ?? "",
      }),
    });
    if (!response.ok) throw new Error(`refresh failed: ${response.status}`);
    const data = (await response.json()) as TokenResponse;
    return {
      ...token,
      accessToken: data.access_token,
      expiresAt: Math.floor(Date.now() / 1000) + data.expires_in,
      refreshToken: data.refresh_token ?? token.refreshToken,
      error: undefined,
    };
  } catch {
    return { ...token, error: "RefreshAccessTokenError" };
  }
}

export const authConfig = {
  providers: [
    Keycloak({
      issuer,
      clientId,
      clientSecret,
      authorization: { params: { scope: "openid profile email" } },
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/signin" },
  trustHost: true,
  events: {
    async signOut(message) {
      await endIdpSession("token" in message ? message.token : null);
    },
  },
  callbacks: {
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      if (pathname.startsWith("/signin")) return true;
      return Boolean(auth?.user);
    },
    async jwt({ token, account }) {
      if (account) {
        return {
          ...token,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          expiresAt: account.expires_at,
        };
      }
      const now = Math.floor(Date.now() / 1000);
      if (token.expiresAt && now < token.expiresAt - REFRESH_MARGIN_S) return token;
      if (!token.refreshToken) return { ...token, error: "RefreshAccessTokenError" };
      return refreshAccessToken(token);
    },
    session({ session, token }) {
      // Erişim token'ı bilinçli olarak oturum nesnesine konmaz.
      return { ...session, error: token.error };
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
