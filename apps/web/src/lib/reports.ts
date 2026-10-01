import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import type { Loaded } from "./analysis";
import { apiClient, getMe, permissionSet } from "./api";

/**
 * Raporlar, brifing ve LLM ayarlarının sunucu tarafı veri katmanı (SPEC §14, §15; ADR-0012/0013).
 * PDF'ler worker'da üretilir; burada yalnız durum okunur.
 */

export type Report = Schemas["ReportOut"];
export type Briefing = Schemas["BriefingOut"];
export type LlmSettings = Schemas["LlmSettingsOut"];

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

export interface ReportsAccess {
  read: boolean;
  /** Brifing üretme (A-76: hazırlık içeriği yazan roller). */
  brief: boolean;
  admin: boolean;
}

export async function reportsAccess(): Promise<ReportsAccess> {
  const me = await getMe();
  if (me.status !== "ok") return { read: false, brief: false, admin: false };
  const perms = permissionSet(me.me);
  return {
    read: perms.has("read_analysis"),
    brief: perms.has("edit_routines"),
    admin: perms.has("user_admin_audit"),
  };
}

export const listReports = cache((fixtureId?: string): Promise<Loaded<Report[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/reports", {
      params: { query: fixtureId ? { fixture_id: fixtureId } : {} },
    });
    return settle(data, response);
  }),
);

export async function getReport(reportId: string): Promise<Loaded<Report>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/reports/{report_id}", {
      params: { path: { report_id: reportId } },
    });
    return settle(data, response);
  });
}

export const getBriefing = cache((fixtureId: string): Promise<Loaded<Briefing>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}/briefing", {
      params: { path: { fixture_id: fixtureId } },
    });
    return settle(data, response);
  }),
);

export async function getLlmSettings(): Promise<Loaded<LlmSettings>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/admin/llm-settings");
    return settle(data, response);
  });
}
