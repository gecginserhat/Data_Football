import { EmptyState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { FixtureList } from "@/components/live/FixtureList";
import { liveAccess } from "@/lib/live-data";
import { clubFixtures } from "@/lib/live-fixtures";

export default async function LivePage() {
  const t = await getTranslations("live");
  const tStates = await getTranslations("states");
  const access = await liveAccess();
  if (!access.tag) {
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
  const fixtures = await clubFixtures();
  if (fixtures.status === "no-club") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState title={t("noClubTitle")} description={t("noClub")} />
      </>
    );
  }
  if (fixtures.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={fixtures} />
      </>
    );
  }
  const { upcoming, played } = fixtures.data;
  return (
    <>
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      <Section id="live-upcoming" title={t("upcoming")}>
        {upcoming.length ? (
          <FixtureList fixtures={upcoming} href={(f) => `/live/${f.id}`} testId="live-upcoming" />
        ) : (
          <p className="text-sm text-ink-2">{t("noUpcoming")}</p>
        )}
      </Section>
      {played.length ? (
        <Section id="live-played" title={t("played")}>
          <FixtureList fixtures={played} href={(f) => `/live/${f.id}`} testId="live-played" />
        </Section>
      ) : null}
    </>
  );
}
