import { cn, EmptyState } from "@kurgu/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { StatusPoller } from "@/components/video/AssetControls";
import { formatDuration, formatSize, isBusy } from "@/lib/report-display";
import { requestReport } from "@/lib/report-actions";
import type { Report } from "@/lib/reports";
import { PendingButton } from "./PendingButton";

export interface FixtureOption {
  id: string;
  label: string;
}

/** Rakip raporu ve maç planı PDF isteği (SPEC §14). Fikstür sabit ya da listeden seçilir. */
export function RequestReport({
  fixtureId,
  fixtures,
  returnTo,
}: {
  fixtureId?: string;
  fixtures?: FixtureOption[];
  returnTo: "prep" | "reports";
}) {
  const t = useTranslations("reports");
  return (
    <form action={requestReport} className="flex flex-wrap items-end gap-2">
      {fixtures ? (
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          {t("fixture")}
          <select
            name="fixtureId"
            defaultValue={fixtureId}
            className={inputCls}
            data-testid="report-fixture"
          >
            {fixtures.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <input type="hidden" name="fixtureId" value={fixtureId} />
      )}
      <input type="hidden" name="returnTo" value={returnTo} />
      <PendingButton
        name="type"
        value="opponent"
        className={btnPrimary}
        pendingLabel={t("requesting")}
        testId="request-opponent"
      >
        {t("request.opponent")}
      </PendingButton>
      <PendingButton
        name="type"
        value="match_plan"
        className={btn}
        pendingLabel={t("requesting")}
        testId="request-match_plan"
      >
        {t("request.match_plan")}
      </PendingButton>
    </form>
  );
}

function Row({ report, highlight }: { report: Report; highlight: boolean }) {
  const t = useTranslations("reports");
  const format = useFormatter();
  const locale = useLocale();
  const f = report.fixture;
  const busy = isBusy(report.status);
  const asOf = report.data_as_of as { season?: string; week?: number | null } | null;
  const meta = [
    report.pages ? t("pages", { count: report.pages }) : null,
    formatSize(report.size_bytes, locale),
    report.duration_ms != null
      ? t("duration", { value: formatDuration(report.duration_ms, locale) ?? "" })
      : null,
  ].filter(Boolean);
  return (
    <li
      id={`report-${report.id}`}
      data-testid="report"
      data-status={report.status}
      data-type={report.type}
      className={cn(
        "flex scroll-mt-20 flex-col gap-2 rounded-lg border bg-surface p-3",
        highlight ? "border-pri" : "border-line",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium">{t(`types.${report.type}`)}</span>
        <span className="text-sm text-ink-2 tabular-nums">
          {f.home_code}–{f.away_code}
          {f.week ? ` · ${t("week", { week: f.week })}` : ""}
        </span>
        <span className="ml-auto rounded bg-bg px-2 py-0.5 text-xs" data-testid="report-status">
          {t(`status.${report.status}`)}
        </span>
      </div>
      {busy ? (
        <div
          role="progressbar"
          aria-label={t("progress")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={report.progress}
          className="h-2 overflow-hidden rounded bg-bg"
        >
          <div
            className="h-full bg-pri transition-all"
            style={{ width: `${Math.max(report.progress, 5)}%` }}
          />
        </div>
      ) : null}
      {report.status === "failed" ? (
        <p className="text-sm text-neg" role="status">
          {t("failed")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
        <span className="tabular-nums">
          {format.dateTime(new Date(report.created_at), {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
        {report.created_by?.name ? <span>{report.created_by.name}</span> : null}
        {asOf?.season ? (
          <span>
            {asOf.week
              ? t("asOfWeek", { season: asOf.season, week: asOf.week })
              : t("asOf", { season: asOf.season })}
          </span>
        ) : null}
        {meta.length ? <span className="tabular-nums">{meta.join(" · ")}</span> : null}
        {report.status === "ready" ? (
          <a
            href={`/api/reports/${report.id}/download`}
            className={cn(btn, "ml-auto")}
            data-testid="report-download"
            target="_blank"
            rel="noopener"
          >
            {t("download")}
          </a>
        ) : null}
      </div>
    </li>
  );
}

/** Rapor listesi; üretim sürerken sayfa kendini yeniler (ilerleme göstergesi). */
export function ReportList({ reports, highlight }: { reports: Report[]; highlight?: string }) {
  const t = useTranslations("reports");
  if (!reports.length) {
    return <EmptyState title={t("emptyTitle")} description={t("empty")} />;
  }
  return (
    <>
      <StatusPoller active={reports.some((r) => isBusy(r.status))} intervalMs={1500} />
      <ol className="flex flex-col gap-2" data-testid="reports">
        {reports.map((r) => (
          <Row key={r.id} report={r} highlight={r.id === highlight} />
        ))}
      </ol>
    </>
  );
}
