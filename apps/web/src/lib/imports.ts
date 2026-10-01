"use server";

import { redirect } from "next/navigation";
import { apiFetch } from "./api";

/**
 * İçe aktarım sihirbazının sunucu eylemleri. Her eylem sonucu sayfaya yönlendirir; hata kodu
 * `?error=` parametresinde taşınır. Sayfalar çerez okuduğu için her istekte yeniden çizilir;
 * önbellek temizliği gerekmez.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BASE = "/admin/imports";

async function problemCode(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { type?: string };
    return body.type?.split("/").pop() || `http-${response.status}`;
  } catch {
    return `http-${response.status}`;
  }
}

function withError(path: string, code: string): string {
  return `${path}?error=${encodeURIComponent(code)}`;
}

export async function uploadImport(formData: FormData): Promise<void> {
  const file = formData.get("file");
  const kind = String(formData.get("kind") ?? "");
  const seasonId = String(formData.get("seasonId") ?? "");
  const key = String(formData.get("idempotencyKey") ?? "");
  if (!(file instanceof File) || file.size === 0) redirect(withError(BASE, "no-file"));
  if (!UUID_RE.test(seasonId)) redirect(withError(BASE, "unknown-season"));

  const body = new FormData();
  body.set("file", file, file.name);
  body.set("kind", kind);
  body.set("season_id", seasonId);
  let target: string;
  try {
    const response = await apiFetch("/api/v1/imports", {
      method: "POST",
      body,
      headers: { "Idempotency-Key": key },
    });
    if (!response.ok) {
      target = withError(BASE, await problemCode(response));
    } else {
      const created = (await response.json()) as { id: string };
      target = `${BASE}/${created.id}`;
    }
  } catch {
    target = withError(BASE, "network");
  }
  redirect(target);
}

export async function saveMapping(formData: FormData): Promise<void> {
  const id = String(formData.get("importId") ?? "");
  if (!UUID_RE.test(id)) redirect(BASE);
  const columns: Record<string, string | null> = {};
  const teams: Record<string, string | null> = {};
  for (const [name, value] of formData.entries()) {
    const text = String(value);
    const col = /^colname\.(\d+)$/.exec(name);
    if (col) columns[text] = String(formData.get(`col.${col[1]}`) ?? "") || null;
    const team = /^teamname\.(\d+)$/.exec(name);
    if (team) {
      // Yalnızca değiştirilen takımlar gönderilir; dokunulmayan otomatik eşleşmeler öyle kalır.
      const chosen = String(formData.get(`team.${team[1]}`) ?? "");
      const current = String(formData.get(`teamcurrent.${team[1]}`) ?? "");
      if (chosen !== current) teams[text] = chosen || null;
    }
  }
  const path = `${BASE}/${id}`;
  let target = `${path}?saved=1`;
  try {
    const response = await apiFetch(`/api/v1/imports/${id}/mapping`, {
      method: "PUT",
      body: JSON.stringify({ columns, teams }),
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) target = withError(path, await problemCode(response));
  } catch {
    target = withError(path, "network");
  }
  redirect(target);
}

export async function commitImport(formData: FormData): Promise<void> {
  const id = String(formData.get("importId") ?? "");
  if (!UUID_RE.test(id)) redirect(BASE);
  const path = `${BASE}/${id}`;
  let target = path;
  try {
    const response = await apiFetch(`/api/v1/imports/${id}/commit`, { method: "POST" });
    if (!response.ok) target = withError(path, await problemCode(response));
  } catch {
    target = withError(path, "network");
  }
  redirect(target);
}
