import { DemoBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { HooperChart, LoadChart, WeeklyChart } from "@/components/performance/Charts";
import { WellnessForm } from "@/components/performance/WellnessForm";
import { PrivacySection } from "@/components/privacy/PrivacySection";
import { getPlayerLoad, loadScope, todayIso } from "@/lib/performance";

type Search = { error?: string; saved?: string; privacyError?: string; privacySaved?: string };

/** Oyuncu yük ayrıntısı: günlük sRPE ve EWMA, Hooper, haftalık sıçrama ve kafa vuruşu (§8.2). */
export default async function PlayerLoadPage({
  params,
  searchParams,
}: {
  params: Promise<{ playerId: string }>;
  searchParams: Promise<Search>;
}) {
  const { playerId } = await params;
  const search = await searchParams;
  const t = await getTranslations("performance");
  const format = await getFormatter();
  const scope = await loadScope();
  const result = await getPlayerLoad(playerId);
  const crumb =
    scope === "all" ? (
      <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
        <Link href="/performance" className="underline-offset-2 hover:underline">
          {t("title")}
        </Link>
      </nav>
    ) : null;
  if (result.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={result} />
      </>
    );
  }
  const data = result.data;
  const p = data.player;
  const n = (v: number | null | undefined, digits = 0) =>
    v == null ? "—" : format.number(v, { maximumFractionDigits: digits });
  const last = data.days.at(-1);
  const day = (d: string) =>
    format.dateTime(new Date(`${d}T00:00:00Z`), {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    });
  return (
    <>
      {crumb}
      <PageTitle
        sub={
          <span className="inline-flex flex-wrap items-center gap-2">
            {t(`positions.${p.position}`)}
            {p.is_demo ? <DemoBadge label={t("demo")} /> : null}
            {data.low_data ? (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium text-ink">
                {t("table.lowData")}
              </span>
            ) : null}
          </span>
        }
      >
        {p.shirt_number ? `${p.shirt_number} · ${p.name}` : p.name}
      </PageTitle>
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t.has(`errors.${search.error}`)
            ? t(`errors.${search.error}`)
            : t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      {search.saved ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t("saved.wellness")}
        </p>
      ) : null}

      <dl className="mb-8 grid gap-3 sm:grid-cols-4" data-testid="player-kpis">
        {[
          ["acute", n(last?.acute)],
          ["chronic", n(last?.chronic)],
          ["acwr", n(last?.acwr, 2)],
          ["z", last?.z == null ? "—" : format.number(last.z, { maximumFractionDigits: 1 })],
        ].map(([key, value]) => (
          <div key={key} className="rounded-lg border border-line bg-surface p-3">
            <dt className="text-xs text-ink-2">{t(`table.cols.${key}`)}</dt>
            <dd className="font-condensed text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="-mt-6 mb-8 max-w-3xl text-xs text-ink-3">{t("acwrNote")}</p>

      {data.alerts.length ? (
        <Section id="alerts" title={t("alerts.title")}>
          <ul className="flex flex-col gap-2" data-testid="player-alerts">
            {data.alerts.map((a) => (
              <li
                key={`${a.metric}-${a.week}`}
                className="rounded-lg border border-l-4 border-line border-l-neg bg-surface p-3 text-sm"
              >
                <span className="mr-2 rounded border border-neg px-1.5 py-0.5 text-[11px] font-semibold text-ink">
                  {t("alerts.badge")}
                </span>
                {t("alerts.text", { metric: t(`alerts.metric.${a.metric}`), week: day(a.week) })}{" "}
                {t("alerts.values", {
                  total: a.total,
                  threshold: format.number(a.threshold, { maximumFractionDigits: 1 }),
                  mean: format.number(a.mean, { maximumFractionDigits: 1 }),
                  weeks: a.weeks,
                })}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-ink-3">{t("alerts.disclaimer")}</p>
        </Section>
      ) : null}

      <Section id="trend" title={t("chart.loadTitle")}>
        {data.days.length ? (
          <LoadChart days={data.days} />
        ) : (
          <p className="text-sm text-ink-2">{t("chart.noLoad")}</p>
        )}
      </Section>

      <Section id="weekly" title={t("chart.weeklyTitle")}>
        {data.weeks.length ? (
          <WeeklyChart weeks={data.weeks} alerts={data.alerts} />
        ) : (
          <p className="text-sm text-ink-2">{t("chart.noLoad")}</p>
        )}
      </Section>

      <Section id="hooper" title={t("chart.hooperTitle")}>
        {data.hooper.length ? (
          <HooperChart points={data.hooper} />
        ) : (
          <p className="text-sm text-ink-2">{t("chart.noWellness")}</p>
        )}
      </Section>

      {scope === "own" || scope === "all" ? (
        <Section id="wellness" title={t("wellness.title")}>
          <WellnessForm
            players={[{ id: p.id, name: p.name }]}
            today={todayIso()}
            returnTo="player"
          />
        </Section>
      ) : null}

      {scope === "all" ? (
        <PrivacySection
          playerId={p.id}
          returnTo="player"
          error={search.privacyError}
          saved={search.privacySaved}
        />
      ) : null}

      <Section id="player-sessions" title={t("sessions.title")}>
        {data.sessions.length === 0 ? (
          <p className="text-sm text-ink-2">{t("chart.noLoad")}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full min-w-max text-left text-sm" data-testid="player-sessions">
              <caption className="sr-only">{t("sessions.title")}</caption>
              <thead className="border-b border-line text-xs text-ink-3">
                <tr>
                  {["date", "name", "rpe", "minutes", "srpe", "headers", "jumps"].map((c) => (
                    <th
                      key={c}
                      scope="col"
                      className={`px-3 py-2 ${c === "date" || c === "name" ? "" : "text-right"}`}
                    >
                      {t(`sessions.cols.${c}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.sessions.map((s, i) => (
                  <tr key={`${s.date}-${i}`} className="border-b border-line last:border-0">
                    <td className="px-3 py-2 tabular-nums">{day(s.date)}</td>
                    <td className="px-3 py-2">
                      {s.title}
                      {s.md_code ? (
                        <span className="ml-2 text-xs text-ink-3">{s.md_code}</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{n(s.rpe, 1)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.minutes}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{n(s.srpe)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.headers}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.jumps}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}
