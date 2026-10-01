"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";

/** Seans ve iyi oluş girişi sunucu eylemleri (SPEC §8.2, A-83). */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MD_CODES = ["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"] as const;
type MdCode = (typeof MD_CODES)[number];

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

function field(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

function count(form: FormData, name: string): number {
  const raw = field(form, name);
  return raw ? Number(raw) : 0;
}

export async function createSession(form: FormData): Promise<void> {
  const date = field(form, "date");
  const md = field(form, "md_code");
  const title = field(form, "title");
  const loads = form
    .getAll("player")
    .map(String)
    .filter((id) => UUID_RE.test(id))
    .map((id) => ({
      squad_player_id: id,
      rpe: Number(field(form, `rpe:${id}`).replace(",", ".")),
      minutes: Number(field(form, `minutes:${id}`)),
      headers: count(form, `headers:${id}`),
      jumps: count(form, `jumps:${id}`),
    }));
  const numbers = loads.flatMap((l) => [l.rpe, l.minutes, l.headers, l.jumps]);
  if (
    !DATE_RE.test(date) ||
    !title ||
    loads.length === 0 ||
    numbers.some((n) => !Number.isFinite(n)) ||
    (md && !MD_CODES.includes(md as MdCode))
  ) {
    redirect("/performance?error=invalid#session");
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST("/api/v1/sessions", {
      body: { date, title, md_code: (md || null) as MdCode | null, loads },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath("/performance");
  redirect(
    error
      ? `/performance?error=${encodeURIComponent(error)}#session`
      : "/performance?saved=session",
  );
}

export async function saveWellness(form: FormData): Promise<void> {
  const playerId = field(form, "playerId");
  const date = field(form, "date");
  const returnTo = field(form, "returnTo");
  const back =
    returnTo === "me"
      ? "/me"
      : returnTo === "player" && UUID_RE.test(playerId)
        ? `/performance/players/${playerId}`
        : "/performance";
  const items = ["sleep", "stress", "fatigue", "soreness"] as const;
  const scores = Object.fromEntries(items.map((k) => [k, Number(field(form, k))])) as Record<
    (typeof items)[number],
    number
  >;
  if (
    !UUID_RE.test(playerId) ||
    !DATE_RE.test(date) ||
    items.some((k) => !Number.isInteger(scores[k]) || scores[k] < 1 || scores[k] > 7)
  ) {
    redirect(`${back}?error=invalid#wellness`);
  }
  let error: string | null = null;
  try {
    const client = await apiClient();
    const { error: problem, response } = await client.POST("/api/v1/wellness", {
      body: { squad_player_id: playerId, date, ...scores },
    });
    if (!response.ok) error = problemCode(problem, response.status);
  } catch {
    error = "network";
  }
  revalidatePath(back);
  redirect(
    error
      ? `${back}?error=${encodeURIComponent(error)}#wellness`
      : `${back}?saved=wellness#wellness`,
  );
}
