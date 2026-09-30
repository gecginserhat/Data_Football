import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { RoutePage } from "@/components/RoutePage";
import { canImport } from "@/components/imports/guard";

export default async function Page() {
  if (!(await canImport())) return <RoutePage routeKey="admin" />;
  const t = await getTranslations();
  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t("pages.admin.title")}</h1>
      <ul className="mb-6 grid gap-3 sm:grid-cols-2">
        <li>
          <Link
            href="/admin/imports"
            className="flex min-h-11 flex-col gap-1 rounded-lg border border-line bg-surface p-4 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus"
          >
            <span className="font-condensed text-lg font-semibold">{t("imports.adminLink")}</span>
            <span className="text-sm text-ink-2">{t("imports.adminLinkDescription")}</span>
          </Link>
        </li>
      </ul>
      <EmptyState
        title={t("pages.admin.emptyTitle")}
        description={t("pages.admin.emptyDescription")}
      />
    </>
  );
}
