"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { apiClient } from "./api";
import type { EditorDoc } from "./routine-editor";
import { toPayload } from "./routine-editor";

/**
 * Rutin kütüphanesinin sunucu eylemleri. Erişim token'ı tarayıcıya verilmediği için editör
 * kaydı da sunucu eyleminden geçer (ADR-0005).
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TEMPLATE_RE = /^[a-z0-9-]{1,64}$/;
const SP_TYPES = new Set(["corner", "free_kick", "throw_in"]);

function problemCode(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

export async function addTemplate(formData: FormData): Promise<void> {
  const templateId = String(formData.get("templateId") ?? "");
  if (!TEMPLATE_RE.test(templateId)) redirect("/routines?tab=templates&error=not-found");
  let target: string;
  try {
    const client = await apiClient();
    const { data, error, response } = await client.POST(
      "/api/v1/routines/from-template/{template_id}",
      { params: { path: { template_id: templateId } } },
    );
    target = data
      ? `/routines/${data.id}?created=1`
      : `/routines?tab=templates&error=${problemCode(error, response.status)}`;
  } catch {
    target = "/routines?tab=templates&error=network";
  }
  revalidatePath("/routines");
  redirect(target);
}

export async function createRoutine(formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const spType = String(formData.get("spType") ?? "");
  const sideRaw = String(formData.get("side") ?? "");
  if (!name || name.length > 120) redirect("/routines?error=name");
  if (!SP_TYPES.has(spType)) redirect("/routines?error=type");
  const side = sideRaw === "left" || sideRaw === "right" ? sideRaw : null;
  let target: string;
  try {
    const client = await apiClient();
    const { data, error, response } = await client.POST("/api/v1/routines", {
      body: {
        name,
        sp_type: spType as "corner" | "free_kick" | "throw_in",
        side,
        is_defensive: formData.get("defensive") === "on",
        notes: "",
        when_to_use: "",
      },
    });
    target = data
      ? `/routines/${data.id}`
      : `/routines?error=${problemCode(error, response.status)}`;
  } catch {
    target = "/routines?error=network";
  }
  revalidatePath("/routines");
  redirect(target);
}

export type SaveResult =
  | { status: "ok"; version: number }
  | { status: "conflict"; currentVersion: number | null }
  | { status: "error"; code: string };

/** Editör kaydı: yeni sürüm açar. Eşzamanlı değişiklikte `conflict` döner (A-41). */
export async function saveRoutine(
  id: string,
  doc: EditorDoc,
  baseVersion: number,
  message: string | null,
): Promise<SaveResult> {
  if (!UUID_RE.test(id)) return { status: "error", code: "not-found" };
  try {
    const client = await apiClient();
    const { data, error, response } = await client.PUT("/api/v1/routines/{routine_id}", {
      params: { path: { routine_id: id } },
      body: toPayload(doc, baseVersion, message),
    });
    if (data) {
      revalidatePath(`/routines/${id}`);
      revalidatePath("/routines");
      return { status: "ok", version: data.current_version };
    }
    const code = problemCode(error, response.status);
    if (code === "version-conflict") {
      const current = (error as { current_version?: number } | undefined)?.current_version;
      return { status: "conflict", currentVersion: current ?? null };
    }
    return { status: "error", code };
  } catch {
    return { status: "error", code: "network" };
  }
}

/** Eski bir sürüme dönmek: o sürümün içeriği yeni sürüm olarak kaydedilir (A-41). */
export async function restoreVersion(formData: FormData): Promise<void> {
  const id = String(formData.get("routineId") ?? "");
  const version = Number(formData.get("version"));
  const base = Number(formData.get("baseVersion"));
  const message = String(formData.get("message") ?? "");
  if (!UUID_RE.test(id) || !Number.isInteger(version) || !Number.isInteger(base)) {
    redirect("/routines");
  }
  let target = `/routines/${id}`;
  try {
    const client = await apiClient();
    const old = await client.GET("/api/v1/routines/{routine_id}/versions/{version}", {
      params: { path: { routine_id: id, version } },
    });
    if (!old.data) {
      target = `/routines/${id}?error=not-found`;
    } else {
      const { data, error, response } = await client.PUT("/api/v1/routines/{routine_id}", {
        params: { path: { routine_id: id } },
        body: {
          base_version: base,
          name: old.data.name,
          side: old.data.side,
          notes: old.data.notes,
          when_to_use: old.data.when_to_use,
          diagram: old.data.diagram,
          message: message || null,
        },
      });
      target = data
        ? `/routines/${id}?restored=${data.current_version}`
        : `/routines/${id}?error=${problemCode(error, response.status)}`;
    }
  } catch {
    target = `/routines/${id}?error=network`;
  }
  revalidatePath(`/routines/${id}`);
  redirect(target);
}

export async function setArchived(formData: FormData): Promise<void> {
  const id = String(formData.get("routineId") ?? "");
  const archived = formData.get("archived") === "true";
  if (!UUID_RE.test(id)) redirect("/routines");
  let target = archived ? "/routines?archived=1" : `/routines/${id}`;
  try {
    const client = await apiClient();
    const { error, response } = await client.PATCH("/api/v1/routines/{routine_id}", {
      params: { path: { routine_id: id } },
      body: { archived },
    });
    if (error) target = `/routines/${id}?error=${problemCode(error, response.status)}`;
  } catch {
    target = `/routines/${id}?error=network`;
  }
  revalidatePath("/routines");
  revalidatePath(`/routines/${id}`);
  redirect(target);
}
