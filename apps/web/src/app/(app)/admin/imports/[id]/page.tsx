import type { Schemas } from "@kurgu/api-client";
import { cn, EmptyState, ErrorState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { ErrorNotice } from "@/components/imports/ErrorNotice";
import { ImportStatus } from "@/components/imports/ImportStatus";
import { canImport, Forbidden } from "@/components/imports/guard";
import { apiClient } from "@/lib/api";
import { commitImport, saveMapping } from "@/lib/imports";

type ImportOut = Schemas["ImportOut"];
interface Issue {
  check: string;
  severity: "critical" | "warning";
  message: string;
  column: string | null;
  count: number;
  rows: number[];
}

async function load(id: string): Promise<{ status: number; data?: ImportOut }> {
  try {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/imports/{import_id}", {
      params: { path: { import_id: id } },
    });
    return { status: response.status, data };
  } catch {
    return { status: 0 };
  }
}

const STEP_KEYS = ["upload", "map", "check", "commit"] as const;

function currentStep(status: string): number {
  if (status === "committed") return 4;
  if (status === "validated") return 3;
  return 1;
}

export default async function ImportDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  if (!(await canImport())) return <Forbidden />;
  const t = await getTranslations("imports");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const { id } = await params;
  const { error, saved } = await searchParams;
  const { status, data } = await load(id);

  const back = (
    <Link href="/admin/imports" className="mb-4 inline-block text-sm text-pri hover:underline">
      ← {t("back")}
    </Link>
  );
  if (!data) {
    return (
      <>
        {back}
        {status === 404 || status === 422 ? (
          <EmptyState
            title={tStates("notFoundTitle")}
            description={tStates("notFoundDescription")}
          />
        ) : (
          <ErrorState
            title={tStates("errorTitle")}
            description={tStates("errorDescription")}
            retryLabel={tStates("retry")}
          />
        )}
      </>
    );
  }

  const report = data.report as { rows?: number; critical?: number; warnings?: number };
  const issues = ((data.report as { issues?: Issue[] }).issues ?? []) as Issue[];
  const closed = data.status === "committed" || data.status === "failed";
  const step = currentStep(data.status);
  const mappedFields = new Set(Object.values(data.columns).filter(Boolean));
  const missing = data.fields.filter((f) => f.required && !mappedFields.has(f.name));
  const firstSample = data.sample[0] ?? {};
  const optionById = new Map(data.team_options.map((o) => [o.id, o]));

  return (
    <>
      {back}
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="font-condensed text-2xl font-semibold break-all">{data.filename}</h1>
        <ImportStatus status={data.status} />
      </div>
      <p className="mb-4 text-sm text-ink-2">
        {t(`kinds.${data.kind}`)} · {t(`statusHelp.${data.status}`)}
      </p>

      <ol aria-label={t("steps.label")} className="mb-6 grid grid-cols-4 gap-2 text-xs">
        {STEP_KEYS.map((key, i) => {
          const done = i < step;
          const current = i === step;
          return (
            <li
              key={key}
              aria-current={current ? "step" : undefined}
              className={cn(
                "rounded-md border px-2 py-2 text-center",
                done && "border-pri bg-pri/10 font-medium",
                current && "border-accent bg-accent/15 font-semibold",
                !done && !current && "border-line text-ink-3",
              )}
            >
              {i + 1}. {t(`steps.${key}`)}
              <span className="sr-only">
                {done ? ` (${t("steps.done")})` : current ? ` (${t("steps.current")})` : ""}
              </span>
            </li>
          );
        })}
      </ol>

      <ErrorNotice code={error} />
      {saved && !error ? (
        <p
          role="status"
          className="mb-4 rounded-md border border-pos/40 bg-pos/10 px-4 py-3 text-sm"
        >
          {t("mapping.saved")}
        </p>
      ) : null}

      <section
        aria-labelledby="report-title"
        className="mb-6 rounded-lg border border-line bg-surface p-4 sm:p-6"
      >
        <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h2 id="report-title" className="font-condensed text-lg font-semibold">
            {t("report.title")}
          </h2>
          <span className="text-sm tabular-nums text-ink-2">
            {t("report.rows", { count: report.rows ?? 0 })} ·{" "}
            {t("report.critical", { count: report.critical ?? 0 })} ·{" "}
            {t("report.warnings", { count: report.warnings ?? 0 })}
          </span>
        </div>
        {issues.length === 0 ? (
          <p className="text-sm text-ink-2">{t("report.none")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="issues">
              <thead className="border-b border-line text-xs text-ink-3">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t("report.severity")}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t("report.check")}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t("report.message")}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t("report.count")}
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    {t("report.sampleRows")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue, i) => (
                  <tr key={i} className="border-b border-line align-top last:border-0">
                    <td className="py-2 pr-4">
                      <span
                        className={cn(
                          "inline-flex rounded px-1.5 py-0.5 text-xs font-semibold",
                          issue.severity === "critical"
                            ? "border border-neg/60 bg-neg/10 text-ink"
                            : "bg-accent/15 text-ink",
                        )}
                      >
                        {t(`report.severities.${issue.severity}`)}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-ink-2">
                      {t.has(`report.checks.${issue.check}`)
                        ? t(`report.checks.${issue.check}`)
                        : issue.check}
                    </td>
                    <td className="py-2 pr-4">{issue.message}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{issue.count}</td>
                    <td className="py-2 tabular-nums text-ink-2">{issue.rows.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <form action={saveMapping}>
        <input type="hidden" name="importId" value={data.id} />
        <fieldset disabled={closed} className="contents">
          <section
            aria-labelledby="mapping-title"
            className="mb-6 rounded-lg border border-line bg-surface p-4 sm:p-6"
          >
            <h2 id="mapping-title" className="mb-3 font-condensed text-lg font-semibold">
              {t("mapping.title")}
            </h2>
            {missing.length > 0 ? (
              <p className="mb-3 text-sm font-medium text-ink">
                {t("mapping.missing", { fields: missing.map((f) => f.name).join(", ") })}
              </p>
            ) : null}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs text-ink-3">
                  <tr>
                    <th scope="col" className="py-2 pr-4 font-medium">
                      {t("mapping.column")}
                    </th>
                    <th scope="col" className="py-2 pr-4 font-medium">
                      {t("mapping.sample")}
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      {t("mapping.field")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.file_columns.map((column, i) => (
                    <tr key={column} className="border-b border-line last:border-0">
                      <th scope="row" className="py-2 pr-4 font-medium">
                        {column}
                        <input type="hidden" name={`colname.${i}`} value={column} />
                      </th>
                      <td className="max-w-40 truncate py-2 pr-4 text-ink-2">
                        {firstSample[column] ?? ""}
                      </td>
                      <td className="py-2">
                        <select
                          name={`col.${i}`}
                          aria-label={`${t("mapping.field")}: ${column}`}
                          defaultValue={data.columns[column] ?? ""}
                          className="min-h-11 w-full min-w-44 rounded-md border border-line bg-surface px-2"
                        >
                          <option value="">{t("mapping.ignore")}</option>
                          {data.fields.map((f) => (
                            <option key={f.name} value={f.name}>
                              {f.name}
                              {f.required ? ` (${t("mapping.required")})` : ""}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {data.teams.length > 0 ? (
            <section
              aria-labelledby="teams-title"
              className="mb-6 rounded-lg border border-line bg-surface p-4 sm:p-6"
            >
              <h2 id="teams-title" className="mb-1 font-condensed text-lg font-semibold">
                {t("mapping.teamsTitle")}
              </h2>
              <p className="mb-3 text-sm text-ink-2">{t("mapping.teamsHelp")}</p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm" data-testid="teams">
                  <thead className="border-b border-line text-xs text-ink-3">
                    <tr>
                      <th scope="col" className="py-2 pr-4 font-medium">
                        {t("mapping.team")}
                      </th>
                      <th scope="col" className="py-2 pr-4 font-medium">
                        {t("mapping.match")}
                      </th>
                      <th scope="col" className="py-2 text-right font-medium">
                        {t("mapping.score")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.teams.map((team, i) => {
                      const suggested = team.suggested ? optionById.get(team.suggested) : undefined;
                      return (
                        <tr key={team.name} className="border-b border-line last:border-0">
                          <th scope="row" className="py-2 pr-4 font-medium">
                            {team.name}
                            <input type="hidden" name={`teamname.${i}`} value={team.name} />
                            <input
                              type="hidden"
                              name={`teamcurrent.${i}`}
                              value={team.team_id ?? ""}
                            />
                            <span className="block text-xs font-normal text-ink-3">
                              {team.confirmed
                                ? team.manual
                                  ? t("mapping.manual")
                                  : t("mapping.auto")
                                : t("mapping.needsConfirmation")}
                            </span>
                          </th>
                          <td className="py-2 pr-4">
                            <select
                              name={`team.${i}`}
                              aria-label={`${t("mapping.match")}: ${team.name}`}
                              defaultValue={team.team_id ?? ""}
                              className={cn(
                                "min-h-11 w-full min-w-48 rounded-md border bg-surface px-2",
                                team.confirmed ? "border-line" : "border-accent",
                              )}
                            >
                              <option value="">{t("mapping.notSelected")}</option>
                              {data.team_options.map((o) => (
                                <option key={o.id} value={o.id}>
                                  {o.code} · {o.name}
                                </option>
                              ))}
                            </select>
                            {!team.confirmed && suggested ? (
                              <span className="mt-1 block text-xs text-ink-3">
                                {t("mapping.suggestion", {
                                  team: `${suggested.code} · ${suggested.name}`,
                                })}
                              </span>
                            ) : null}
                          </td>
                          <td className="py-2 text-right tabular-nums">
                            {format.number(team.score, { style: "percent" })}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {closed ? null : (
            <button
              type="submit"
              className="mb-8 min-h-11 rounded-md border border-pri px-5 text-sm font-semibold text-pri hover:bg-pri/5 focus-visible:outline-2 focus-visible:outline-focus"
            >
              {t("mapping.save")}
            </button>
          )}
        </fieldset>
      </form>

      <section
        aria-labelledby="commit-title"
        className="rounded-lg border border-line bg-surface p-4 sm:p-6"
      >
        <h2 id="commit-title" className="mb-3 font-condensed text-lg font-semibold">
          {t("commit.title")}
        </h2>
        {data.result ? (
          <dl
            className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3"
            data-testid="result"
          >
            {Object.entries(data.result).map(([key, value]) => (
              <div key={key}>
                <dt className="text-ink-3">
                  {t.has(`commit.resultKeys.${key}`) ? t(`commit.resultKeys.${key}`) : key}
                </dt>
                <dd className="font-condensed text-xl font-semibold tabular-nums">
                  {String(value)}
                </dd>
              </div>
            ))}
            {data.committed_at ? (
              <div>
                <dt className="text-ink-3">{t("commit.committedAt")}</dt>
                <dd className="tabular-nums">
                  {format.dateTime(new Date(data.committed_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </dd>
              </div>
            ) : null}
          </dl>
        ) : (
          <form action={commitImport} className="flex flex-wrap items-center gap-4">
            <input type="hidden" name="importId" value={data.id} />
            <button
              type="submit"
              disabled={data.status !== "validated"}
              className="min-h-11 rounded-md bg-pri px-5 text-sm font-semibold text-pri-ink focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("commit.submit")}
            </button>
            {data.status !== "validated" ? (
              <p className="text-sm text-ink-2">{t("commit.blocked")}</p>
            ) : null}
          </form>
        )}
      </section>
    </>
  );
}
