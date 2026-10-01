import { badRequest, isUuid } from "@/lib/api-proxy";
import { getReport } from "@/lib/reports";

export const dynamic = "force-dynamic";

/**
 * Hazır raporun dosyasına yönlendirir. İmzalı adres her tıklamada API'den yeniden alınır; sayfa
 * uzun süre açık kalsa da bağlantı geçerlidir (A-70).
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ reportId: string }> },
) {
  const { reportId } = await params;
  if (!isUuid(reportId)) return badRequest();
  const report = await getReport(reportId);
  if (report.status !== "ok") {
    const status = report.status === "forbidden" ? 403 : report.status === "missing" ? 404 : 502;
    return new Response(null, { status });
  }
  if (!report.data.download_url) return new Response(null, { status: 409 });
  return Response.redirect(report.data.download_url, 302);
}
