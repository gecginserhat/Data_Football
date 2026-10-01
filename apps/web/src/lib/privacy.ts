import "server-only";
import type { Schemas } from "@kurgu/api-client";
import type { Loaded } from "./analysis";
import { apiClient } from "./api";

/** KVKK veri katmanı: rıza, envanter ve saklama, veri sahibi talepleri (ADR-0019, A-92). */

export type ConsentStatus = Schemas["ConsentStatusOut"];
export type ConsentText = Schemas["ConsentTextOut"];
export type PrivacySettings = Schemas["PrivacySettingsOut"];
export type PrivacyRequest = Schemas["RequestOut"];

function settle<T>(data: T | undefined, response: Response): Loaded<T> {
  if (data !== undefined) return { status: "ok", data };
  if (response.status === 403) return { status: "forbidden" };
  if (response.status === 404) return { status: "missing" };
  return { status: "error" };
}

async function guarded<T>(run: () => Promise<Loaded<T>>): Promise<Loaded<T>> {
  try {
    return await run();
  } catch {
    return { status: "error" };
  }
}

export function getConsent(playerId: string): Promise<Loaded<ConsentStatus>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/squad/{player_id}/consent", {
      params: { path: { player_id: playerId } },
    });
    return settle(data, response);
  });
}

export function getConsentText(): Promise<Loaded<ConsentText>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/privacy/consent-text");
    return settle(data, response);
  });
}

export function getPrivacySettings(): Promise<Loaded<PrivacySettings>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/privacy/settings");
    return settle(data, response);
  });
}

export function listPrivacyRequests(): Promise<Loaded<PrivacyRequest[]>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/privacy/requests");
    return settle(data, response);
  });
}
