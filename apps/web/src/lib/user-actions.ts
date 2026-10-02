"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiClient } from "./api";

/** Kullanıcı yönetimi eylemleri; sonuç `/admin/users?saved=…|error=…` ile bildirilir. */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROLE_SET = new Set([
  "admin",
  "head_coach",
  "sp_coach",
  "analyst",
  "performance",
  "medical",
  "player",
  "viewer",
] as const);
type Role = typeof ROLE_SET extends Set<infer R> ? R : never;

function field(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function roles(form: FormData): Role[] {
  return form
    .getAll("roles")
    .map(String)
    .filter((r): r is Role => ROLE_SET.has(r as Role));
}

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

async function finish(error: string | null, saved: string, anchor: string): Promise<never> {
  revalidatePath("/admin/users");
  redirect(
    error
      ? `/admin/users?error=${encodeURIComponent(error)}#${anchor}`
      : `/admin/users?saved=${saved}#${anchor}`,
  );
}

async function call(run: () => Promise<{ error?: unknown; response: Response }>) {
  try {
    const { error, response } = await run();
    return response.ok ? null : problemCode(error, response.status);
  } catch {
    return "network";
  }
}

export async function saveRoles(form: FormData): Promise<void> {
  const userId = field(form, "userId");
  const chosen = roles(form);
  if (!UUID_RE.test(userId)) return finish("invalid", "", "members");
  if (chosen.length === 0) return finish("no-roles", "", "members");
  const error = await call(async () =>
    (await apiClient()).PUT("/api/v1/users/{user_id}/roles", {
      params: { path: { user_id: userId } },
      body: { roles: chosen },
    }),
  );
  return finish(error, "roles", "members");
}

export async function removeMember(form: FormData): Promise<void> {
  const userId = field(form, "userId");
  if (!UUID_RE.test(userId)) return finish("invalid", "", "members");
  const error = await call(async () =>
    (await apiClient()).DELETE("/api/v1/users/{user_id}", {
      params: { path: { user_id: userId } },
    }),
  );
  return finish(error, "removed", "members");
}

export async function createInvite(form: FormData): Promise<void> {
  const email = field(form, "email").toLowerCase();
  const chosen = roles(form);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return finish("email", "", "invite");
  if (chosen.length === 0) return finish("no-roles", "", "invite");
  const error = await call(async () =>
    (await apiClient()).POST("/api/v1/invites", { body: { email, roles: chosen } }),
  );
  return finish(error, "invited", "invite");
}

export async function revokeInvite(form: FormData): Promise<void> {
  const inviteId = field(form, "inviteId");
  if (!UUID_RE.test(inviteId)) return finish("invalid", "", "invites");
  const error = await call(async () =>
    (await apiClient()).DELETE("/api/v1/invites/{invite_id}", {
      params: { path: { invite_id: inviteId } },
    }),
  );
  return finish(error, "revoked", "invites");
}
