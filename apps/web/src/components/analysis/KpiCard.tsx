import { useFormatter, useTranslations } from "next-intl";
import type { MetricValue } from "@/lib/analysis";
import { formatMetric } from "@/lib/metric-display";
import { MetricBadges } from "./MetricBadges";

export interface KpiCardProps {
  metric: string;
  value: MetricValue | undefined;
}

/** Tek metrik kartı: değer, lig sırası ve rozetler. Değer yoksa nedenini söyler. */
export function KpiCard({ metric, value }: KpiCardProps) {
  const t = useTranslations("analysis");
  const format = useFormatter();
  return (
    <div
      className="flex min-h-28 flex-col gap-1 rounded-lg border border-line bg-surface p-4"
      data-metric={metric}
    >
      <p className="text-xs font-medium text-ink-3">{t(`metrics.${metric}.label`)}</p>
      {value ? (
        <>
          <p className="font-condensed text-3xl font-semibold tabular-nums">
            {formatMetric(format.number, metric, value.value)}
          </p>
          <p className="text-sm text-ink-2" data-testid="kpi-rank">
            {t("rank", { rank: value.rank, teams: value.teams })}
          </p>
          <MetricBadges value={value} />
        </>
      ) : (
        <p className="text-sm text-ink-3">{t("noValue")}</p>
      )}
    </div>
  );
}
