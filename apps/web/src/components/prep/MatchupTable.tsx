import { SampleSizeBadge } from "@kurgu/ui";
import { useFormatter, useTranslations } from "next-intl";
import type { MatchupRow, PrepFixture } from "@/lib/prep";
import { formatEvidence, metricLabelKey } from "@/lib/prep-display";

type Side = MatchupRow["opponent"];

function Cell({ side, metric }: { side: Side; metric: string }) {
  const t = useTranslations();
  const format = useFormatter();
  if (!side) return <td className="px-2 py-1.5 text-right text-ink-3">—</td>;
  return (
    <td className="px-2 py-1.5 text-right tabular-nums">
      {formatEvidence(format.number, metric, side.value)}
      <span className="ml-1 text-xs text-ink-3">
        {t("prep.evidence.rankOf", { rank: side.rank, teams: side.teams })}
      </span>
      {side.low_sample ? (
        <span className="ml-1">
          <SampleSizeBadge label={t("analysis.badges.lowSample")} matches={0} />
        </span>
      ) : null}
    </td>
  );
}

/** Eşleşme notları: aynı metrikte rakip ve kulüp, lig ortalamasıyla (SPEC §13.2). */
export function MatchupTable({ rows, fixture }: { rows: MatchupRow[]; fixture: PrepFixture }) {
  const t = useTranslations();
  const format = useFormatter();
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-[36rem] text-sm" data-testid="matchup">
        <caption className="sr-only">{t("prep.matchup.caption")}</caption>
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-2 py-2 font-medium">
              {t("prep.evidence.metric")}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              {t("prep.matchup.opponent", {
                team: fixture.opponent.code,
                season: fixture.previous_season?.label ?? "—",
              })}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              {t("prep.matchup.opponent", {
                team: fixture.opponent.code,
                season: fixture.season.label,
              })}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              {t("prep.matchup.club", {
                team: fixture.club.code,
                season: fixture.previous_season?.label ?? "—",
              })}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              {t("prep.evidence.leagueMean")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.metric} className="border-t border-line">
              <th scope="row" className="px-2 py-1.5 text-left font-normal">
                {metricLabelKey(r.metric) ? t(metricLabelKey(r.metric)) : r.metric}
                {r.indirect ? (
                  <span className="ml-1 text-xs text-ink-3">({t("analysis.badges.indirect")})</span>
                ) : null}
              </th>
              <Cell side={r.opponent} metric={r.metric} />
              <Cell side={r.opponent_current} metric={r.metric} />
              <Cell side={r.club} metric={r.metric} />
              <td className="px-2 py-1.5 text-right text-ink-2 tabular-nums">
                {r.league_mean !== null
                  ? formatEvidence(format.number, r.metric, r.league_mean)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
