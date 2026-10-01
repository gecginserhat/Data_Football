import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("states");
  return (
    <main className="mx-auto max-w-lg p-6">
      <EmptyState
        title={t("notFoundTitle")}
        description={t("notFoundDescription")}
        action={
          <Link
            href="/"
            className="inline-flex min-h-11 items-center rounded-md bg-pri px-4 text-sm text-pri-ink"
          >
            {t("backHome")}
          </Link>
        }
      />
    </main>
  );
}
