"use client";

import { TeamBadge, cn } from "@kurgu/ui";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import type { MetricValue } from "@/lib/analysis";
import { formatMetric } from "@/lib/metric-display";

export interface LeagueRow {
  team: { id: string; code: string; name: string };
  isClub: boolean;
  values: Record<string, MetricValue>;
  href: string;
}

/**
 * Duran top tablosu: yapışkan ilk sütun, başlığa tıklayınca sıralama (SPEC §13.3 DataTable).
 * Her hücrede değer ve lig sırası yazar; az veri ve dolaylı göstergeler hücrede işaretlenir.
 */
export function LeagueTable({
  rows,
  metrics,
  initialSort,
  caption,
}: {
  rows: LeagueRow[];
  metrics: string[];
  initialSort: string;
  caption: string;
}) {
  const t = useTranslations("analysis");
  const format = useFormatter();
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({
    key: initialSort,
    desc: true,
  });

  const sorted = useMemo(() => {
    const out = [...rows];
    out.sort((a, b) => {
      if (sort.key === "team") {
        return sort.desc
          ? b.team.code.localeCompare(a.team.code)
          : a.team.code.localeCompare(b.team.code);
      }
      const av = a.values[sort.key]?.value;
      const bv = b.values[sort.key]?.value;
      if (av === undefined) return 1;
      if (bv === undefined) return -1;
      return sort.desc ? bv - av : av - bv;
    });
    return out;
  }, [rows, sort]);

  const toggle = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== "team" }));
  const ariaSort = (key: string) =>
    sort.key === key ? (sort.desc ? "descending" : "ascending") : undefined;

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-max text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-line text-xs text-ink-3">
          <tr>
            <th
              scope="col"
              aria-sort={ariaSort("team")}
              className="sticky left-0 z-10 bg-surface px-3 py-2"
            >
              <SortButton label={t("table.team")} onClick={() => toggle("team")} />
            </th>
            {metrics.map((m) => (
              <th key={m} scope="col" aria-sort={ariaSort(m)} className="px-3 py-2 text-right">
                <SortButton
                  label={t(`metrics.${m}.short`)}
                  title={t(`metrics.${m}.label`)}
                  onClick={() => toggle(m)}
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.team.id}
              data-team={row.team.code}
              className={cn("border-b border-line last:border-0", row.isClub && "bg-accent/10")}
            >
              <th
                scope="row"
                className={cn(
                  "sticky left-0 z-10 px-3 py-2 font-medium",
                  row.isClub
                    ? "bg-[color-mix(in_srgb,var(--accent)_10%,var(--surface))]"
                    : "bg-surface",
                )}
              >
                <Link
                  href={row.href}
                  className="flex items-center gap-2 underline-offset-2 hover:underline"
                >
                  <TeamBadge code={row.team.code} name={row.team.name} highlight={row.isClub} />
                  <span className="max-w-40 truncate">{row.team.name}</span>
                </Link>
              </th>
              {metrics.map((m) => {
                const v = row.values[m];
                return (
                  <td key={m} className="px-3 py-2 text-right tabular-nums" data-metric={m}>
                    {v ? (
                      <span className="inline-flex items-baseline gap-1.5">
                        <span>{formatMetric(format.number, m, v.value)}</span>
                        <span className="text-xs text-ink-3">
                          {t("rankShort", { rank: v.rank })}
                        </span>
                        {v.low_sample ? (
                          <abbr
                            title={t("badges.lowSample")}
                            className="text-xs font-semibold text-ink no-underline"
                          >
                            *
                          </abbr>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-ink-3" aria-label={t("noValue")}>
                        –
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SortButton({
  label,
  title,
  onClick,
}: {
  label: string;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="min-h-11 font-medium underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
    >
      {label}
    </button>
  );
}
