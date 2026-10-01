import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btnPrimary, inputCls } from "@/components/routines/styles";
import { saveLlmSettings } from "@/lib/report-actions";
import { getLlmSettings, reportsAccess } from "@/lib/reports";

type Search = { error?: string; saved?: string };

/** Kulübün LLM brifingi ayarı: açık/kapalı ve aylık sınırlar (SPEC §15, A-76). */
export default async function LlmSettingsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations("llm");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const access = await reportsAccess();
  const crumb = (
    <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
      <Link href="/admin" className="underline-offset-2 hover:underline">
        {t("admin")}
      </Link>
    </nav>
  );
  if (!access.admin) {
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
  const result = await getLlmSettings();
  if (result.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={result} />
      </>
    );
  }
  const { settings, usage, configured } = result.data;
  const number = (n: number) => format.number(n);
  return (
    <>
      {crumb}
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      {search.saved ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t("saved")}
        </p>
      ) : null}
      {!configured ? (
        <p
          className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-2"
          data-testid="llm-not-configured"
        >
          {t("notConfigured")}
        </p>
      ) : null}
      <Section id="llm-usage" title={t("usage")}>
        <dl className="grid gap-3 sm:grid-cols-2" data-testid="llm-usage">
          <div className="rounded-lg border border-line bg-surface p-3">
            <dt className="text-xs text-ink-2">{t("requests")}</dt>
            <dd className="font-condensed text-2xl font-semibold tabular-nums">
              {number(usage.requests)} / {number(settings.monthly_requests)}
            </dd>
          </div>
          <div className="rounded-lg border border-line bg-surface p-3">
            <dt className="text-xs text-ink-2">{t("tokens")}</dt>
            <dd className="font-condensed text-2xl font-semibold tabular-nums">
              {number(usage.tokens)} / {number(settings.monthly_tokens)}
            </dd>
          </div>
        </dl>
        <p className="mt-2 text-xs text-ink-3">
          {t("period", {
            start: format.dateTime(new Date(`${usage.period_start}T00:00:00Z`), {
              dateStyle: "long",
              timeZone: "UTC",
            }),
          })}
        </p>
      </Section>
      <Section id="llm-settings" title={t("settings")}>
        <form action={saveLlmSettings} className="flex max-w-md flex-col gap-4">
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              name="enabled"
              defaultChecked={settings.enabled}
              className="size-5"
              data-testid="llm-enabled"
            />
            {t("enabled")}
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("monthlyRequests")}
            <input
              type="number"
              name="monthly_requests"
              min={0}
              max={100000}
              required
              defaultValue={settings.monthly_requests}
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("monthlyTokens")}
            <input
              type="number"
              name="monthly_tokens"
              min={0}
              max={1000000000}
              required
              defaultValue={settings.monthly_tokens}
              className={inputCls}
            />
          </label>
          <p className="text-xs text-ink-3">{t("help")}</p>
          <div>
            <PendingButton className={btnPrimary} pendingLabel={t("saving")} testId="llm-save">
              {t("save")}
            </PendingButton>
          </div>
        </form>
      </Section>
    </>
  );
}
