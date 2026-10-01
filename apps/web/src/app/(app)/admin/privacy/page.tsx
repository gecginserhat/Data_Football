import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { getPrivacySettings, listPrivacyRequests } from "@/lib/privacy";
import { decideRequest, updateRetention } from "@/lib/privacy-actions";

type Search = { error?: string; saved?: string };

/** KVKK yönetimi: kişisel veri envanteri, saklama süreleri, veri sahibi talepleri (ADR-0019). */
export default async function PrivacyAdminPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const search = await searchParams;
  const t = await getTranslations("privacy");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const [settings, requests] = await Promise.all([getPrivacySettings(), listPrivacyRequests()]);
  const crumb = (
    <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
      <Link href="/admin" className="underline-offset-2 hover:underline">
        {t("admin")}
      </Link>
    </nav>
  );
  if (settings.status === "forbidden") {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  if (settings.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={settings} />
      </>
    );
  }
  const data = settings.data;
  const when = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const message = search.error
    ? t.has(`errors.${search.error}`)
      ? t(`errors.${search.error}`)
      : t("errors.generic", { code: search.error })
    : null;

  return (
    <>
      {crumb}
      <PageTitle sub={t("subtitle", { region: data.data_region.toUpperCase() })}>
        {t("title")}
      </PageTitle>
      {message ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {message}
        </p>
      ) : null}
      {search.saved && t.has(`saved.${search.saved}`) ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t(`saved.${search.saved}`)}
        </p>
      ) : null}

      <Section id="requests" title={t("requests.title")}>
        {requests.status !== "ok" ? (
          <NotLoaded result={requests} />
        ) : requests.data.length === 0 ? (
          <EmptyState title={t("requests.emptyTitle")} description={t("requests.empty")} />
        ) : (
          <ul className="flex flex-col gap-2" data-testid="privacy-requests">
            {requests.data.map((r) => (
              <li
                key={r.id}
                className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4"
                data-testid="privacy-request"
                data-status={r.status}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-medium">
                    {t("requests.erasure")} · {r.player_name}
                  </p>
                  <span className="rounded border border-line px-2 py-0.5 text-xs">
                    {t(`requests.status.${r.status}`)}
                  </span>
                </div>
                <p className="text-sm text-ink-2">
                  {t("requests.created", { date: when(r.created_at) })}
                  {r.reason ? ` · ${r.reason}` : ""}
                </p>
                {r.status === "open" ? (
                  <form action={decideRequest} className="flex flex-wrap items-end gap-2">
                    <input type="hidden" name="requestId" value={r.id} />
                    <label className="flex flex-col gap-1 text-sm">
                      {t("requests.note")}
                      <input name="note" maxLength={500} className={inputCls} />
                    </label>
                    <PendingButton
                      className={btnPrimary}
                      pendingLabel={t("pending")}
                      name="decision"
                      value="approve"
                      testId="request-approve"
                    >
                      {t("requests.approve")}
                    </PendingButton>
                    <PendingButton
                      className={btn}
                      pendingLabel={t("pending")}
                      name="decision"
                      value="reject"
                      testId="request-reject"
                    >
                      {t("requests.reject")}
                    </PendingButton>
                    <p className="basis-full text-xs text-ink-3">{t("requests.approveNote")}</p>
                  </form>
                ) : r.note ? (
                  <p className="text-sm text-ink-2">{r.note}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="retention" title={t("retention.title")}>
        <form
          action={updateRetention}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
          data-testid="retention-form"
        >
          {(
            [
              ["wellness_days", 30],
              ["loads_days", 30],
              ["audit_days", 365],
            ] as const
          ).map(([key, min]) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              {t(`retention.${key}`)}
              <input
                type="number"
                name={key}
                min={min}
                max={3650}
                required
                defaultValue={data.retention[key]}
                className={`${inputCls} w-32 tabular-nums`}
              />
            </label>
          ))}
          <PendingButton className={btnPrimary} pendingLabel={t("pending")} testId="retention-save">
            {t("retention.save")}
          </PendingButton>
          <p className="basis-full text-xs text-ink-3">{t("retention.note")}</p>
        </form>
      </Section>

      <Section id="inventory" title={t("inventory.title")}>
        <p className="mb-3 max-w-prose text-sm text-ink-2">{t("inventory.description")}</p>
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[48rem] text-left text-sm" data-testid="privacy-inventory">
            <thead className="border-b border-line text-xs text-ink-3">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t("inventory.item")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("inventory.fields")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("inventory.purpose")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("inventory.basis")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("inventory.retention")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.inventory.map((item) => (
                <tr key={item.key} className="border-b border-line align-top last:border-0">
                  <th scope="row" className="px-3 py-2 font-medium">
                    {item.title}
                    <span className="mt-1 flex flex-wrap gap-1">
                      {item.special_category ? (
                        <span className="rounded border border-neg px-1.5 text-[11px] text-ink">
                          {t("inventory.special")}
                        </span>
                      ) : null}
                      {item.encrypted ? (
                        <span className="rounded border border-line px-1.5 text-[11px]">
                          {t("inventory.encrypted")}
                        </span>
                      ) : null}
                    </span>
                  </th>
                  <td className="px-3 py-2">{item.fields.join(", ")}</td>
                  <td className="px-3 py-2">
                    {item.purpose}
                    <span className="block text-xs text-ink-3">{item.subjects}</span>
                  </td>
                  <td className="px-3 py-2">{item.legal_basis}</td>
                  <td className="px-3 py-2">
                    {item.retention_days
                      ? t("inventory.days", { days: item.retention_days })
                      : item.retention}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-3">{t("inventory.legal")}</p>
      </Section>
    </>
  );
}
