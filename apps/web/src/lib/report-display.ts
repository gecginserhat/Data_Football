/** Rapor ekranlarının saf yardımcıları (istemci ve sunucu ortak). */

export type ReportStatus = "queued" | "running" | "ready" | "failed";

export function isBusy(status: ReportStatus): boolean {
  return status === "queued" || status === "running";
}

/** `1840` → `1,8 sn`; bir dakikadan uzunsa `1 dk 05 sn`. */
export function formatDuration(ms: number | null | undefined, locale = "tr"): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 60_000) {
    const seconds = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(ms / 1000);
    return locale.startsWith("tr") ? `${seconds} sn` : `${seconds} s`;
  }
  const total = Math.round(ms / 1000);
  const min = Math.floor(total / 60);
  const sec = String(total % 60).padStart(2, "0");
  return locale.startsWith("tr") ? `${min} dk ${sec} sn` : `${min} min ${sec} s`;
}

/** `245760` → `240 KB`, `1572864` → `1,5 MB`. */
export function formatSize(bytes: number | null | undefined, locale = "tr"): string | null {
  if (bytes === null || bytes === undefined) return null;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  const mb = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(
    bytes / 1024 / 1024,
  );
  return `${mb} MB`;
}
