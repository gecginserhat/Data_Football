import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { RoutePage } from "@/components/RoutePage";
import { canImport } from "@/components/imports/guard";
import { prepAccess } from "@/lib/prep";
import { squadAccess } from "@/lib/squad";

const card =
  "flex min-h-11 flex-col gap-1 rounded-lg border border-line bg-surface p-4 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus";

export default async function Page() {
  const [imports, { rules }, { edit: squad }] = await Promise.all([
    canImport(),
    prepAccess(),
    squadAccess(),
  ]);
  if (!imports && !rules && !squad) return <RoutePage routeKey="admin" />;
  const t = await getTranslations();
  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t("pages.admin.title")}</h1>
      <ul className="mb-6 grid gap-3 sm:grid-cols-2">
        {imports ? (
          <li>
            <Link href="/admin/imports" className={card}>
              <span className="font-condensed text-lg font-semibold">{t("imports.adminLink")}</span>
              <span className="text-sm text-ink-2">{t("imports.adminLinkDescription")}</span>
            </Link>
          </li>
        ) : null}
        {imports ? (
          <li>
            <Link href="/admin/llm" className={card}>
              <span className="font-condensed text-lg font-semibold">{t("llm.adminLink")}</span>
              <span className="text-sm text-ink-2">{t("llm.adminLinkDescription")}</span>
            </Link>
          </li>
        ) : null}
        {squad ? (
          <li>
            <Link href="/admin/squad" className={card}>
              <span className="font-condensed text-lg font-semibold">{t("squad.adminLink")}</span>
              <span className="text-sm text-ink-2">{t("squad.adminLinkDescription")}</span>
            </Link>
          </li>
        ) : null}
        {imports ? (
          <li>
            <Link href="/admin/privacy" className={card}>
              <span className="font-condensed text-lg font-semibold">{t("privacy.adminLink")}</span>
              <span className="text-sm text-ink-2">{t("privacy.adminLinkDescription")}</span>
            </Link>
          </li>
        ) : null}
        {rules ? (
          <li>
            <Link href="/admin/rules" className={card}>
              <span className="font-condensed text-lg font-semibold">{t("rules.adminLink")}</span>
              <span className="text-sm text-ink-2">{t("rules.adminLinkDescription")}</span>
            </Link>
          </li>
        ) : null}
      </ul>
      <EmptyState
        title={t("pages.admin.emptyTitle")}
        description={t("pages.admin.emptyDescription")}
      />
    </>
  );
}
