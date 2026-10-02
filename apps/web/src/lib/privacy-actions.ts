"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function field(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

/** Dönüş sayfası: oyuncunun kendi sayfası ya da performans ekibinin oyuncu sayfası. */
function backTo(form: FormData, playerId: string): string {
  return field(form, "returnTo") === "player" && UUID_RE.test(playerId)
    ? `/performance/players/${playerId}`
    : "/me";
}

async function finish(back: string, error: string | null, saved: string): Promise<never> {
  revalidatePath(back);
  redirect(
    error
      ? `${back}?privacyError=${encodeURIComponent(error)}#privacy`
      : `${back}?privacySaved=${saved}#privacy`,
  );
}

export async function giveConsent(form: FormData): Promise<void> {
  const playerId = field(form, "playerId");
  const back = backTo(form, playerId);
  const method = field(form, "method") === "paper" ? "paper" : "self";
  const reference = field(form, "reference");
  if (!UUID_RE.test(playerId) || (method === "paper" && !reference)) {
    return finish(back, "invalid", "");
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST("/api/v1/squad/{player_id}/consent", {
      params: { path: { player_id: playerId } },
      body: {
        method,
        reference: method === "paper" ? reference : null,
        text_version: field(form, "textVersion"),
      },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  return finish(back, error, "consent");
}

export async function withdrawConsent(form: FormData): Promise<void> {
  const playerId = field(form, "playerId");
  const back = backTo(form, playerId);
  if (!UUID_RE.test(playerId)) return finish(back, "invalid", "");
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.DELETE("/api/v1/squad/{player_id}/consent", {
      params: { path: { player_id: playerId } },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  return finish(back, error, "withdrawn");
}

export async function requestErasure(form: FormData): Promise<void> {
  const playerId = field(form, "playerId");
  const back = backTo(form, playerId);
  if (!UUID_RE.test(playerId)) return finish(back, "invalid", "");
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST("/api/v1/privacy/requests", {
      body: { squad_player_id: playerId, kind: "erasure", reason: field(form, "reason") || null },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  return finish(back, error, "request");
}

export async function decideRequest(form: FormData): Promise<void> {
  const requestId = field(form, "requestId");
  const approve = field(form, "decision") === "approve";
  if (!UUID_RE.test(requestId)) redirect("/admin/privacy?error=invalid#requests");
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST(
      "/api/v1/privacy/requests/{request_id}/decision",
      {
        params: { path: { request_id: requestId } },
        body: { approve, note: field(form, "note") || null },
      },
    );
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/admin/privacy");
  redirect(
    error
      ? `/admin/privacy?error=${encodeURIComponent(error)}#requests`
      : `/admin/privacy?saved=${approve ? "approved" : "rejected"}#requests`,
  );
}

export async function updateRetention(form: FormData): Promise<void> {
  const days = (key: string) => Number(field(form, key));
  const body = {
    wellness_days: days("wellness_days"),
    loads_days: days("loads_days"),
    audit_days: days("audit_days"),
  };
  if (Object.values(body).some((v) => !Number.isInteger(v))) {
    redirect("/admin/privacy?error=invalid#retention");
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.PUT("/api/v1/privacy/retention", { body });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/admin/privacy");
  redirect(
    error
      ? `/admin/privacy?error=${encodeURIComponent(error)}#retention`
      : "/admin/privacy?saved=retention#retention",
  );
}
