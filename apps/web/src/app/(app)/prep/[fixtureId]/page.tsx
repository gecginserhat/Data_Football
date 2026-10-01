import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { BriefingPanel } from "@/components/prep/BriefingPanel";
import { FeedbackPanel } from "@/components/prep/FeedbackPanel";
import { MatchupTable } from "@/components/prep/MatchupTable";
import { CreatePlan, PlanBoard } from "@/components/prep/PlanBoard";
import { RecommendationCard } from "@/components/prep/RecommendationCard";
import { ReportList, RequestReport } from "@/components/reports/ReportList";
import { getPrep, prepAccess } from "@/lib/prep";
import { getBriefing, listReports, reportsAccess } from "@/lib/reports";

type Search = { error?: string; briefing?: string; report?: string };

export default async function PrepFixturePage({
  params,
  searchParams,
}: {
  params: Promise<{ fixtureId: string }>;
  searchParams: Promise<Search>;
}) {
  const { fixtureId } = await params;
  const search = await searchParams;
  const t = await getTranslations("prep");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const access = await prepAccess();
  if (!access.read) {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const [prep, briefing, reports, reportAccess] = await Promise.all([
    getPrep(fixtureId),
    getBriefing(fixtureId),
    listReports(fixtureId),
    reportsAccess(),
  ]);
  if (prep.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={prep} />
      </>
    );
  }
  const { fixture, recommendations, plan } = prep.data;
  const active = recommendations.filter((r) => r.status !== "rejected");
  const rejected = recommendations.filter((r) => r.status === "rejected");

  return (
    <>
      <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
        <Link href="/prep" className="underline-offset-2 hover:underline">
          {t("title")}
        </Link>
      </nav>
      <PageTitle
        sub={
          <>
            {t("fixtureSub", {
              week: fixture.week ?? 0,
              season: fixture.season.label,
              venue: t(fixture.is_home ? "home" : "away"),
            })}
            {" · "}
            {fixture.kickoff_at
              ? format.dateTime(new Date(fixture.kickoff_at), {
                  dateStyle: "full",
                  timeStyle: "short",
                  timeZone: "Europe/Istanbul",
                })
              : t("dateTbd")}
          </>
        }
      >
        <span className="inline-flex flex-wrap items-center gap-2">
          <TeamBadge code={fixture.home.code} name={fixture.home.name} />
          {fixture.home.name}
          <span className="text-ink-3">–</span>
          <TeamBadge code={fixture.away.code} name={fixture.away.name} />
          {fixture.away.name}
        </span>
      </PageTitle>

      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t.has(`errors.${search.error}`)
            ? t(`errors.${search.error}`)
            : t("errors.generic", { code: search.error })}
        </p>
      ) : null}

      <Section
        id="recommendations"
        title={t("recommendations")}
        action={
          <p className="text-xs text-ink-3" data-testid="rule-set">
            {prep.data.rule_set.is_default
              ? t("ruleSetDefault", { label: prep.data.rule_set.label ?? "—" })
              : t("ruleSetClub", { version: prep.data.rule_set.version })}
            {access.rules ? (
              <>
                {" · "}
                <Link href="/admin/rules" className="text-pri underline-offset-2 hover:underline">
                  {t("editRules")}
                </Link>
              </>
            ) : null}
          </p>
        }
      >
        <p className="mb-3 text-sm text-ink-2">
          {t("basis", {
            previous: fixture.previous_season?.label ?? "—",
            current: fixture.season.label,
          })}
        </p>
        {active.length === 0 ? (
          <EmptyState title={t("noRecsTitle")} description={t("noRecs")} />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2" data-testid="recommendations">
            {active.map((rec) => (
              <RecommendationCard
                key={rec.id}
                rec={rec}
                fixtureId={fixture.id}
                canDecide={access.decide}
              />
            ))}
          </div>
        )}
        {rejected.length ? (
          <details className="mt-4">
            <summary className="min-h-11 cursor-pointer text-sm text-ink-2">
              {t("rejectedCount", { count: rejected.length })}
            </summary>
            <div className="mt-2 grid gap-4 lg:grid-cols-2">
              {rejected.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  rec={rec}
                  fixtureId={fixture.id}
                  canDecide={access.decide}
                />
              ))}
            </div>
          </details>
        ) : null}
      </Section>

      <BriefingPanel
        briefing={briefing}
        fixtureId={fixture.id}
        canBrief={reportAccess.brief}
        error={search.briefing}
      />

      <FeedbackPanel fixture={fixture} recommendations={recommendations} />
      <Section id="matchup" title={t("matchup.title")}>
        {prep.data.matchup.length ? (
          <MatchupTable rows={prep.data.matchup} fixture={fixture} />
        ) : (
          <EmptyState title={t("matchup.emptyTitle")} description={t("matchup.empty")} />
        )}
      </Section>

      <Section id="plan" title={t("plan.heading")}>
        {plan ? (
          <PlanBoard
            plan={plan}
            fixtureId={fixture.id}
            canMark={access.mark}
            assignees={prep.data.assignees}
            routines={prep.data.routines}
          />
        ) : (
          <CreatePlan fixtureId={fixture.id} canMark={access.mark} />
        )}
      </Section>

      <Section
        id="reports"
        title={t("reports")}
        action={<RequestReport fixtureId={fixture.id} returnTo="prep" />}
      >
        {reports.status === "ok" ? (
          <ReportList reports={reports.data.slice(0, 6)} highlight={search.report} />
        ) : (
          <NotLoaded result={reports} />
        )}
      </Section>
    </>
  );
}
