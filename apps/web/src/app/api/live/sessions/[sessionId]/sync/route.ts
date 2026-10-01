import { badRequest, forward, isUuid } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

/** Toplu, idempotent senkronizasyon (ADR-0004). Idempotency-Key olduğu gibi iletilir. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;
  if (!isUuid(sessionId)) return badRequest();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = request.headers.get("Idempotency-Key");
  if (key) headers["Idempotency-Key"] = key;
  return forward(`/api/v1/tagging-sessions/${sessionId}/sync`, {
    method: "POST",
    headers,
    body: await request.text(),
  });
}
