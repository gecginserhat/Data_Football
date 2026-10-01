import { EmptyState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { ReportList, RequestReport, type FixtureOption } from "@/components/reports/ReportList";
import { clubFixtures } from "@/lib/live-fixtures";
import { listReports, reportsAccess } from "@/lib/reports";

type Search = { error?: string; report?: string };

/** Rapor arşivi ve yeni rapor isteği (SPEC §14, ADR-0012). */
export default async function ReportsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations("reports");
  const tStates = await getTranslations("states");
  const access = await reportsAccess();
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
  const [reports, fixtures] = await Promise.all([listReports(), clubFixtures()]);
  const options: FixtureOption[] =
    fixtures.status === "ok"
      ? [...fixtures.data.upcoming, ...fixtures.data.played].map((f) => ({
          id: f.id,
          label: `${t("week", { week: f.week ?? 0 })} · ${f.home.code}–${f.away.code}`,
        }))
      : [];

  return (
    <>
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      <Section id="new-report" title={t("new")}>
        {options.length ? (
          <RequestReport fixtures={options} fixtureId={options[0]?.id} returnTo="reports" />
        ) : (
          <EmptyState title={t("noFixturesTitle")} description={t("noFixtures")} />
        )}
      </Section>
      <Section id="reports" title={t("archive")}>
        {reports.status === "ok" ? (
          <ReportList reports={reports.data} highlight={search.report} />
        ) : (
          <NotLoaded result={reports} />
        )}
      </Section>
    </>
  );
}
