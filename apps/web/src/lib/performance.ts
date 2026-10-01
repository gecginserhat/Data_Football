import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import type { Loaded } from "./analysis";
import { apiClient, getMe } from "./api";

/**
 * Yük, iyi oluş ve uyarıların sunucu tarafı veri katmanı (SPEC §8.2-8.3, A-83 … A-86).
 * sRPE, EWMA, z-skoru ve uyarılar API'de `kurgu_analytics.metrics.load` ile hesaplanır.
 */

export type LoadOverview = Schemas["OverviewOut"];
export type PlayerLoadRow = Schemas["PlayerLoadRow"];
export type LoadAlert = Schemas["AlertOut"];
export type PlayerLoad = Schemas["PlayerLoadOut"];
export type TrainingSession = Schemas["TrainingSessionOut"];

function settle<T>(data: T | undefined, response: Response): Loaded<T> {
  if (data !== undefined) return { status: "ok", data };
  if (response.status === 403) return { status: "forbidden" };
  if (response.status === 404 || response.status === 422) return { status: "missing" };
  return { status: "error" };
}

async function guarded<T>(run: () => Promise<Loaded<T>>): Promise<Loaded<T>> {
  try {
    return await run();
  } catch {
    return { status: "error" };
  }
}

/** `load_wellness` kapsamı: `all` tam, `summary` takım özeti, `own` yalnız kendi verisi. */
export async function loadScope(): Promise<"all" | "summary" | "own" | null> {
  const me = await getMe();
  if (me.status !== "ok") return null;
  return me.me.active_tenant?.permissions.load_wellness ?? null;
}

export const getLoadOverview = cache((): Promise<Loaded<LoadOverview>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/load/overview");
    return settle(data, response);
  }),
);

export const getPlayerLoad = cache((playerId: string): Promise<Loaded<PlayerLoad>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/players/{player_id}/load", {
      params: { path: { player_id: playerId } },
    });
    return settle(data, response);
  }),
);

/** Bugünün tarihi (Europe/Istanbul, YYYY-AA-GG). */
export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Istanbul" }).format(new Date());
}
