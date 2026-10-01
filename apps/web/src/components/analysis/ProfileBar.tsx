import { useFormatter, useTranslations } from "next-intl";
import type { Benchmark, MetricValue } from "@/lib/analysis";
import { formatMetric } from "@/lib/metric-display";
import { MetricBadges } from "./MetricBadges";

export interface ProfileBarProps {
  metric: string;
  value: MetricValue;
  benchmark: Benchmark | undefined;
  /** Kendi kulübümüzün değeri; incelenen takım kulübün kendisiyse verilmez. */
  club?: { code: string; value: MetricValue } | undefined;
}

function position(v: number, b: Benchmark): number {
  if (b.max === b.min) return 50;
  return Math.min(100, Math.max(0, ((v - b.min) / (b.max - b.min)) * 100));
}

/**
 * Profil çubuğu: lig en düşük ile en yüksek değer arasında takımın yeri; lig ortalaması ve
 * kendi kulübümüz işaretli (SPEC §13.2). Çizgi süs amaçlıdır; tüm sayılar metin olarak da yazar.
 */
export function ProfileBar({ metric, value, benchmark, club }: ProfileBarProps) {
  const t = useTranslations("analysis");
  const format = useFormatter();
  const fmt = (v: number) => formatMetric(format.number, metric, v);
  return (
    <div className="flex flex-col gap-1.5 py-3" data-metric={metric}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {t(`metrics.${metric}.label`)}
          <MetricBadges value={value} />
        </span>
        <span className="flex items-baseline gap-2">
          <span className="font-condensed text-lg font-semibold tabular-nums">
            {fmt(value.value)}
          </span>
          <span className="text-xs text-ink-2 tabular-nums">
            {t("rank", { rank: value.rank, teams: value.teams })}
          </span>
        </span>
      </div>
      {benchmark ? (
        <>
          <div aria-hidden="true" className="relative h-3">
            <div className="absolute inset-x-0 top-1 h-1 rounded-full bg-line" />
            <div
              className="absolute top-0 h-3 w-0.5 bg-ink-3"
              style={{ left: `${position(benchmark.mean, benchmark)}%` }}
            />
            {club ? (
              <div
                className="absolute top-0 size-3 -translate-x-1/2 rotate-45 border border-surface bg-accent"
                style={{ left: `${position(club.value.value, benchmark)}%` }}
              />
            ) : null}
            <div
              className="absolute top-0 size-3 -translate-x-1/2 rounded-full border-2 border-surface bg-pri"
              style={{ left: `${position(value.value, benchmark)}%` }}
            />
          </div>
          <p className="flex flex-wrap gap-x-3 text-xs text-ink-3 tabular-nums">
            <span>{t("bar.min", { value: fmt(benchmark.min) })}</span>
            <span>{t("bar.mean", { value: fmt(benchmark.mean) })}</span>
            <span>{t("bar.max", { value: fmt(benchmark.max) })}</span>
            {club ? (
              <span className="text-ink-2">
                {t("bar.club", { code: club.code, value: fmt(club.value.value) })}
              </span>
            ) : null}
            {value.shrunk != null ? (
              <span>
                {t("bar.shrunk", {
                  value: fmt(value.shrunk),
                  low: fmt(value.shrunk_low ?? value.shrunk),
                  high: fmt(value.shrunk_high ?? value.shrunk),
                })}
              </span>
            ) : null}
          </p>
        </>
      ) : null}
    </div>
  );
}
