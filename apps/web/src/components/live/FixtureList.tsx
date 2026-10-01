import { TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import type { Fixture } from "@/lib/analysis";

/** Kulübün maçları; canlı kayıt ve video ekranlarında maç seçimi için. */
export async function FixtureList({
  fixtures,
  href,
  testId,
}: {
  fixtures: Fixture[];
  href: (fixture: Fixture) => string;
  testId: string;
}) {
  const t = await getTranslations("live");
  const format = await getFormatter();
  return (
    <ol className="flex flex-col gap-2" data-testid={testId}>
      {fixtures.map((fixture) => (
        <li key={fixture.id}>
          <Link
            href={href(fixture)}
            data-fixture-week={fixture.week ?? undefined}
            className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface p-3 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus"
          >
            <span className="w-16 text-xs text-ink-3">
              {t("week", { week: fixture.week ?? 0 })}
            </span>
            <span className="w-40 text-xs text-ink-2 tabular-nums">
              {fixture.kickoff_at
                ? format.dateTime(new Date(fixture.kickoff_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                    timeZone: "Europe/Istanbul",
                  })
                : t("dateTbd")}
            </span>
            <span className="flex items-center gap-2 font-medium">
              <TeamBadge code={fixture.home.code} name={fixture.home.name} />
              {fixture.home.name}
              <span className="text-ink-3 tabular-nums">
                {fixture.home_score !== null && fixture.away_score !== null
                  ? `${fixture.home_score}–${fixture.away_score}`
                  : "–"}
              </span>
              <TeamBadge code={fixture.away.code} name={fixture.away.name} />
              {fixture.away.name}
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
