import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { btn, inputCls } from "@/components/routines/styles";
import { listAudit } from "@/lib/users";

type Search = { before?: string; action?: string };

/** Süzgeçteki eylem grupları; değer, denetim kaydındaki eylem adının ön ekidir. */
const GROUPS = [
  "member.",
  "invite.",
  "privacy.",
  "consent.",
  "wellness.",
  "session.",
  "squad.",
  "routine.",
  "rule_set.",
  "plan",
  "import.",
  "report.",
  "briefing.",
  "llm.",
  "video.",
  "clip.",
  "tagging_session.",
  "marking.",
  "assignments.",
  "keys.",
] as const;

function details(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return "";
  return Object.entries(value)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" · ");
}

/** Denetim kaydı (SPEC §10 `audit_log`, §12.1). Yeniden eskiye, 50'şer kayıt. Yalnız yönetici. */
export default async function AuditPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations();
  const format = await getFormatter();
  const before = Number.parseInt(search.before ?? "", 10);
  const action = GROUPS.find((g) => g === search.action);
  const page = await listAudit(Number.isFinite(before) && before > 0 ? before : undefined, action);
  const crumb = (
    <nav aria-label={t("audit.breadcrumb")} className="mb-2 text-xs text-ink-3">
      <Link href="/admin" className="underline-offset-2 hover:underline">
        {t("users.admin")}
      </Link>
    </nav>
  );
  if (page.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("audit.title")}</PageTitle>
        <NotLoaded result={page} />
      </>
    );
  }
  const when = (iso: string) =>
    format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });
  const label = (name: string) =>
    t.has(`audit.actions.${name}`) ? t(`audit.actions.${name}`) : name;
  const next = page.data.next_before;

  return (
    <>
      {crumb}
      <PageTitle sub={t("audit.subtitle")}>{t("audit.title")}</PageTitle>
      <form method="get" className="mb-4 flex flex-wrap items-end gap-2" role="search">
        <label className="flex flex-col gap-1 text-sm">
          {t("audit.filter")}
          <select name="action" defaultValue={action ?? ""} className={inputCls}>
            <option value="">{t("audit.all")}</option>
            {GROUPS.map((g) => (
              <option key={g} value={g}>
                {t(`audit.groups.${g.replace(/\.$/, "")}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className={btn}>
          {t("audit.apply")}
        </button>
      </form>
      {page.data.items.length === 0 ? (
        <EmptyState title={t("audit.emptyTitle")} description={t("audit.empty")} />
      ) : (
        <div
          className="overflow-x-auto rounded-lg border border-line bg-surface"
          role="region"
          aria-label={t("audit.title")}
          tabIndex={0}
        >
          <table className="w-full min-w-[44rem] text-left text-sm" data-testid="audit-table">
            <thead className="border-b border-line text-xs text-ink-3">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t("audit.at")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("audit.actor")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("audit.action")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("audit.details")}
                </th>
              </tr>
            </thead>
            <tbody>
              {page.data.items.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-line align-top last:border-0"
                  data-testid="audit-row"
                  data-action={item.action}
                >
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">{when(item.at)}</td>
                  <td className="px-3 py-2">
                    {item.actor_name ??
                      (item.actor_id ? t("audit.formerMember") : t("audit.system"))}
                  </td>
                  <td className="px-3 py-2">
                    {label(item.action)}
                    <span className="block text-xs text-ink-3">{item.action}</span>
                  </td>
                  <td className="break-all px-3 py-2 text-xs text-ink-2">
                    {[
                      item.before && Object.keys(item.before).length > 0
                        ? `${t("audit.before")}: ${details(item.before)}`
                        : "",
                      details(item.after),
                    ]
                      .filter(Boolean)
                      .join(" → ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav aria-label={t("audit.pages")} className="mt-4 flex flex-wrap gap-2">
        {search.before ? (
          <Link href={action ? `/admin/audit?action=${action}` : "/admin/audit"} className={btn}>
            {t("audit.newest")}
          </Link>
        ) : null}
        {next ? (
          <Link
            href={`/admin/audit?before=${next}${action ? `&action=${action}` : ""}`}
            className={btn}
            data-testid="audit-older"
          >
            {t("audit.older")}
          </Link>
        ) : null}
      </nav>
    </>
  );
}
