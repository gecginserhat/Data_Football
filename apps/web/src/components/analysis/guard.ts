import "server-only";
import { getMe, permissionSet } from "@/lib/api";

/** Analiz sayfaları `read_analysis` izni ister (SPEC §12.1). */
export async function canReadAnalysis(): Promise<boolean> {
  const result = await getMe();
  return result.status === "ok" && permissionSet(result.me).has("read_analysis");
}
