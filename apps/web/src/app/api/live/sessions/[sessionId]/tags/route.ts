import { badRequest, forward, isUuid } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

/** Diğer cihazların değişiklikleri: `since` sırasından sonrası (A-57). */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;
  const since = Number(new URL(request.url).searchParams.get("since") ?? "0");
  if (!isUuid(sessionId) || !Number.isSafeInteger(since) || since < 0) return badRequest();
  return forward(`/api/v1/tagging-sessions/${sessionId}/tags?since=${since}`, { method: "GET" });
}
