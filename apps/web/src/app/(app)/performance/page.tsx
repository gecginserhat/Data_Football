import { DemoBadge, EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { WellnessForm } from "@/components/performance/WellnessForm";
import { PendingButton } from "@/components/reports/PendingButton";
import { btnPrimary, inputCls } from "@/components/routines/styles";
import {
  getLoadOverview,
  loadScope,
  todayIso,
  type LoadAlert,
  type LoadOverview,
  type PlayerLoadRow,
  type TrainingSession,
} from "@/lib/performance";
import { createSession } from "@/lib/performance-actions";
import { squadAccess } from "@/lib/squad";

type Search = { error?: string; saved?: string };

const MD_CODES = ["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"] as const;

/**
 * Spor bilimi (SPEC §8.2-8.3): takım yük tablosu, sıçrama ve kafa vuruşu uyarıları, seans ve
 * iyi oluş girişi. Yönetici yalnız takım özetini, oyuncu yalnız kendi verisini görür (A-86).
 */
export default async function PerformancePage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations("performance");
  const tStates = await getTranslations("states");
  const scope = await loadScope();
  if (scope === null) {
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
  if (scope === "own") {
    const { playerId } = await squadAccess();
    if (playerId) redirect(`/performance/players/${playerId}`);
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState title={t("notLinkedTitle")} description={t("notLinked")} />
      </>
    );
  }
  const overview = await getLoadOverview();
  if (overview.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={overview} />
      </>
    );
  }
  const data = overview.data;
  const access = await squadAccess();
  return (
    <>
      <PageTitle sub={t(scope === "summary" ? "subtitleSummary" : "subtitle")}>
        {t("title")}
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
          {t(`saved.${search.saved === "wellness" ? "wellness" : "session"}`)}
        </p>
      ) : null}

      <Summary data={data} />

      {data.alerts ? (
        <Section id="alerts" title={t("alerts.title")}>
          <AlertList alerts={data.alerts} />
        </Section>
      ) : null}

      {data.players ? (
        <Section
          id="load"
          title={t("table.title")}
          action={
            access.edit ? (
              <Link
                href="/admin/squad"
                className="text-sm text-pri underline-offset-2 hover:underline"
              >
                {t("editSquad")}
              </Link>
            ) : null
          }
        >
          {data.players.length === 0 ? (
            <EmptyState title={t("noSquadTitle")} description={t("noSquad")} />
          ) : (
            <LoadTable rows={data.players} />
          )}
          <p className="mt-2 max-w-3xl text-xs text-ink-3" data-testid="acwr-note">
            {t("acwrNote")}
          </p>
        </Section>
      ) : null}

      {data.players && data.players.length ? (
        <>
          <Section id="session" title={t("session.title")}>
            <SessionForm players={data.players} />
          </Section>
          <Section id="wellness" title={t("wellness.title")}>
            <WellnessForm
              players={data.players.map((r) => ({ id: r.player.id, name: label(r.player) }))}
              today={todayIso()}
              returnTo="performance"
            />
          </Section>
        </>
      ) : null}

      <Section id="sessions" title={t("sessions.title")}>
        {data.sessions.length === 0 ? (
          <EmptyState title={t("emptyTitle")} description={t("empty")} />
        ) : (
          <SessionList sessions={data.sessions} />
        )}
      </Section>
    </>
  );
}

function label(p: PlayerLoadRow["player"]): string {
  return p.shirt_number ? `${p.shirt_number} · ${p.name}` : p.name;
}

async function Summary({ data }: { data: LoadOverview }) {
  const t = await getTranslations("performance.summary");
  const format = await getFormatter();
  const s = data.summary;
  const n = (v: number | null | undefined, digits = 0) =>
    v == null ? "—" : format.number(v, { maximumFractionDigits: digits });
  const items = [
    { key: "players", value: `${n(s.players_with_data)} / ${n(s.players)}` },
    { key: "sessions", value: n(s.sessions_7d) },
    { key: "load", value: n(s.mean_load_7d) },
    { key: "wellness", value: n(s.wellness_entries_7d) },
    { key: "hooper", value: n(s.mean_hooper_7d, 1) },
  ];
  return (
    <dl className="mb-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-5" data-testid="load-summary">
      {items.map((i) => (
        <div key={i.key} className="rounded-lg border border-line bg-surface p-3">
          <dt className="text-xs text-ink-2">{t(i.key)}</dt>
          <dd className="font-condensed text-2xl font-semibold tabular-nums">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

async function AlertList({ alerts }: { alerts: LoadAlert[] }) {
  const t = await getTranslations("performance.alerts");
  const format = await getFormatter();
  if (alerts.length === 0) {
    return <p className="text-sm text-ink-2">{t("none")}</p>;
  }
  return (
    <>
      <ul className="flex flex-col gap-2" data-testid="alerts">
        {alerts.map((a) => (
          <li
            key={`${a.player.id}-${a.metric}-${a.week}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-l-4 border-line border-l-neg bg-surface p-3"
            data-testid="alert"
            data-metric={a.metric}
          >
            <span className="flex flex-col">
              <span className="font-medium">
                <span className="mr-2 rounded border border-neg px-1.5 py-0.5 text-[11px] font-semibold text-ink">
                  {t("badge")}
                </span>
                <Link
                  href={`/performance/players/${a.player.id}`}
                  className="underline-offset-2 hover:underline"
                >
                  {label(a.player)}
                </Link>
                {a.player.is_demo ? (
                  <span className="ml-2">
                    <DemoBadge label={t("demo")} />
                  </span>
                ) : null}
              </span>
              <span className="text-sm text-ink-2">
                {t("text", {
                  metric: t(`metric.${a.metric}`),
                  week: format.dateTime(new Date(`${a.week}T00:00:00Z`), {
                    day: "numeric",
                    month: "short",
                    timeZone: "UTC",
                  }),
                })}
              </span>
            </span>
            <span className="text-sm tabular-nums">
              {t("values", {
                total: a.total,
                threshold: format.number(a.threshold, { maximumFractionDigits: 1 }),
                mean: format.number(a.mean, { maximumFractionDigits: 1 }),
                weeks: a.weeks,
              })}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-3">{t("disclaimer")}</p>
    </>
  );
}

async function LoadTable({ rows }: { rows: PlayerLoadRow[] }) {
  const t = await getTranslations("performance.table");
  const format = await getFormatter();
  const n = (v: number | null | undefined, digits = 0) =>
    v == null ? "—" : format.number(v, { maximumFractionDigits: digits });
  const z = (v: number | null | undefined) =>
    v == null
      ? "—"
      : format.number(v, {
          signDisplay: "exceptZero",
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        });
  const date = (d: string | null | undefined) =>
    d
      ? format.dateTime(new Date(`${d}T00:00:00Z`), {
          day: "numeric",
          month: "short",
          timeZone: "UTC",
        })
      : "—";
  const cols = [
    "last",
    "load7",
    "acute",
    "chronic",
    "acwr",
    "z",
    "hooper",
    "jumps",
    "headers",
  ] as const;
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-max text-left text-sm" data-testid="load-table">
        <caption className="sr-only">{t("title")}</caption>
        <thead className="border-b border-line text-xs text-ink-3">
          <tr>
            <th scope="col" className="sticky left-0 z-10 bg-surface px-3 py-2">
              {t("player")}
            </th>
            {cols.map((c) => (
              <th key={c} scope="col" className="px-3 py-2 text-right" title={t(`help.${c}`)}>
                {t(`cols.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.player.id}
              className="border-b border-line last:border-0"
              data-testid="load-row"
              data-player={r.player.name}
            >
              <th scope="row" className="sticky left-0 z-10 bg-surface px-3 py-2 font-medium">
                <span className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/performance/players/${r.player.id}`}
                    className="underline-offset-2 hover:underline"
                  >
                    {label(r.player)}
                  </Link>
                  {r.player.is_demo ? <DemoBadge label={t("demo")} /> : null}
                  {r.days > 0 && r.low_data ? (
                    <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium">
                      {t("lowData")}
                    </span>
                  ) : null}
                </span>
              </th>
              <td className="px-3 py-2 text-right tabular-nums">{date(r.last_session)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{n(r.load_7d)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{n(r.acute)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{n(r.chronic)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-ink-3">{n(r.acwr, 2)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{z(r.z)}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {r.hooper ? (
                  <>
                    {r.hooper.value}
                    {r.hooper.z != null ? (
                      <span className="ml-1 text-xs text-ink-3">({z(r.hooper.z)})</span>
                    ) : null}
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{r.jumps_week}</td>
              <td className="px-3 py-2 text-right tabular-nums">{r.headers_week}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function SessionForm({ players }: { players: PlayerLoadRow[] }) {
  const t = await getTranslations("performance.session");
  return (
    <form action={createSession} className="flex flex-col gap-4" data-testid="session-form">
      <div className="grid max-w-2xl gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">
          {t("date")}
          <input type="date" name="date" required defaultValue={todayIso()} className={inputCls} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("md")}
          <select name="md_code" defaultValue="" className={inputCls}>
            <option value="">—</option>
            {MD_CODES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("name")}
          <input
            name="title"
            required
            maxLength={120}
            defaultValue={t("defaultName")}
            className={inputCls}
          />
        </label>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-max text-left text-sm">
          <caption className="sr-only">{t("title")}</caption>
          <thead className="border-b border-line text-xs text-ink-3">
            <tr>
              <th scope="col" className="px-3 py-2">
                {t("include")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("rpe")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("minutes")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("headers")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("jumps")}
              </th>
            </tr>
          </thead>
          <tbody>
            {players.map(({ player: p }) => {
              const name = label(p);
              return (
                <tr key={p.id} className="border-b border-line last:border-0">
                  <td className="px-3 py-1">
                    <label className="flex min-h-11 items-center gap-2">
                      <input
                        type="checkbox"
                        name="player"
                        value={p.id}
                        className="size-5"
                        data-testid={`session-include-${p.shirt_number ?? p.id}`}
                      />
                      {name}
                    </label>
                  </td>
                  <td className="px-3 py-1">
                    <input
                      name={`rpe:${p.id}`}
                      type="number"
                      min={0}
                      max={10}
                      step={0.5}
                      aria-label={t("rpeFor", { name })}
                      className={`${inputCls} w-20`}
                      data-testid={`session-rpe-${p.shirt_number ?? p.id}`}
                    />
                  </td>
                  <td className="px-3 py-1">
                    <input
                      name={`minutes:${p.id}`}
                      type="number"
                      min={0}
                      max={300}
                      aria-label={t("minutesFor", { name })}
                      className={`${inputCls} w-20`}
                      data-testid={`session-minutes-${p.shirt_number ?? p.id}`}
                    />
                  </td>
                  <td className="px-3 py-1">
                    <input
                      name={`headers:${p.id}`}
                      type="number"
                      min={0}
                      max={500}
                      aria-label={t("headersFor", { name })}
                      className={`${inputCls} w-20`}
                    />
                  </td>
                  <td className="px-3 py-1">
                    <input
                      name={`jumps:${p.id}`}
                      type="number"
                      min={0}
                      max={1000}
                      aria-label={t("jumpsFor", { name })}
                      className={`${inputCls} w-20`}
                      data-testid={`session-jumps-${p.shirt_number ?? p.id}`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">{t("help")}</p>
      <div>
        <PendingButton className={btnPrimary} pendingLabel={t("saving")} testId="session-save">
          {t("save")}
        </PendingButton>
      </div>
    </form>
  );
}

async function SessionList({ sessions }: { sessions: TrainingSession[] }) {
  const t = await getTranslations("performance.sessions");
  const format = await getFormatter();
  return (
    <ul className="flex flex-col gap-2" data-testid="sessions">
      {sessions.map((s) => (
        <li
          key={s.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface p-3 text-sm"
          data-testid="session"
        >
          <span className="flex flex-wrap items-center gap-2">
            <span className="tabular-nums">
              {format.dateTime(new Date(`${s.date}T00:00:00Z`), {
                weekday: "short",
                day: "numeric",
                month: "short",
                timeZone: "UTC",
              })}
            </span>
            {s.md_code ? (
              <span className="rounded border border-line px-1.5 py-0.5 text-[11px]">
                {s.md_code}
              </span>
            ) : null}
            <span className="font-medium">{s.title}</span>
            {s.is_demo ? <DemoBadge label={t("demo")} /> : null}
          </span>
          <span className="text-ink-2 tabular-nums">
            {t("stats", {
              players: s.players,
              srpe: format.number(s.mean_srpe, { maximumFractionDigits: 0 }),
              jumps: s.jumps,
              headers: s.headers,
            })}
          </span>
        </li>
      ))}
    </ul>
  );
}
