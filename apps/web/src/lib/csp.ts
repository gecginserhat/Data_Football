/**
 * İçerik güvenlik politikası (ADR-0016, A-88). Betikler istek başına nonce ile izinlidir;
 * `strict-dynamic` sayesinde Next.js'in yüklediği parçalar da çalışır. Satır içi stil Next.js ve
 * Tailwind gereği izinlidir.
 */

function origin(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

export interface CspOptions {
  nonce: string;
  dev: boolean;
  /** Tarayıcının video, yükleme ve dosya için doğrudan eriştiği adresler (API, nesne deposu). */
  mediaOrigins: string[];
  /** Kimlik sağlayıcı: giriş formu oraya yönlendirir. */
  issuer?: string;
  https: boolean;
}

export function buildCsp({ nonce, dev, mediaOrigins, issuer, https }: CspOptions): string {
  const media = [...new Set(mediaOrigins.map(origin).filter((o): o is string => Boolean(o)))];
  const idp = origin(issuer);
  const directives: [string, string[]][] = [
    ["default-src", ["'self'"]],
    [
      "script-src",
      ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(dev ? ["'unsafe-eval'"] : [])],
    ],
    ["style-src", ["'self'", "'unsafe-inline'"]],
    ["img-src", ["'self'", "data:", "blob:", ...media]],
    ["font-src", ["'self'"]],
    ["media-src", ["'self'", "blob:", ...media]],
    ["connect-src", ["'self'", ...media, ...(dev ? ["ws:"] : [])]],
    ["worker-src", ["'self'", "blob:"]],
    ["manifest-src", ["'self'"]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'self'"]],
    ["form-action", ["'self'", ...(idp ? [idp] : [])]],
    ["frame-ancestors", ["'none'"]],
  ];
  const parts = directives.map(([name, values]) => `${name} ${values.join(" ")}`);
  if (https) parts.push("upgrade-insecure-requests");
  return parts.join("; ");
}

export function makeNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
