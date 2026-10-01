import { EmptyState } from "@kurgu/ui";
import { getFormatter, getTranslations } from "next-intl/server";
import { LeagueTable, type LeagueRow } from "@/components/analysis/LeagueTable";
import { ScatterPlot } from "@/components/analysis/ScatterPlot";
import { SeasonPicker } from "@/components/analysis/SeasonPicker";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { StandingsTable } from "@/components/analysis/StandingsTable";
import {
  getBenchmarks,
  getSeasons,
  getStandings,
  getTeamMetrics,
  orderSeasons,
  pickSeason,
} from "@/lib/analysis";

const TABLE_METRICS = [
  "set_piece_goals",
  "set_piece_xg",
  "set_piece_goals_minus_xg",
  "set_piece_goal_share",
  "corners_per_match",
  "goals_per_100_corners",
  "headed_goals",
  "set_piece_goals_against",
  "first_contact_win_pct",
  "aerial_win_pct",
];

export default async function LeaguePage({
  searchParams,
}: {
  searchParams: Promise<{ season?: string }>;
}) {
  const t = await getTranslations("analysis");
  const format = await getFormatter();
  const { season: requested } = await searchParams;
  const seasons = await getSeasons();
  if (seasons.status !== "ok") {
    return (
      <>
        <PageTitle>{t("league.title")}</PageTitle>
        <NotLoaded result={seasons} />
      </>
    );
  }
  const season = pickSeason(seasons.data, requested);
  if (!season) {
    return (
      <>
        <PageTitle>{t("league.title")}</PageTitle>
        <EmptyState title={t("league.noSeasonsTitle")} description={t("league.noSeasons")} />
      </>
    );
  }

  const [metrics, benchmarks, standings] = await Promise.all([
    getTeamMetrics(season.id),
    getBenchmarks(season.id),
    getStandings(season.id),
  ]);
  const href = (teamId: string) => `/opponents/${teamId}?season=${season.id}`;

  return (
    <>
      <PageTitle sub={t("league.subtitle")}>{t("league.title")}</PageTitle>
      <div className="mb-6">
        <SeasonPicker seasons={orderSeasons(seasons.data)} current={season} basePath="/league" />
      </div>

      {metrics.status !== "ok" ? (
        <NotLoaded result={metrics} />
      ) : metrics.data.items.length === 0 ? (
        <EmptyState title={t("league.emptyTitle")} description={t("league.empty")} />
      ) : (
        <>
          {benchmarks.status === "ok" ? (
            <Section id="totals" title={t("league.totals")}>
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="league-totals">
                {(
                  [
                    [
                      "set_piece_goal_share",
                      { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 },
                    ],
                    ["set_piece_goals", { maximumFractionDigits: 0 }],
                    ["goals", { maximumFractionDigits: 0 }],
                    [
                      "set_piece_goals_per_match",
                      { minimumFractionDigits: 2, maximumFractionDigits: 2 },
                    ],
                  ] as const
                ).map(([key, opts]) =>
                  benchmarks.data.totals[key] !== undefined ? (
                    <div
                      key={key}
                      className="rounded-lg border border-line bg-surface p-4"
                      data-total={key}
                    >
                      <dt className="text-xs font-medium text-ink-3">{t(`totals.${key}`)}</dt>
                      <dd className="font-condensed text-3xl font-semibold tabular-nums">
                        {format.number(benchmarks.data.totals[key]!, opts)}
                      </dd>
                    </div>
                  ) : null,
                )}
              </dl>
              {benchmarks.data.references.length > 0 ? (
                <ul className="mt-3 flex flex-col gap-1 text-xs text-ink-3">
                  {benchmarks.data.references
                    .filter(
                      (r) =>
                        r.competition.id !== season.competition.id &&
                        r.metric.endsWith("_per_match"),
                    )
                    .map((r) => (
                      <li key={`${r.competition.id}-${r.metric}`}>
                        {t("league.reference", {
                          competition: r.competition.name,
                          value: format.number(r.value, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 3,
                          }),
                        })}
                      </li>
                    ))}
                </ul>
              ) : null}
            </Section>
          ) : null}

          {standings.status === "ok" ? (
            <Section id="standings" title={t("league.standings", { week: standings.data.week })}>
              <StandingsTable
                standings={standings.data}
                clubId={metrics.data.club_team_id ?? null}
                hrefFor={href}
              />
            </Section>
          ) : null}

          <Section id="set-pieces" title={t("league.setPieceTable")}>
            <p className="mb-3 text-xs text-ink-3">{t("league.tableNote")}</p>
            <LeagueTable
              caption={t("league.setPieceTable")}
              initialSort="set_piece_goals"
              metrics={TABLE_METRICS.filter((m) => metrics.data.items.some((i) => i.values[m]))}
              rows={metrics.data.items.map((i): LeagueRow => ({
                team: i.team,
                isClub: i.team.id === metrics.data.club_team_id,
                values: i.values,
                href: href(i.team.id),
              }))}
            />
          </Section>

          <Section id="scatter" title={t("scatter.title")}>
            <ScatterPlot items={metrics.data.items} clubId={metrics.data.club_team_id ?? null} />
          </Section>
        </>
      )}
    </>
  );
}
