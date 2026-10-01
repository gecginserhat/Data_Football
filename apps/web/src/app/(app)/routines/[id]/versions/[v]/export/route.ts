import { apiFetch } from "@/lib/api";

/**
 * Rutin kartı indirme (A-42): tarayıcı token görmediği için API'ye sunucudan gidilir ve yanıt
 * olduğu gibi aktarılır.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PASS_HEADERS = ["content-type", "content-disposition", "content-length", "cache-control"];

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; v: string }> },
): Promise<Response> {
  const { id, v } = await params;
  const url = new URL(request.url);
  const format = url.searchParams.get("format") === "png" ? "png" : "pdf";
  const lang = url.searchParams.get("lang") === "en" ? "en" : "tr";
  if (!UUID_RE.test(id) || !/^[1-9][0-9]{0,5}$/.test(v)) {
    return new Response("Not found", { status: 404 });
  }
  let upstream: Response;
  try {
    upstream = await apiFetch(
      `/api/v1/routines/${id}/versions/${v}/export?format=${format}&lang=${lang}`,
      { method: "GET" },
    );
  } catch {
    return new Response("Bad gateway", { status: 502 });
  }
  const headers = new Headers();
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
