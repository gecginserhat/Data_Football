import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import { getTeamMetrics, type Fixture, type Loaded } from "./analysis";
import { apiClient, getMe, permissionSet } from "./api";

/** Canlı kayıt ve video ekranlarının sunucu tarafı verisi (SPEC §11, §13.1). */

export type Clip = Schemas["ClipOut"];
export type VideoAsset = Schemas["AssetOut"];
export type MatchSetPiece = Schemas["MatchSetPieceOut"];

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

export async function liveAccess(): Promise<{ tag: boolean; read: boolean }> {
  const me = await getMe();
  if (me.status !== "ok") return { tag: false, read: false };
  const perms = permissionSet(me.me);
  return { tag: perms.has("live_tagging_video"), read: perms.has("read_analysis") };
}

export const getFixture = cache((id: string): Promise<Loaded<Fixture>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}", {
      params: { path: { fixture_id: id } },
    });
    return settle(data, response);
  }),
);

/** Kulübün takımı (kiracı ayarı); takım metrikleri yanıtında gelir. */
export async function clubTeamId(seasonId: string): Promise<string | null> {
  const metrics = await getTeamMetrics(seasonId);
  return metrics.status === "ok" ? (metrics.data.club_team_id ?? null) : null;
}

export const getMatchSetPieces = cache((fixtureId: string): Promise<Loaded<MatchSetPiece[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}/set-pieces", {
      params: { path: { fixture_id: fixtureId } },
    });
    return settle(data, response);
  }),
);

export const listAssets = cache((matchId?: string): Promise<Loaded<VideoAsset[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/video/assets", {
      params: { query: { match_id: matchId } },
    });
    return settle(data, response);
  }),
);

export const getAsset = cache((id: string): Promise<Loaded<VideoAsset>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/video/assets/{asset_id}", {
      params: { path: { asset_id: id } },
    });
    return settle(data, response);
  }),
);

export const listClips = cache(
  (filter: {
    asset_id?: string;
    routine_id?: string;
    match_id?: string;
  }): Promise<Loaded<Clip[]>> =>
    guarded(async () => {
      const client = await apiClient();
      const { data, response } = await client.GET("/api/v1/clips", {
        params: { query: filter },
      });
      return settle(data, response);
    }),
);
