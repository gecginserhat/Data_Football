import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { FormChips } from "@/components/analysis/FormChips";
import { canReadAnalysis } from "@/components/analysis/guard";
import { KpiCard } from "@/components/analysis/KpiCard";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import {
  getFixtures,
  getProfile,
  getSeasons,
  getTeamMetrics,
  pickSeason,
  previousSeason,
  type TeamMetrics,
} from "@/lib/analysis";
import { getMe } from "@/lib/api";
import { formatMetric } from "@/lib/metric-display";
import { getOverview } from "@/lib/prep";
import { ConfidenceChip } from "@/components/prep/RecommendationCard";

const KPIS = [
  "set_piece_goals",
  "set_piece_xg",
  "set_piece_goal_share",
  "set_piece_goals_per_match",
];

export default async function OverviewPage() {
  const t = await getTranslations("analysis");
  const tStates = await getTranslations("states");
  const tPages = await getTranslations("pages.overview");
  const format = await getFormatter();
  const me = await getMe();
  const clubName = me.status === "ok" ? me.me.active_tenant?.tenant_name : undefined;

  if (!(await canReadAnalysis())) {
    return (
      <>
        <PageTitle>{tPages("title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const seasons = await getSeasons();
  if (seasons.status !== "ok") {
    return (
      <>
        <PageTitle>{tPages("title")}</PageTitle>
        <NotLoaded result={seasons} />
      </>
    );
  }
  const season = pickSeason(seasons.data);
  const metrics = season ? await getTeamMetrics(season.id) : null;
  const clubId = metrics?.status === "ok" ? metrics.data.club_team_id : null;
  if (
    !season ||
    !metrics ||
    metrics.status !== "ok" ||
    metrics.data.items.length === 0 ||
    !clubId
  ) {
    return (
      <>
        <PageTitle>{tPages("title")}</PageTitle>
        {metrics && metrics.status !== "ok" ? (
          <NotLoaded result={metrics} />
        ) : (
          <EmptyState title={tPages("emptyTitle")} description={tPages("emptyDescription")} />
        )}
      </>
    );
  }

  const last = previousSeason(seasons.data, season);
  const [profile, upcoming, lastMetrics, recs] = await Promise.all([
    getProfile(clubId, season.id),
    getFixtures(clubId, season.id, "scheduled", 5),
    last ? getTeamMetrics(last.id) : Promise.resolve(null),
    getOverview(5),
  ]);
  const threats = new Map(
    recs.status === "ok" ? recs.data.upcoming.map((u) => [u.fixture.id, u.threats]) : [],
  );
  const byTeam = new Map<string, TeamMetrics>(metrics.data.items.map((i) => [i.team.id, i]));
  const club = byTeam.get(clubId);
  const p = profile.status === "ok" ? profile.data : null;
  const lastClub =
    lastMetrics?.status === "ok"
      ? lastMetrics.data.items.find((i) => i.team.id === clubId)
      : undefined;
  const next = upcoming.status === "ok" ? upcoming.data[0] : undefined;

  return (
    <>
      <PageTitle
        sub={
          club?.as_of_week
            ? t("overview.asOfWeek", { season: season.label, week: club.as_of_week })
            : season.label
        }
      >
        {clubName ?? tPages("title")}
      </PageTitle>

      <Section id="club-status" title={t("overview.status")}>
        <div className="flex flex-wrap items-center gap-6 rounded-lg border border-line bg-surface p-4">
          {p?.standing ? (
            <p className="text-sm" data-testid="club-standing">
              {t("opponents.standing", {
                position: p.standing.position,
                pts: p.standing.pts,
                played: p.standing.played,
                week: p.standing_week ?? 0,
              })}
            </p>
          ) : (
            <p className="text-sm text-ink-3">{t("overview.noStanding")}</p>
          )}
          {p ? <FormChips form={p.form} /> : null}
          <Link
            href={`/opponents/${clubId}?season=${season.id}`}
            className="text-sm text-pri underline-offset-2 hover:underline"
          >
            {t("overview.profileLink")}
          </Link>
        </div>
      </Section>

      <Section id="club-kpis" title={t("overview.setPieces", { season: season.label })}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {KPIS.map((m) => (
            <KpiCard key={m} metric={m} value={club?.values[m]} />
          ))}
        </div>
      </Section>

      {last && lastClub ? (
        <Section id="last-season" title={t("overview.lastSeason", { season: last.label })}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="last-season">
            {[
              "set_piece_goals",
              "set_piece_xg",
              "set_piece_goal_share",
              "set_piece_goals_minus_xg",
            ].map((m) => (
              <KpiCard key={m} metric={m} value={lastClub.values[m]} />
            ))}
          </div>
        </Section>
      ) : null}

      <Section id="upcoming" title={t("overview.upcoming")}>
        {upcoming.status !== "ok" ? (
          <NotLoaded result={upcoming} />
        ) : upcoming.data.length === 0 ? (
          <EmptyState
            title={t("overview.noFixturesTitle")}
            description={t("overview.noFixtures")}
          />
        ) : (
          <ol className="flex flex-col gap-2">
            {upcoming.data.map((f) => {
              const home = f.home.id === clubId;
              const opponent = home ? f.away : f.home;
              const opp = byTeam.get(opponent.id);
              const goals = opp?.values.set_piece_goals;
              const xg = opp?.values.set_piece_xg;
              return (
                <li key={f.id} className="flex flex-col gap-1">
                  <Link
                    href={`/opponents/${opponent.id}?season=${season.id}`}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface p-3 hover:border-pri"
                    data-fixture-week={f.week ?? undefined}
                  >
                    <span className="w-16 text-xs text-ink-3">
                      {t("sequence.week", { week: f.week ?? 0 })}
                    </span>
                    <span className="w-28 text-xs text-ink-2 tabular-nums">
                      {f.kickoff_at
                        ? format.dateTime(new Date(f.kickoff_at), {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })
                        : t("overview.dateTbd")}
                    </span>
                    <span className="flex items-center gap-2 font-medium">
                      <TeamBadge code={opponent.code} name={opponent.name} />
                      {opponent.name}
                      <span className="text-xs font-normal text-ink-3">
                        {t(home ? "form.home" : "form.away")}
                      </span>
                    </span>
                    {goals || xg ? (
                      <span className="ml-auto text-xs text-ink-2 tabular-nums">
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
                    ) : null}
                  </Link>
                  <ThreatLine fixtureId={f.id} threats={threats.get(f.id) ?? []} />
                </li>
              );
            })}
          </ol>
        )}
        {next ? <p className="mt-2 text-xs text-ink-3">{t("overview.nextHint")}</p> : null}
      </Section>

      <Section id="recommendations" title={t("overview.recommendations")}>
        {recs.status !== "ok" ? (
          <NotLoaded result={recs} />
        ) : recs.data.recommendations.length === 0 ? (
          <EmptyState
            title={t("overview.recommendationsTitle")}
            description={t("overview.recommendationsNone")}
          />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2" data-testid="season-recommendations">
            {recs.data.recommendations.map((r) => (
              <li
                key={r.id}
                className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-4"
              >
                <span className="flex items-center gap-2">
                  <ConfidenceChip level={r.confidence} />
                </span>
                <span className="font-condensed text-lg leading-tight font-semibold">
                  {r.title}
                </span>
                <span className="text-sm text-ink-2">{r.why}</span>
                <span className="text-sm">{r.action}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

async function ThreatLine({
  fixtureId,
  threats,
}: {
  fixtureId: string;
  threats: { rule_id: string; title: string; confidence: string }[];
}) {
  const t = await getTranslations("analysis.overview");
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 text-xs" data-testid="threats">
      {threats.map((th) => (
        <span key={th.rule_id} className="inline-flex items-center gap-1">
          <span aria-hidden className="text-def">
            ▲
          </span>
          <span className="sr-only">{t("threat")}: </span>
          {th.title}
        </span>
      ))}
      <Link href={`/prep/${fixtureId}`} className="text-pri underline-offset-2 hover:underline">
        {t("prepLink")}
      </Link>
    </p>
  );
}
