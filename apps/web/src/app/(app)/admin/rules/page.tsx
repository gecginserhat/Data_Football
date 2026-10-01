import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { RuleEditor } from "@/components/prep/RuleEditor";
import { getOverview, getRuleSet, getRuleVersions, prepAccess } from "@/lib/prep";
import { LOG_METRICS, metricLabelKey } from "@/lib/prep-display";
import { conditionsOf, type RuleJson } from "@/lib/rules";

export default async function RulesPage() {
  const t = await getTranslations("rules");
  const tAll = await getTranslations();
  const format = await getFormatter();
  const access = await prepAccess();
  if (!access.rules) {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState
          title={tAll("states.forbiddenTitle")}
          description={tAll("states.forbiddenDescription")}
        />
      </>
    );
  }
  const [ruleSet, versions, overview] = await Promise.all([
    getRuleSet(),
    getRuleVersions(),
    getOverview(10),
  ]);
  if (ruleSet.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={ruleSet} />
      </>
    );
  }
  const rules = ruleSet.data.rules as RuleJson[];
  const metrics = new Set<string>(LOG_METRICS);
  for (const r of rules) for (const c of conditionsOf(r.when)) metrics.add(c.metric);
  const metricLabels = Object.fromEntries(
    [...metrics].map((m) => [m, metricLabelKey(m) ? tAll(metricLabelKey(m)) : m]),
  );
  const fixtures =
    overview.status === "ok"
      ? overview.data.upcoming.map(({ fixture: f }) => ({
          id: f.id,
          label: t("fixtureOption", {
            week: f.week ?? 0,
            home: f.home.code,
            away: f.away.code,
          }),
        }))
      : [];

  return (
    <>
      <nav aria-label={tAll("pages.admin.title")} className="mb-2 text-xs text-ink-3">
        <Link href="/admin" className="underline-offset-2 hover:underline">
          {tAll("pages.admin.title")}
        </Link>
      </nav>
      <PageTitle
        sub={
          ruleSet.data.is_default
            ? t("currentDefault", { label: ruleSet.data.label ?? "—" })
            : t("currentClub", {
                version: ruleSet.data.version,
                date: format.dateTime(new Date(ruleSet.data.published_at), {
                  dateStyle: "medium",
                }),
                name: ruleSet.data.published_by?.name ?? "—",
              })
        }
      >
        {t("title")}
      </PageTitle>
      <p className="mb-6 max-w-3xl text-sm text-ink-2">{t("intro")}</p>

      <Section id="rules-edit" title={t("edit")}>
        <RuleEditor
          rules={rules}
          baseVersion={ruleSet.data.version}
          fixtures={fixtures}
          metricLabels={metricLabels}
        />
      </Section>

      <Section id="rules-history" title={t("history")}>
        {versions.status !== "ok" ? (
          <NotLoaded result={versions} />
        ) : (
          <ol className="flex flex-col gap-2 text-sm" data-testid="rule-versions">
            {versions.data.map((v) => (
              <li
                key={`${v.is_default}:${v.version}`}
                className="flex flex-wrap gap-x-3 rounded-md border border-line bg-surface px-3 py-2"
              >
                <span className="font-medium">
                  {v.is_default
                    ? t("defaultVersion", { label: v.label ?? "—" })
                    : t("clubVersion", { version: v.version })}
                </span>
                <span className="text-ink-2 tabular-nums">
                  {format.dateTime(new Date(v.published_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
                {v.published_by ? <span className="text-ink-2">{v.published_by.name}</span> : null}
                {v.message ? <span className="text-ink-3">“{v.message}”</span> : null}
              </li>
            ))}
          </ol>
        )}
      </Section>
    </>
  );
}
