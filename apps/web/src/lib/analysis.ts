import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import { apiClient } from "./api";

/**
 * Analiz sayfalarının (genel bakış, lig, rakip) veri katmanı. Tüm sayılar API'den gelir; burada
 * hesap yapılmaz (formüller `kurgu_analytics.metrics` içinde).
 */

export type Season = Schemas["SeasonOut"];
export type TeamMetrics = Schemas["TeamMetricsOut"];
export type MetricValue = Schemas["MetricValueOut"];
export type Benchmark = Schemas["BenchmarkOut"];
export type Profile = Schemas["TeamProfileOut"];
export type Standings = Schemas["StandingsOut"];
export type Fixture = Schemas["FixtureOut"];
export type SetPiece = Schemas["SetPieceOut"];

/** API yanıtının durumu: veri, yetkisiz (403), bulunamadı (404) ya da hata. */
export type Loaded<T> =
  { status: "ok"; data: T } | { status: "forbidden" } | { status: "missing" } | { status: "error" };

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

export const getSeasons = cache((): Promise<Loaded<Season[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/seasons", {
      params: { query: { limit: 100 } },
    });
    return settle(data?.items, response);
  }),
);

/** Süper Lig sezonları yeniden eskiye; diğer yarışmalar (StatsBomb vb.) sonra. */
export function orderSeasons(seasons: Season[]): Season[] {
  return [...seasons].sort((a, b) => {
    const league = Number(b.competition.code === "TR-SL") - Number(a.competition.code === "TR-SL");
    return (
      league || b.code.localeCompare(a.code) || a.competition.name.localeCompare(b.competition.name)
    );
  });
}

/** `?season=` geçerliyse o sezon, değilse en güncel Süper Lig sezonu. */
export function pickSeason(seasons: Season[], requested?: string): Season | undefined {
  return seasons.find((s) => s.id === requested) ?? orderSeasons(seasons)[0];
}

/** Aynı yarışmanın bir önceki sezonu (genel bakışta "geçen sezon" kartı için). */
export function previousSeason(seasons: Season[], current: Season): Season | undefined {
  return orderSeasons(seasons).find(
    (s) => s.competition.id === current.competition.id && s.code < current.code,
  );
}

export const getTeamMetrics = cache(
  (seasonId: string): Promise<Loaded<Schemas["TeamMetricsPage"]>> =>
    guarded(async () => {
      const client = await apiClient();
      const { data, response } = await client.GET("/api/v1/seasons/{season_id}/team-metrics", {
        params: { path: { season_id: seasonId }, query: { limit: 200 } },
      });
      return settle(data, response);
    }),
);

export const getBenchmarks = cache((seasonId: string): Promise<Loaded<Schemas["BenchmarksOut"]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/seasons/{season_id}/benchmarks", {
      params: { path: { season_id: seasonId } },
    });
    return settle(data, response);
  }),
);

export const getStandings = cache((seasonId: string): Promise<Loaded<Standings>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/seasons/{season_id}/standings", {
      params: { path: { season_id: seasonId } },
    });
    return settle(data, response);
  }),
);

export const getProfile = cache((teamId: string, seasonId: string): Promise<Loaded<Profile>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/teams/{team_id}/profile", {
      params: { path: { team_id: teamId }, query: { season: seasonId } },
    });
    return settle(data, response);
  }),
);

export const getTeamSetPieces = cache(
  (teamId: string, seasonId: string): Promise<Loaded<SetPiece[]>> =>
    guarded(async () => {
      const client = await apiClient();
      const { data, response } = await client.GET("/api/v1/teams/{team_id}/set-pieces", {
        params: { path: { team_id: teamId }, query: { season: seasonId, limit: 50 } },
      });
      return settle(data?.items, response);
    }),
);

export const getFixtures = cache(
  (
    teamId: string,
    seasonId: string,
    status: "scheduled" | "finished",
    limit: number,
  ): Promise<Loaded<Fixture[]>> =>
    guarded(async () => {
      const client = await apiClient();
      const { data, response } = await client.GET("/api/v1/fixtures", {
        params: { query: { team: teamId, season: seasonId, status, limit } },
      });
      return settle(data?.items, response);
    }),
);
