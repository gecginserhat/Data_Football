import "server-only";
import { createKurguClient, TENANT_HEADER, type Me } from "@kurgu/api-client";
import { cookies } from "next/headers";
import { cache } from "react";
import { getAccessToken } from "./session";

export const TENANT_COOKIE = "kurgu_tenant";

const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Oturumdaki kullanıcının kimlik ve kulüp başlıkları. */
export async function apiHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  const tenant = (await cookies()).get(TENANT_COOKIE)?.value;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (tenant) headers[TENANT_HEADER] = tenant;
  return headers;
}

/** Oturumdaki kullanıcı adına API istemcisi (yalnızca sunucuda). */
export async function apiClient() {
  return createKurguClient({ baseUrl, headers: await apiHeaders() });
}

/** openapi-fetch'in çok parçalı gövdeyi desteklemediği yüklemeler için ham istek. */
export async function apiFetch(path: string, init: RequestInit): Promise<Response> {
  const headers = { ...(await apiHeaders()), ...(init.headers as Record<string, string>) };
  return fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
}

export type MeResult =
  | { status: "ok"; me: Me }
  | { status: "unauthenticated" }
  /** Rol MFA ister, token'da kanıt yok (ADR-0016): Keycloak'ta adım yükseltme gerekir. */
  | { status: "mfa-required" }
  | { status: "error"; httpStatus?: number };

export async function fetchMe(): Promise<MeResult> {
  try {
    const client = await apiClient();
    const { data, error, response } = await client.GET("/api/v1/me");
    if (data) return { status: "ok", me: data };
    if (response.status === 401) return { status: "unauthenticated" };
    const problemType = (error as { type?: unknown } | undefined)?.type;
    if (
      response.status === 403 &&
      typeof problemType === "string" &&
      problemType.endsWith("/mfa-required")
    ) {
      return { status: "mfa-required" };
    }
    return { status: "error", httpStatus: response.status };
  } catch {
    return { status: "error" };
  }
}

export function permissionSet(me: Me): Set<string> {
  return new Set(Object.keys(me.active_tenant?.permissions ?? {}));
}

/** İstek başına tek `/me` çağrısı (layout ve sayfalar paylaşır). */
export const getMe = cache(fetchMe);
