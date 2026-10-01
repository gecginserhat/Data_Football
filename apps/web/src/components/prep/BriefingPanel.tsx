import { EmptyState } from "@kurgu/ui";
import { useFormatter, useTranslations } from "next-intl";
import { NotLoaded, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn } from "@/components/routines/styles";
import type { Loaded } from "@/lib/analysis";
import { generateBriefing } from "@/lib/report-actions";
import type { Briefing } from "@/lib/reports";

const KNOWN_ERRORS = new Set([
  "briefing-unverified",
  "briefing-error",
  "llm-disabled",
  "llm-budget-exceeded",
  "llm-not-configured",
]);

/**
 * Kanıta bağlı brifing (SPEC §15, ADR-0013). Yalnız sayıları kayıtla eşleşen metin gösterilir;
 * denetimden geçmeyen metin kullanıcıya hiç gelmez.
 */
export function BriefingPanel({
  briefing,
  fixtureId,
  canBrief,
  error,
}: {
  briefing: Loaded<Briefing>;
  fixtureId: string;
  canBrief: boolean;
  error?: string;
}) {
  const t = useTranslations("prep.briefing");
  const format = useFormatter();
  const current =
    briefing.status === "ok" && briefing.data.status === "verified" ? briefing.data : null;
  return (
    <Section
      id="briefing"
      title={t("title")}
      action={
        canBrief ? (
          <form action={generateBriefing}>
            <input type="hidden" name="fixtureId" value={fixtureId} />
            <PendingButton
              className={btn}
              pendingLabel={t("generating")}
              testId="generate-briefing"
            >
              {current ? t("regenerate") : t("generate")}
            </PendingButton>
          </form>
        ) : null
      }
    >
      {error ? (
        <p
          role="alert"
          data-testid="briefing-error"
          className="mb-3 rounded-md border border-neg px-3 py-2 text-sm text-neg"
        >
          {KNOWN_ERRORS.has(error) ? t(`errors.${error}`) : t("errors.generic", { code: error })}
        </p>
      ) : null}
      {briefing.status !== "ok" ? (
        <NotLoaded result={briefing} />
      ) : current?.text ? (
        <article className="rounded-lg border border-line bg-surface p-4" data-testid="briefing">
          <div className="flex flex-col gap-3 text-sm leading-relaxed">
            {current.text.split(/\n{2,}/).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
          <p
            className="mt-3 border-t border-line pt-2 text-xs text-ink-3"
            data-testid="briefing-label"
          >
            {t("label", { count: current.numbers })}
            {current.created_at
              ? ` · ${format.dateTime(new Date(current.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}`
              : ""}
          </p>
        </article>
      ) : (
        <EmptyState title={t("emptyTitle")} description={canBrief ? t("empty") : t("emptyRead")} />
      )}
    </Section>
  );
}
