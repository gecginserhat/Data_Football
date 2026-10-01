import type { Schemas } from "@kurgu/api-client";
import { EmptyState, ErrorState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { ErrorNotice } from "@/components/imports/ErrorNotice";
import { ImportStatus } from "@/components/imports/ImportStatus";
import { canImport, Forbidden } from "@/components/imports/guard";
import { apiClient } from "@/lib/api";
import { uploadImport } from "@/lib/imports";

const KINDS = ["team_season_stats", "events"] as const;

type Loaded =
  | { ok: true; seasons: Schemas["SeasonOut"][]; imports: Schemas["ImportSummary"][] }
  | { ok: false };

async function load(): Promise<Loaded> {
  try {
    const client = await apiClient();
    const [seasons, imports] = await Promise.all([
      client.GET("/api/v1/seasons", { params: { query: { limit: 100 } } }),
      client.GET("/api/v1/imports"),
    ]);
    if (!seasons.data || !imports.data) return { ok: false };
    return { ok: true, seasons: seasons.data.items, imports: imports.data };
  } catch {
    return { ok: false };
  }
}

export default async function ImportsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if (!(await canImport())) return <Forbidden />;
  const t = await getTranslations("imports");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const { error } = await searchParams;
  const data = await load();

  return (
    <>
      <h1 className="mb-2 font-condensed text-2xl font-semibold">{t("title")}</h1>
      <p className="mb-6 max-w-prose text-sm text-ink-2">{t("description")}</p>
      <ErrorNotice code={error} />

      {!data.ok ? (
        <ErrorState
          title={tStates("errorTitle")}
          description={tStates("errorDescription")}
          retryLabel={tStates("retry")}
        />
      ) : (
        <>
          <section
            aria-labelledby="upload-title"
            className="mb-8 rounded-lg border border-line bg-surface p-4 sm:p-6"
          >
            <h2 id="upload-title" className="mb-4 font-condensed text-lg font-semibold">
              {t("upload.title")}
            </h2>
            {data.seasons.length === 0 ? (
              <p className="text-sm text-ink-2">{t("upload.noSeasons")}</p>
            ) : (
              <form action={uploadImport} className="grid gap-4 md:grid-cols-2">
                <input type="hidden" name="idempotencyKey" value={crypto.randomUUID()} />
                <fieldset className="md:col-span-2">
                  <legend className="mb-2 text-sm font-medium">{t("upload.kind")}</legend>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {KINDS.map((kind, i) => (
                      <label
                        key={kind}
                        className="flex cursor-pointer gap-3 rounded-md border border-line p-3 has-[:checked]:border-pri has-[:checked]:bg-pri/5"
                      >
                        <input
                          type="radio"
                          name="kind"
                          value={kind}
                          defaultChecked={i === 0}
                          className="mt-1 size-4 accent-[var(--pri)]"
                        />
                        <span>
                          <span className="block text-sm font-medium">{t(`kinds.${kind}`)}</span>
                          <span className="block text-xs text-ink-3">{t(`kindHelp.${kind}`)}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <label className="flex flex-col gap-1 text-sm font-medium">
                  {t("upload.season")}
                  <select
                    name="seasonId"
                    required
                    className="min-h-11 rounded-md border border-line bg-surface px-3 font-normal"
                  >
                    {data.seasons.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.competition.name} · {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm font-medium">
                  {t("upload.file")}
                  <input
                    type="file"
                    name="file"
                    required
                    accept=".csv,.tsv,.txt,.xlsx,.xlsm"
                    className="min-h-11 rounded-md border border-line bg-surface px-3 py-2 font-normal file:mr-3 file:rounded file:border-0 file:bg-bg file:px-3 file:py-1"
                  />
                </label>
                <div className="md:col-span-2">
                  <button
                    type="submit"
                    className="min-h-11 rounded-md bg-pri px-5 text-sm font-semibold text-brand-ink focus-visible:outline-2 focus-visible:outline-focus"
                  >
                    {t("upload.submit")}
                  </button>
                </div>
              </form>
            )}
          </section>

          <section aria-labelledby="list-title">
            <h2 id="list-title" className="mb-3 font-condensed text-lg font-semibold">
              {t("list.title")}
            </h2>
            {data.imports.length === 0 ? (
              <EmptyState title={t("list.empty")} description={t("list.emptyDescription")} />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-line bg-surface">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-line text-xs text-ink-3">
                    <tr>
                      <th scope="col" className="px-4 py-2 font-medium">
                        {t("list.file")}
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        {t("list.kind")}
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        {t("list.status")}
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        {t("list.created")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.imports.map((item) => (
                      <tr key={item.id} className="border-b border-line last:border-0">
                        <td className="px-4 py-2">
                          <Link
                            href={`/admin/imports/${item.id}`}
                            className="font-medium text-pri underline-offset-2 hover:underline"
                          >
                            {item.filename}
                          </Link>
                        </td>
                        <td className="px-4 py-2 text-ink-2">{t(`kinds.${item.kind}`)}</td>
                        <td className="px-4 py-2">
                          <ImportStatus status={item.status} />
                        </td>
                        <td className="px-4 py-2 tabular-nums text-ink-2">
                          {format.dateTime(new Date(item.created_at), {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
