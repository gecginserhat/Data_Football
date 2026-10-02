import { apiFetch } from "@/lib/api";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Veri sahibinin verisinin kopyası (KVKK m.11): API'den oturum sahibi adına alınır. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ playerId: string }> },
): Promise<Response> {
  const { playerId } = await params;
  if (!UUID_RE.test(playerId)) return new Response("Not found", { status: 404 });
  const upstream = await apiFetch(`/api/v1/squad/${playerId}/export`, { method: "GET" });
  const headers = new Headers({ "Cache-Control": "no-store" });
  for (const key of ["content-type", "content-disposition"]) {
    const value = upstream.headers.get(key);
    if (value) headers.set(key, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
