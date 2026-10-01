"use server";

import type { Schemas } from "@kurgu/api-client";
import { revalidatePath } from "next/cache";
import { apiClient, apiFetch } from "./api";

/**
 * Video ve klip sunucu eylemleri (ADR-0005: token tarayıcıya verilmez). Dosyanın kendisi
 * tarayıcıdan doğrudan depoya, API'nin verdiği imzalı adreslere yüklenir (A-60).
 */

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function code(error: unknown, status: number): string {
  const type = (error as { type?: string } | undefined)?.type;
  return type?.split("/").pop() || `http-${status}`;
}

async function run<T>(
  call: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<ActionResult<T>> {
  try {
    const { data, error, response } = await call();
    if (response.ok) return { ok: true, data: data as T };
    return { ok: false, error: code(error, response.status) };
  } catch {
    return { ok: false, error: "network" };
  }
}

function refresh(assetId?: string) {
  revalidatePath("/video");
  if (assetId) revalidatePath(`/video/${assetId}`);
}

export async function startUpload(
  body: Schemas["UploadCreate"],
  idempotencyKey: string,
): Promise<ActionResult<Schemas["UploadOut"]>> {
  if (!UUID_RE.test(idempotencyKey)) return { ok: false, error: "invalid-key" };
  try {
    const response = await apiFetch("/api/v1/video/uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
    const json = (await response.json()) as unknown;
    if (!response.ok) return { ok: false, error: code(json, response.status) };
    return { ok: true, data: json as Schemas["UploadOut"] };
  } catch {
    return { ok: false, error: "network" };
  }
}

export async function completeUpload(
  assetId: string,
  etags: string[],
): Promise<ActionResult<Schemas["AssetOut"]>> {
  if (!UUID_RE.test(assetId)) return { ok: false, error: "invalid-id" };
  const client = await apiClient();
  const result = await run(() =>
    client.POST("/api/v1/video/assets/{asset_id}/complete", {
      params: { path: { asset_id: assetId } },
      body: { etags },
    }),
  );
  refresh(assetId);
  return result;
}

export async function updateVideo(
  assetId: string,
  patch: Schemas["AssetPatch"],
): Promise<ActionResult<Schemas["AssetOut"]>> {
  if (!UUID_RE.test(assetId)) return { ok: false, error: "invalid-id" };
  const client = await apiClient();
  const result = await run(() =>
    client.PATCH("/api/v1/video/assets/{asset_id}", {
      params: { path: { asset_id: assetId } },
      body: patch,
    }),
  );
  refresh(assetId);
  return result;
}

export async function deleteVideo(assetId: string): Promise<ActionResult<null>> {
  if (!UUID_RE.test(assetId)) return { ok: false, error: "invalid-id" };
  const client = await apiClient();
  const result = await run(() =>
    client.DELETE("/api/v1/video/assets/{asset_id}", {
      params: { path: { asset_id: assetId } },
    }),
  );
  refresh();
  return result.ok ? { ok: true, data: null } : result;
}

export async function createClip(
  body: Schemas["ClipCreate"],
): Promise<ActionResult<Schemas["ClipOut"]>> {
  const client = await apiClient();
  const result = await run(() => client.POST("/api/v1/clips", { body }));
  refresh(body.asset_id);
  revalidatePath("/routines", "layout");
  return result;
}

export async function updateClip(
  clipId: string,
  assetId: string,
  patch: Schemas["ClipPatch"],
): Promise<ActionResult<Schemas["ClipOut"]>> {
  if (!UUID_RE.test(clipId)) return { ok: false, error: "invalid-id" };
  const client = await apiClient();
  const result = await run(() =>
    client.PATCH("/api/v1/clips/{clip_id}", { params: { path: { clip_id: clipId } }, body: patch }),
  );
  refresh(assetId);
  revalidatePath("/routines", "layout");
  return result;
}

export async function deleteClip(clipId: string, assetId: string): Promise<ActionResult<null>> {
  if (!UUID_RE.test(clipId)) return { ok: false, error: "invalid-id" };
  const client = await apiClient();
  const result = await run(() =>
    client.DELETE("/api/v1/clips/{clip_id}", { params: { path: { clip_id: clipId } } }),
  );
  refresh(assetId);
  revalidatePath("/routines", "layout");
  return result.ok ? { ok: true, data: null } : result;
}
