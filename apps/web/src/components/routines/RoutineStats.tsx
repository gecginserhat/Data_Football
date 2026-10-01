import { SampleSizeBadge } from "@kurgu/ui";
import { useFormatter, useTranslations } from "next-intl";
import type { RoutineStats } from "@/lib/routines";

/**
 * Rutin performansı (SPEC §6.3, A-44). Oranlar beta-binom ile büzülmüş değerdir; örneklem
 * küçükse "Az veri" rozeti çıkar (n < 8 ya da maç < 5).
 */
export function RoutineStatsLine({ stats }: { stats: RoutineStats }) {
  const t = useTranslations("routines.stats");
  const tStates = useTranslations("states");
  const format = useFormatter();
  if (stats.uses === 0) {
    return <p className="text-xs text-ink-3">{t("unused")}</p>;
  }
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tabular-nums text-ink-2">
      <span>{t("uses", { n: stats.uses, matches: stats.matches })}</span>
      <span>· {t("goals", { n: stats.goals })}</span>
      <span>· xG {format.number(stats.xg, { maximumFractionDigits: 2 })}</span>
      <SampleSizeBadge label={tStates("lowSample")} n={stats.uses} matches={stats.matches} />
    </p>
  );
}

function pct(format: ReturnType<typeof useFormatter>, v: number | null): string {
  return v === null ? "—" : format.number(v, { style: "percent", maximumFractionDigits: 0 });
}

export function RoutineStatsPanel({ stats }: { stats: RoutineStats }) {
  const t = useTranslations("routines.stats");
  const tStates = useTranslations("states");
  const format = useFormatter();
  const rows: [string, string][] = [
    [t("usesLabel"), format.number(stats.uses)],
    [t("matchesLabel"), format.number(stats.matches)],
    [t("goalsLabel"), format.number(stats.goals)],
    [t("xgLabel"), format.number(stats.xg, { maximumFractionDigits: 2 })],
    [
      t("xgPerUse"),
      stats.xg_per_use === null
        ? "—"
        : format.number(stats.xg_per_use, { maximumFractionDigits: 3 }),
    ],
    [t("firstContact"), pct(format, stats.first_contact.shrunk)],
    [t("shot"), pct(format, stats.shot.shrunk)],
  ];
  return (
    <section aria-labelledby="stats-title" className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 id="stats-title" className="font-condensed text-base font-semibold">
          {t("title")}
        </h2>
        {stats.uses > 0 ? (
          <SampleSizeBadge label={tStates("lowSample")} n={stats.uses} matches={stats.matches} />
        ) : null}
      </div>
      {stats.uses === 0 ? (
        <p className="text-sm text-ink-3">{t("unusedLong")}</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm" data-testid="routine-stats">
            {rows.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-2">{k}</dt>
                <dd className="text-right font-medium tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-ink-3">{t("shrunkNote")}</p>
        </>
      )}
    </section>
  );
}
