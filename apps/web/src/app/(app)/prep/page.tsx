import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { ConfidenceChip } from "@/components/prep/RecommendationCard";
import { getOverview, prepAccess } from "@/lib/prep";

export default async function PrepPage() {
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
  const overview = await getOverview(10);
  if (overview.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={overview} />
      </>
    );
  }
  const upcoming = overview.data.upcoming;
  return (
    <>
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      {upcoming.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <ol className="flex flex-col gap-3" data-testid="prep-fixtures">
          {upcoming.map(({ fixture, threats, recommendations }, index) => (
            <li key={fixture.id}>
              <Link
                href={`/prep/${fixture.id}`}
                className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus"
                data-fixture-week={fixture.week ?? undefined}
              >
                <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="w-16 text-xs text-ink-3">
                    {t("week", { week: fixture.week ?? 0 })}
                  </span>
                  <span className="text-xs text-ink-2 tabular-nums">
                    {fixture.kickoff_at
                      ? format.dateTime(new Date(fixture.kickoff_at), {
                          dateStyle: "medium",
                          timeStyle: "short",
                          timeZone: "Europe/Istanbul",
                        })
                      : t("dateTbd")}
                  </span>
                  <span className="flex items-center gap-2 font-medium">
                    <TeamBadge code={fixture.opponent.code} name={fixture.opponent.name} />
                    {fixture.opponent.name}
                    <span className="text-xs font-normal text-ink-3">
                      {t(fixture.is_home ? "home" : "away")}
                    </span>
                  </span>
                  {index === 0 ? (
                    <span className="rounded bg-accent px-1.5 py-0.5 text-[11px] font-semibold text-accent-ink">
                      {t("next")}
                    </span>
                  ) : null}
                  <span className="ml-auto text-xs text-ink-2">
                    {t("recCount", { count: recommendations })}
                  </span>
                </span>
                {threats.length ? (
                  <span className="flex flex-col gap-1">
                    <span className="sr-only">{t("threats")}</span>
                    {threats.map((th) => (
                      <span key={th.rule_id} className="flex flex-wrap items-center gap-2 text-sm">
                        <span aria-hidden className="text-def">
                          ▲
                        </span>
                        {th.title}
                        <ConfidenceChip level={th.confidence} />
                      </span>
                    ))}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
