import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { canReadAnalysis } from "@/components/analysis/guard";
import { SeasonPicker } from "@/components/analysis/SeasonPicker";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { getSeasons, getTeamMetrics, orderSeasons, pickSeason } from "@/lib/analysis";
import { formatMetric } from "@/lib/metric-display";

export default async function OpponentsPage({
  searchParams,
}: {
  searchParams: Promise<{ season?: string }>;
}) {
  const t = await getTranslations("analysis");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  if (!(await canReadAnalysis())) {
    return (
      <>
        <PageTitle>{t("opponents.title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const { season: requested } = await searchParams;
  const seasons = await getSeasons();
  if (seasons.status !== "ok") {
    return (
      <>
        <PageTitle>{t("opponents.title")}</PageTitle>
        <NotLoaded result={seasons} />
      </>
    );
  }
  const season = pickSeason(seasons.data, requested);
  const metrics = season ? await getTeamMetrics(season.id) : null;

  return (
    <>
      <PageTitle sub={t("opponents.subtitle")}>{t("opponents.title")}</PageTitle>
      {season ? (
        <div className="mb-6">
          <SeasonPicker
            seasons={orderSeasons(seasons.data)}
            current={season}
            basePath="/opponents"
          />
        </div>
      ) : null}
      {!season || !metrics ? (
        <EmptyState title={t("league.noSeasonsTitle")} description={t("league.noSeasons")} />
      ) : metrics.status !== "ok" ? (
        <NotLoaded result={metrics} />
      ) : metrics.data.items.length === 0 ? (
        <EmptyState title={t("league.emptyTitle")} description={t("league.empty")} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[...metrics.data.items]
            .sort((a, b) => a.team.name.localeCompare(b.team.name, "tr"))
            .map((item) => {
              const club = item.team.id === metrics.data.club_team_id;
              const goals = item.values.set_piece_goals;
              const xg = item.values.set_piece_xg;
              return (
                <li key={item.team.id}>
                  <Link
                    href={`/opponents/${item.team.id}?season=${season.id}`}
                    className="flex min-h-20 items-center gap-3 rounded-lg border border-line bg-surface p-4 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus"
                  >
                    <TeamBadge code={item.team.code} name={item.team.name} highlight={club} />
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-medium">
                        {item.team.name}
                        {club ? (
                          <span className="ml-2 text-xs text-ink-2">{t("yourClub")}</span>
                        ) : null}
                      </span>
                      <span className="text-xs text-ink-2 tabular-nums">
                        {goals
                          ? t("opponents.cardGoals", {
                              value: formatMetric(format.number, "set_piece_goals", goals.value),
                              rank: goals.rank,
                            })
                          : null}
                        {goals && xg ? " · " : null}
                        {xg
                          ? t("opponents.cardXg", {
                              value: formatMetric(format.number, "set_piece_xg", xg.value),
                              rank: xg.rank,
                            })
                          : null}
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
        </ul>
      )}
    </>
  );
}
