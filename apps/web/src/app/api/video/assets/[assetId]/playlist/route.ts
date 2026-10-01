import { badRequest, forward, isUuid } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

/** HLS oynatma listesi; parça adresleri API'de kısa ömürlü imzalı adreslere çevrilir (A-61). */
export async function GET(_request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  if (!isUuid(assetId)) return badRequest();
  return forward(`/api/v1/video/assets/${assetId}/playlist`, { method: "GET" });
}
