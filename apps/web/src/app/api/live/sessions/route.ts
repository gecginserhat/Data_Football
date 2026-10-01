import { forward } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

/** Maçın kayıt oturumunu açar ya da var olanı döner (A-56). */
export async function POST(request: Request) {
  return forward("/api/v1/tagging-sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
