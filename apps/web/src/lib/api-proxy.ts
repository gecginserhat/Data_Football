import "server-only";
import { apiFetch } from "./api";

/**
 * Tarayıcının çağırdığı küçük vekil uçlar (canlı kayıt senkronizasyonu, video oynatma listesi).
 * Erişim token'ı sunucuda eklenir; tarayıcıya hiç verilmez (ADR-0005).
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

export function badRequest(): Response {
  return Response.json(
    { type: "about:blank#invalid-id", title: "Bad Request", status: 400 },
    { status: 400, headers: { "Content-Type": "application/problem+json" } },
  );
}

/** API yanıtını gövdesi, durumu ve içerik türüyle aynen döner. */
export async function forward(path: string, init: RequestInit): Promise<Response> {
  try {
    const upstream = await apiFetch(path, init);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { type: "about:blank#upstream", title: "Bad Gateway", status: 502 },
      { status: 502, headers: { "Content-Type": "application/problem+json" } },
    );
  }
}
