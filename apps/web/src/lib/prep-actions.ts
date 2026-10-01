"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";
import { applyEdits, editsFromForm, type RuleJson } from "./rules";
import type { DryRunRule } from "./prep";

/**
 * Maç hazırlığı ve kural setinin sunucu eylemleri. Erişim token'ı tarayıcıya verilmez (ADR-0005);
 * formlar buradan API'ye gider ve sayfaya geri döner.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DECISIONS = new Set(["accepted", "rejected", "suggested"]);
const TEMPLATES = new Set(["standard", "congested"]);
const MD_CODES = new Set(["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]);
type MdCode = "MD-4" | "MD-3" | "MD-2" | "MD-1" | "MD" | "MD+1";

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

function field(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

function uuidOrNull(raw: string): string | null {
  return UUID_RE.test(raw) ? raw : null;
}

/** Hazırlık sayfasına döner; hata varsa `?error=` ile, yoksa ilgili bölüme. */
function back(fixtureId: string, error: string | null, anchor: string): never {
  revalidatePath(`/prep/${fixtureId}`);
  revalidatePath("/prep");
  revalidatePath("/");
  redirect(`/prep/${fixtureId}${error ? `?error=${encodeURIComponent(error)}` : ""}#${anchor}`);
}

async function call(
  run: () => Promise<{ error?: unknown; response: Response }>,
): Promise<string | null> {
  try {
    const { error, response } = await run();
    return response.ok ? null : problemCode(error, response.status);
  } catch {
    return "network";
  }
}

export async function decideRecommendation(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const recId = field(form, "recommendationId");
  const decision = field(form, "decision");
  if (!uuidOrNull(fixtureId)) redirect("/prep");
  if (!uuidOrNull(recId) || !DECISIONS.has(decision)) back(fixtureId, "invalid", "recommendations");
  const reason = field(form, "reason").slice(0, 1000) || null;
  if (decision === "rejected" && !reason) back(fixtureId, "reason-required", `rec-${recId}`);
  const client = await apiClient();
  const error = await call(() =>
    client.POST("/api/v1/recommendations/{recommendation_id}/decision", {
      params: { path: { recommendation_id: recId } },
      body: {
        fixture_id: fixtureId,
        decision: decision as "accepted" | "rejected" | "suggested",
        reason,
      },
    }),
  );
  back(fixtureId, error, `rec-${recId}`);
}

export async function createPlan(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const template = field(form, "template");
  if (!uuidOrNull(fixtureId)) redirect("/prep");
  if (!TEMPLATES.has(template)) back(fixtureId, "invalid", "plan");
  const client = await apiClient();
  const error = await call(() =>
    client.POST("/api/v1/fixtures/{fixture_id}/plan", {
      params: { path: { fixture_id: fixtureId } },
      body: { template: template as "standard" | "congested" },
    }),
  );
  back(fixtureId, error, "plan");
}

export async function addPlanItem(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const md = field(form, "mdCode");
  const title = field(form, "title");
  if (!uuidOrNull(fixtureId)) redirect("/prep");
  if (!MD_CODES.has(md) || !title || title.length > 200) back(fixtureId, "invalid", "plan");
  const client = await apiClient();
  const error = await call(() =>
    client.POST("/api/v1/fixtures/{fixture_id}/plan/items", {
      params: { path: { fixture_id: fixtureId } },
      body: {
        md_code: md as MdCode,
        title,
        detail: field(form, "detail").slice(0, 2000),
        assignee_id: uuidOrNull(field(form, "assigneeId")),
        routine_id: uuidOrNull(field(form, "routineId")),
      },
    }),
  );
  back(fixtureId, error, "plan");
}

/** Tamamlandı işareti ya da sorumlu değişikliği (formda hangisi varsa). */
export async function updatePlanItem(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const itemId = field(form, "itemId");
  if (!uuidOrNull(fixtureId)) redirect("/prep");
  if (!uuidOrNull(itemId)) back(fixtureId, "invalid", "plan");
  const body: { status?: "todo" | "done"; assignee_id?: string | null } = {};
  const status = field(form, "status");
  if (status === "todo" || status === "done") body.status = status;
  if (form.has("assigneeId")) body.assignee_id = uuidOrNull(field(form, "assigneeId"));
  const client = await apiClient();
  const error = await call(() =>
    client.PATCH("/api/v1/plan-items/{item_id}", {
      params: { path: { item_id: itemId } },
      body,
    }),
  );
  back(fixtureId, error, `item-${itemId}`);
}

export async function deletePlanItem(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const itemId = field(form, "itemId");
  if (!uuidOrNull(fixtureId)) redirect("/prep");
  if (!uuidOrNull(itemId)) back(fixtureId, "invalid", "plan");
  const client = await apiClient();
  const error = await call(() =>
    client.DELETE("/api/v1/plan-items/{item_id}", { params: { path: { item_id: itemId } } }),
  );
  back(fixtureId, error, "plan");
}

// --- Kural seti ---------------------------------------------------------------------------------

export type RulesState =
  | { status: "idle" }
  | { status: "preview"; results: DryRunRule[]; fixtureLabel: string }
  | { status: "published"; version: number }
  | { status: "unchanged" }
  | { status: "conflict"; currentVersion: number | null }
  | { status: "error"; code: string; details: string[] };

function problemDetails(error: unknown): string[] {
  const errors = (error as { errors?: unknown } | undefined)?.errors;
  if (!Array.isArray(errors)) return [];
  return errors.slice(0, 10).map((e) => (typeof e === "string" ? e : JSON.stringify(e)));
}

/**
 * Kural düzenleyicisinin tek eylemi: `intent=preview` taslağı seçili maçta dener (kaydetmez),
 * `intent=publish` yeni kulüp sürümü yayımlar (A-51).
 */
export async function ruleSetAction(_prev: RulesState, form: FormData): Promise<RulesState> {
  let base: RuleJson[];
  try {
    base = JSON.parse(String(form.get("rules") ?? "[]")) as RuleJson[];
  } catch {
    return { status: "error", code: "invalid-rules", details: [] };
  }
  const rules = applyEdits(base, editsFromForm(form, base));
  const intent = field(form, "intent");
  try {
    const client = await apiClient();
    if (intent === "preview") {
      const fixtureId = field(form, "fixtureId");
      if (!uuidOrNull(fixtureId)) return { status: "error", code: "fixture-required", details: [] };
      const { data, error, response } = await client.POST("/api/v1/rule-sets/dry-run", {
        body: { fixture_id: fixtureId, rules },
      });
      if (!data) {
        return {
          status: "error",
          code: problemCode(error, response.status),
          details: problemDetails(error),
        };
      }
      const f = data.fixture;
      return {
        status: "preview",
        results: data.results,
        fixtureLabel: `${f.home.code} – ${f.away.code}`,
      };
    }
    const baseVersion = Number(field(form, "baseVersion"));
    const { data, error, response } = await client.PUT("/api/v1/rule-sets/current", {
      body: {
        base_version: Number.isInteger(baseVersion) ? baseVersion : 0,
        rules,
        message: field(form, "message").slice(0, 200) || null,
      },
    });
    if (response.status === 409) {
      const current = (error as { current_version?: number } | undefined)?.current_version;
      return { status: "conflict", currentVersion: current ?? null };
    }
    if (!data) {
      return {
        status: "error",
        code: problemCode(error, response.status),
        details: problemDetails(error),
      };
    }
    revalidatePath("/admin/rules");
    revalidatePath("/prep", "layout");
    revalidatePath("/");
    return data.version === baseVersion
      ? { status: "unchanged" }
      : { status: "published", version: data.version };
  } catch {
    return { status: "error", code: "network", details: [] };
  }
}
