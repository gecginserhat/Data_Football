import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import type { Loaded } from "./analysis";
import { apiClient, getMe, permissionSet } from "./api";

/**
 * Maç hazırlığı ve kural setlerinin sunucu tarafı veri katmanı (SPEC §11 Hazırlık, Kurallar).
 * Öneriler her istekte API'de hesaplanır (A-50); burada hesap yapılmaz.
 */

export type Prep = Schemas["PrepOut"];
export type Recommendation = Schemas["RecommendationOut"];
export type Evidence = Schemas["EvidenceOut"];
export type Plan = Schemas["PlanOut"];
export type PlanItem = Schemas["PlanItemOut"];
export type MatchupRow = Schemas["MatchupRow"];
export type PrepFixture = Schemas["PrepFixtureOut"];
export type Overview = Schemas["OverviewRecsOut"];
export type RuleSet = Schemas["RuleSetOut"];
export type RuleSetVersion = Schemas["RuleSetVersionOut"];
export type DryRun = Schemas["DryRunOut"];
export type DryRunRule = Schemas["DryRunRule"];

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

export interface PrepAccess {
  read: boolean;
  decide: boolean;
  mark: boolean;
  rules: boolean;
}

/** Hazırlık izinleri (SPEC §12.1): okuma, öneri kararı, plan işaretleme, kural ayarları. */
export async function prepAccess(): Promise<PrepAccess> {
  const me = await getMe();
  if (me.status !== "ok") return { read: false, decide: false, mark: false, rules: false };
  const perms = permissionSet(me.me);
  return {
    read: perms.has("read_analysis"),
    decide: perms.has("decide_recommendations"),
    mark: perms.has("mark_plan_items"),
    rules: perms.has("rule_settings"),
  };
}

export const getPrep = cache((fixtureId: string): Promise<Loaded<Prep>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}/prep", {
      params: { path: { fixture_id: fixtureId } },
    });
    return settle(data, response);
  }),
);

export const getOverview = cache((limit = 5): Promise<Loaded<Overview>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/prep/overview", {
      params: { query: { limit } },
    });
    return settle(data, response);
  }),
);

export const getRuleSet = cache((): Promise<Loaded<RuleSet>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/rule-sets/current");
    return settle(data, response);
  }),
);

export const getRuleVersions = cache((): Promise<Loaded<RuleSetVersion[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/rule-sets/versions");
    return settle(data, response);
  }),
);
