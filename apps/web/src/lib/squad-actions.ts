"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";

/**
 * Kadro, rakip hedefi, markaj ve rol ataması sunucu eylemleri (A-79 … A-82, A-87). Erişim
 * token'ı tarayıcıya verilmez (ADR-0005); formlar buradan API'ye gider ve sayfaya geri döner.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const POSITIONS = new Set(["GK", "DEF", "MID", "FWD"]);

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

function field(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

/** Boşsa `null`, sayı değilse `NaN` (sunucu doğrulaması reddeder). */
function optionalNumber(form: FormData, name: string, scale = 1): number | null {
  const raw = field(form, name).replace(",", ".");
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.round((value / scale) * 1000) / 1000 : Number.NaN;
}

function invalid(...values: (number | null)[]): boolean {
  return values.some((v) => v !== null && Number.isNaN(v));
}

function prepPath(fixtureId: string, query = "", hash = "marking"): string {
  return `/prep/${fixtureId}${query}#${hash}`;
}

// --- Kadro ---------------------------------------------------------------------------------------

export async function saveSquadPlayer(form: FormData): Promise<void> {
  const id = field(form, "id");
  const position = field(form, "position");
  const body = {
    name: field(form, "name"),
    shirt_number: optionalNumber(form, "shirt_number"),
    position: position as "GK" | "DEF" | "MID" | "FWD",
    height_cm: optionalNumber(form, "height_cm"),
    aerial_win_pct: optionalNumber(form, "aerial_win_pct", 100),
    jump_score: optionalNumber(form, "jump_score"),
    active: id ? form.get("active") === "on" : true,
  };
  if (
    (id && !UUID_RE.test(id)) ||
    !body.name ||
    !POSITIONS.has(position) ||
    invalid(body.shirt_number, body.height_cm, body.aerial_win_pct, body.jump_score)
  ) {
    redirect("/admin/squad?error=invalid");
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = id
      ? await client.PUT("/api/v1/squad/{player_id}", {
          params: { path: { player_id: id } },
          body,
        })
      : await client.POST("/api/v1/squad", { body });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/admin/squad");
  redirect(error ? `/admin/squad?error=${encodeURIComponent(error)}` : "/admin/squad?saved=1");
}

export async function linkAccount(form: FormData): Promise<void> {
  const playerId = field(form, "playerId");
  const userId = field(form, "userId");
  if (!UUID_RE.test(playerId) || (userId && !UUID_RE.test(userId))) {
    redirect("/admin/squad?error=invalid");
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.PUT("/api/v1/squad/{player_id}/account", {
      params: { path: { player_id: playerId } },
      body: { user_id: userId || null },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/admin/squad");
  redirect(error ? `/admin/squad?error=${encodeURIComponent(error)}` : "/admin/squad?saved=1");
}

// --- Rakip hedefleri -----------------------------------------------------------------------------

export async function addTarget(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const teamId = field(form, "teamId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  const body = {
    name: field(form, "name"),
    shirt_number: optionalNumber(form, "shirt_number"),
    height_cm: optionalNumber(form, "height_cm"),
    aerial_win_pct: optionalNumber(form, "aerial_win_pct", 100),
    sp_goals: optionalNumber(form, "sp_goals"),
    notes: field(form, "notes"),
  };
  if (
    !UUID_RE.test(teamId) ||
    !body.name ||
    invalid(body.shirt_number, body.height_cm, body.aerial_win_pct, body.sp_goals)
  ) {
    redirect(prepPath(fixtureId, "?marking=invalid"));
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST("/api/v1/teams/{team_id}/targets", {
      params: { path: { team_id: teamId } },
      body,
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath(`/prep/${fixtureId}`);
  redirect(prepPath(fixtureId, error ? `?marking=${encodeURIComponent(error)}` : ""));
}

export async function deleteTarget(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const targetId = field(form, "targetId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  if (!UUID_RE.test(targetId)) redirect(prepPath(fixtureId, "?marking=invalid"));
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.DELETE("/api/v1/targets/{target_id}", {
      params: { path: { target_id: targetId } },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath(`/prep/${fixtureId}`);
  redirect(prepPath(fixtureId, error ? `?marking=${encodeURIComponent(error)}` : ""));
}

// --- Markaj --------------------------------------------------------------------------------------

function zonalIds(form: FormData): string[] {
  return form
    .getAll("zonal")
    .map((v) => String(v))
    .filter((v) => UUID_RE.test(v));
}

/** Seçilen alan oyuncularıyla öneriyi yeniden hesaplatır (kaydetmez). */
export async function recomputeMarking(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  const zonal = zonalIds(form);
  redirect(prepPath(fixtureId, `?zonal=${encodeURIComponent(zonal.join(",")) || "none"}`));
}

export async function saveMarking(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  const base = Number(field(form, "baseVersion"));
  const assignments: { target_id: string; marker_id: string | null }[] = [];
  for (const [key, value] of form.entries()) {
    if (!key.startsWith("target:")) continue;
    const targetId = key.slice("target:".length);
    const markerId = String(value);
    if (!UUID_RE.test(targetId) || (markerId && !UUID_RE.test(markerId))) {
      redirect(prepPath(fixtureId, "?marking=invalid"));
    }
    assignments.push({ target_id: targetId, marker_id: markerId || null });
  }
  if (!Number.isInteger(base) || base < 0) redirect(prepPath(fixtureId, "?marking=invalid"));
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.PUT("/api/v1/fixtures/{fixture_id}/marking", {
      params: { path: { fixture_id: fixtureId } },
      body: {
        base_version: base,
        assignments,
        zonal: zonalIds(form),
        note: field(form, "note") || null,
      },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath(`/prep/${fixtureId}`);
  revalidatePath("/me");
  redirect(prepPath(fixtureId, `?marking=${error ? encodeURIComponent(error) : "saved"}`));
}

// --- Rol atamaları -------------------------------------------------------------------------------

export async function saveAssignments(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const routineId = field(form, "routineId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  const slots: { diagram_player_id: string; squad_player_id: string | null }[] = [];
  for (const [key, value] of form.entries()) {
    if (!key.startsWith("slot:")) continue;
    const player = String(value);
    if (player && !UUID_RE.test(player)) {
      redirect(prepPath(fixtureId, "?assign=invalid", "assignments"));
    }
    slots.push({ diagram_player_id: key.slice("slot:".length), squad_player_id: player || null });
  }
  if (!UUID_RE.test(routineId)) redirect(prepPath(fixtureId, "?assign=invalid", "assignments"));
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.PUT(
      "/api/v1/fixtures/{fixture_id}/assignments",
      {
        params: { path: { fixture_id: fixtureId } },
        body: { routine_id: routineId, slots },
      },
    );
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath(`/prep/${fixtureId}`);
  revalidatePath("/me");
  redirect(
    prepPath(fixtureId, `?assign=${error ? encodeURIComponent(error) : "saved"}`, "assignments"),
  );
}

/** Atama listesine kabul edilmiş öneri ya da plan maddesi dışında bir rutin ekler (kaydetmez). */
export async function pickRoutine(form: FormData): Promise<void> {
  const fixtureId = field(form, "fixtureId");
  const routineId = field(form, "routineId");
  if (!UUID_RE.test(fixtureId)) redirect("/prep");
  redirect(
    prepPath(
      fixtureId,
      UUID_RE.test(routineId) ? `?routine=${routineId}` : "?assign=invalid",
      "assignments",
    ),
  );
}
