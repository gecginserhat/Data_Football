import "server-only";
import type { Schemas } from "@kurgu/api-client";
import type { Loaded } from "./analysis";
import { apiClient } from "./api";

/** Kullanıcı yönetimi ve denetim kaydı veri katmanı (SPEC §12.1, A-100). */

export type Member = Schemas["MemberOut"];
export type Invite = Schemas["InviteOut"];
export type AuditPage = Schemas["AuditPageOut"];
export type Role = Member["roles"][number];

export const ROLES: readonly Role[] = [
  "admin",
  "head_coach",
  "sp_coach",
  "analyst",
  "performance",
  "medical",
  "player",
  "viewer",
];

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

export function listMembers(): Promise<Loaded<Member[]>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/users");
    return settle(data, response);
  });
}

export function listInvites(): Promise<Loaded<Invite[]>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/invites");
    return settle(data, response);
  });
}

export function listAudit(before?: number, action?: string): Promise<Loaded<AuditPage>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/audit", {
      params: { query: { before, action } },
    });
    return settle(data, response);
  });
}
