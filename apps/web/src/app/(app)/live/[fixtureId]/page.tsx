import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { LiveTaggerClient } from "@/components/live/LiveTaggerClient";
import { clubTeamId, getFixture, liveAccess } from "@/lib/live-data";
import { listRoutines } from "@/lib/routines";

export default async function LiveFixturePage({
  params,
}: {
  params: Promise<{ fixtureId: string }>;
}) {
  const { fixtureId } = await params;
  const t = await getTranslations("live");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
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
  const fixture = await getFixture(fixtureId);
  if (fixture.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={fixture} />
      </>
    );
  }
  const f = fixture.data;
  const [club, routines] = await Promise.all([
    clubTeamId(f.season_id),
    access.read ? listRoutines(undefined, false) : Promise.resolve(null),
  ]);
  const ownSide = club === f.home.id ? "home" : club === f.away.id ? "away" : null;

  return (
    <>
      <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
        <Link href="/live" className="underline-offset-2 hover:underline">
          {t("title")}
        </Link>
      </nav>
      <PageTitle
        sub={
          <>
            {t("week", { week: f.week ?? 0 })}
            {" · "}
            {f.kickoff_at
              ? format.dateTime(new Date(f.kickoff_at), {
                  dateStyle: "full",
                  timeStyle: "short",
                  timeZone: "Europe/Istanbul",
                })
              : t("dateTbd")}
          </>
        }
      >
        <span className="inline-flex flex-wrap items-center gap-2">
          <TeamBadge code={f.home.code} name={f.home.name} />
          {f.home.name}
          <span className="text-ink-3">–</span>
          <TeamBadge code={f.away.code} name={f.away.name} />
          {f.away.name}
        </span>
      </PageTitle>
      <LiveTaggerClient
        fixtureId={f.id}
        home={{ code: f.home.code, name: f.home.name }}
        away={{ code: f.away.code, name: f.away.name }}
        ownSide={ownSide}
        routines={
          routines?.status === "ok"
            ? routines.data.map((r) => ({ id: r.id, name: r.name, sp_type: r.sp_type }))
            : []
        }
      />
    </>
  );
}
