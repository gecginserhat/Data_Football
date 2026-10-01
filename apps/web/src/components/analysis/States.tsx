import { EmptyState, ErrorState } from "@kurgu/ui";
import { useTranslations } from "next-intl";
import type { Loaded } from "@/lib/analysis";

/** Veri gelmediğinde gösterilecek durum: yetkisiz, bulunamadı ya da hata (SPEC §13.3). */
export function NotLoaded({ result }: { result: Exclude<Loaded<unknown>, { status: "ok" }> }) {
  const t = useTranslations("states");
  if (result.status === "forbidden") {
    return <EmptyState title={t("forbiddenTitle")} description={t("forbiddenDescription")} />;
  }
  if (result.status === "missing") {
    return <EmptyState title={t("notFoundTitle")} description={t("notFoundDescription")} />;
  }
  return (
    <ErrorState
      title={t("errorTitle")}
      description={t("errorDescription")}
      retryLabel={t("retry")}
    />
  );
}

export function PageTitle({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-1">
      <h1 className="font-condensed text-2xl font-semibold">{children}</h1>
      {sub ? <p className="text-sm text-ink-2">{sub}</p> : null}
    </header>
  );
}

export function Section({
  id,
  title,
  children,
  action,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mb-8">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={id} className="font-condensed text-lg font-semibold">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}
