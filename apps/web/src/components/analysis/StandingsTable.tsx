import { TeamBadge, cn } from "@kurgu/ui";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { Standings } from "@/lib/analysis";

export function StandingsTable({
  standings,
  clubId,
  hrefFor,
}: {
  standings: Standings;
  clubId: string | null;
  hrefFor: (teamId: string) => string;
}) {
  const t = useTranslations("analysis.standings");
  const cols = ["played", "won", "drawn", "lost", "gf", "ga", "pts"] as const;
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-max text-sm tabular-nums">
        <caption className="sr-only">{t("caption", { week: standings.week })}</caption>
        <thead className="border-b border-line text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-3 py-2 text-right">
              {t("pos")}
            </th>
            <th scope="col" className="sticky left-0 bg-surface px-3 py-2 text-left">
              {t("team")}
            </th>
            {cols.map((c) => (
              <th key={c} scope="col" className="px-3 py-2 text-right">
                <abbr title={t(`${c}Long`)} className="no-underline">
                  {t(c)}
                </abbr>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {standings.rows.map((r) => {
            const club = r.team.id === clubId;
            return (
              <tr
                key={r.team.id}
                className={cn("border-b border-line last:border-0", club && "bg-accent/10")}
              >
                <td className="px-3 py-2 text-right">{r.position}</td>
                <th
                  scope="row"
                  className={cn(
                    "sticky left-0 px-3 py-2 text-left font-medium",
                    club
                      ? "bg-[color-mix(in_srgb,var(--accent)_10%,var(--surface))]"
                      : "bg-surface",
                  )}
                >
                  <Link
                    href={hrefFor(r.team.id)}
                    className="flex items-center gap-2 underline-offset-2 hover:underline"
                  >
                    <TeamBadge code={r.team.code} name={r.team.name} highlight={club} />
                    <span className="max-w-40 truncate">{r.team.name}</span>
                  </Link>
                </th>
                {cols.map((c) => (
                  <td
                    key={c}
                    className={cn("px-3 py-2 text-right", c === "pts" && "font-semibold")}
                  >
                    {r[c]}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
