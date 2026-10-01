import { SampleSizeBadge, SourceBadge } from "@kurgu/ui";
import { useTranslations } from "next-intl";
import type { MetricValue } from "@/lib/analysis";
import { sourceKey } from "@/lib/metric-display";

/** Bir metriğin yanındaki rozetler: kaynak, az veri, dolaylı ve yaklaşık (SPEC §13.2, §6.4). */
export function MetricBadges({
  value,
  showSource = true,
}: {
  value: MetricValue;
  showSource?: boolean;
}) {
  const t = useTranslations("analysis.badges");
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {showSource ? <SourceBadge label={t(`source.${sourceKey(value.source)}`)} /> : null}
      {value.low_sample ? (
        <SampleSizeBadge
          label={t("lowSample")}
          n={value.trials ?? undefined}
          matches={value.matches ?? 0}
        />
      ) : null}
      {value.indirect ? <TagBadge label={t("indirect")} /> : null}
      {value.approx ? <TagBadge label={t("approx")} /> : null}
    </span>
  );
}

function TagBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded border border-dashed border-ink-3 px-1.5 py-0.5 text-[11px] text-ink-2">
      {label}
    </span>
  );
}
