"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";

/**
 * Rapor, brifing ve LLM ayarı sunucu eylemleri (ADR-0012, ADR-0013). Erişim token'ı tarayıcıya
 * verilmez (ADR-0005); formlar buradan API'ye gider ve sayfaya geri döner.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TYPES = new Set(["opponent", "match_plan"]);

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

function field(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

function target(returnTo: string, fixtureId: string): string {
  return returnTo === "prep" ? `/prep/${fixtureId}` : "/reports";
}

export async function requestReport(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const type = field(form, "type");
  const base = target(field(form, "returnTo"), fixtureId);
  if (!UUID_RE.test(fixtureId) || !TYPES.has(type)) redirect(`${base}?error=invalid#reports`);
  let error: string | null = null;
  let id: string | null = null;
  try {
    const client = await apiClient();
    const {
      data,
      error: problem,
      response,
    } = await client.POST("/api/v1/reports", {
      body: { fixture_id: fixtureId, type: type as "opponent" | "match_plan" },
    });
    if (data) id = data.id;
    else error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/reports");
  revalidatePath(`/prep/${fixtureId}`);
  const query = error ? `?error=${encodeURIComponent(error)}` : `?report=${id}`;
  redirect(`${base}${query}#reports`);
}

export async function generateBriefing(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  let error: string | null = null;
  try {
    const client = await apiClient();
    const {
      data,
      error: problem,
      response,
    } = await client.POST("/api/v1/fixtures/{fixture_id}/briefing", {
      params: { path: { fixture_id: fixtureId } },
    });
    if (!data) error = problemCode(problem, response.status);
    else if (data.status !== "verified") error = `briefing-${data.reason ?? "unverified"}`;
  } catch {
    error = "network";
  }
  revalidatePath(`/prep/${fixtureId}`);
  redirect(`/prep/${fixtureId}${error ? `?briefing=${encodeURIComponent(error)}` : ""}#briefing`);
}

function bounded(raw: string, max: number): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return value <= max ? value : null;
}

export async function saveLlmSettings(form: FormData): Promise<void> {
  const requests = bounded(field(form, "monthly_requests"), 100_000);
  const tokens = bounded(field(form, "monthly_tokens"), 1_000_000_000);
  if (requests === null || tokens === null) redirect("/admin/llm?error=invalid");
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.PUT("/api/v1/admin/llm-settings", {
      body: {
        enabled: form.get("enabled") === "on",
        monthly_requests: requests,
        monthly_tokens: tokens,
      },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/admin/llm");
  redirect(error ? `/admin/llm?error=${encodeURIComponent(error)}` : "/admin/llm?saved=1");
}
