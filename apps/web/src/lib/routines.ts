import "server-only";
import type { Schemas } from "@kurgu/api-client";
import type { Diagram } from "@kurgu/pitch";
import { cache } from "react";
import type { Loaded } from "./analysis";
import { apiClient, getMe, permissionSet } from "./api";

/**
 * Rutin kütüphanesinin sunucu tarafı veri katmanı (SPEC §11 Rutinler). Yazma işlemleri
 * `routine-actions.ts` içindeki sunucu eylemlerinde.
 */

export type Template = Schemas["TemplateOut"];
export type RoutineSummary = Schemas["RoutineSummary"];
export type Routine = Schemas["RoutineOut"];
export type RoutineVersion = Schemas["VersionOut"];
export type VersionSummary = Schemas["VersionSummary"];
export type RoutineStats = Schemas["RoutineStatsOut"];
export type SpType = Routine["sp_type"];

/** API diyagramını (varsayılanlı alanlar isteğe bağlı) editörün tam tipine çevirir. */
export function toDiagram(d: Schemas["Diagram"]): Diagram {
  return {
    schema: 1,
    players: (d.players ?? []).map((p) => ({
      ...p,
      number: p.number ?? null,
      label: p.label ?? null,
    })),
    lines: (d.lines ?? []).map((l) => ({
      ...l,
      curve: l.curve ?? 0,
      player_id: l.player_id ?? null,
    })),
    zones: (d.zones ?? []).map((z) => ({ ...z, label: z.label ?? null })),
    ball: d.ball ?? null,
    frames: (d.frames ?? []).map((f) => ({
      ...f,
      positions: f.positions ?? {},
      ball: f.ball ?? null,
    })),
  };
}

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

/** Rutin izinleri: okuma (`read_analysis`) ve düzenleme (`edit_routines`), SPEC §12.1. */
export async function routineAccess(): Promise<{ read: boolean; edit: boolean }> {
  const me = await getMe();
  if (me.status !== "ok") return { read: false, edit: false };
  const perms = permissionSet(me.me);
  return {
    read: perms.has("read_analysis") || perms.has("edit_routines"),
    edit: perms.has("edit_routines"),
  };
}

export const getTemplates = cache((): Promise<Loaded<Template[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/routine-templates");
    return settle(data, response);
  }),
);

export const listRoutines = cache(
  (type: SpType | undefined, archived: boolean): Promise<Loaded<RoutineSummary[]>> =>
    guarded(async () => {
      const client = await apiClient();
      const { data, response } = await client.GET("/api/v1/routines", {
        params: { query: { type, archived, limit: 200 } },
      });
      return settle(data?.items, response);
    }),
);

export const getRoutine = cache((id: string): Promise<Loaded<Routine>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/routines/{routine_id}", {
      params: { path: { routine_id: id } },
    });
    return settle(data, response);
  }),
);

export const getVersions = cache((id: string): Promise<Loaded<VersionSummary[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/routines/{routine_id}/versions", {
      params: { path: { routine_id: id } },
    });
    return settle(data, response);
  }),
);

export const getVersion = cache((id: string, version: number): Promise<Loaded<RoutineVersion>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET(
      "/api/v1/routines/{routine_id}/versions/{version}",
      { params: { path: { routine_id: id, version } } },
    );
    return settle(data, response);
  }),
);
