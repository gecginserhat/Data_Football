import { cn, SampleSizeBadge } from "@kurgu/ui";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import type { Evidence, Recommendation } from "@/lib/prep";
import { decideRecommendation } from "@/lib/prep-actions";
import { formatEvidence, metricLabelKey } from "@/lib/prep-display";

const AREA_CLS: Record<string, string> = {
  attack: "border-pos text-pos",
  defense: "border-def text-def",
  balance: "border-ink-3 text-ink-2",
  season: "border-accent text-ink",
};

export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium",
        className ?? "border-line text-ink-2",
      )}
    >
      {children}
    </span>
  );
}

/** Güven: harf ve metinle (renk tek başına anlam taşımaz, SPEC §13.3). */
export function ConfidenceChip({ level }: { level: string }) {
  const t = useTranslations("prep.confidence");
  const bars = level === "high" ? "●●●" : level === "medium" ? "●●○" : "●○○";
  return (
    <Chip className="border-line text-ink-2">
      <span aria-hidden className="mr-1 tracking-tighter">
        {bars}
      </span>
      {t(level)}
    </Chip>
  );
}

export function EvidenceTable({ rows }: { rows: Evidence[] }) {
  const t = useTranslations();
  const format = useFormatter();
  const label = (metric: string) => {
    const key = metricLabelKey(metric);
    return key ? t(key) : metric;
  };
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-ink-3">
        <tr>
          <th scope="col" className="py-1 pr-2 font-medium">
            {t("prep.evidence.metric")}
          </th>
          <th scope="col" className="py-1 pr-2 text-right font-medium">
            {t("prep.evidence.value")}
          </th>
          <th scope="col" className="py-1 pr-2 text-right font-medium">
            {t("prep.evidence.rank")}
          </th>
          <th scope="col" className="py-1 pr-2 text-right font-medium">
            {t("prep.evidence.leagueMean")}
          </th>
          <th scope="col" className="py-1 font-medium">
            {t("prep.evidence.notes")}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((e) => (
          <tr key={`${e.subject}:${e.metric}`} className="border-t border-line align-top">
            <td className="py-1 pr-2">
              <span className="block text-ink-3">{t(`prep.subject.${e.subject}`)}</span>
              {label(e.metric)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {formatEvidence(format.number, e.metric, e.value)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {e.rank && e.teams
                ? t("prep.evidence.rankOf", { rank: e.rank, teams: e.teams })
                : "—"}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {e.league_mean !== null
                ? formatEvidence(format.number, e.metric, e.league_mean)
                : "—"}
            </td>
            <td className="py-1">
              <span className="inline-flex flex-wrap gap-1">
                {e.low_sample ? (
                  // API'nin "az veri" kararı esastır; rozet her durumda çizilsin diye maç 0.
                  <SampleSizeBadge label={t("analysis.badges.lowSample")} matches={0} />
                ) : null}
                {e.indirect ? <Chip>{t("analysis.badges.indirect")}</Chip> : null}
                {e.approx ? <Chip>{t("analysis.badges.approx")}</Chip> : null}
                {e.matches !== null && !e.low_sample ? (
                  <span className="text-ink-3">
                    {t("prep.evidence.matches", { count: Math.round(e.matches) })}
                  </span>
                ) : null}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RecommendationCard({
  rec,
  fixtureId,
  canDecide,
}: {
  rec: Recommendation;
  fixtureId: string;
  canDecide: boolean;
}) {
  const t = useTranslations("prep");
  const format = useFormatter();
  const decided = rec.status !== "suggested";
  return (
    <article
      id={`rec-${rec.id}`}
      data-testid="recommendation"
      data-rule={rec.rule_id}
      data-status={rec.status}
      className={cn(
        "flex scroll-mt-20 flex-col gap-2 rounded-lg border bg-surface p-4",
        rec.status === "accepted" ? "border-pos" : "border-line",
        rec.status === "rejected" && "opacity-75",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip className={AREA_CLS[rec.area]}>{t(`area.${rec.area}`)}</Chip>
        <Chip>{t("priority", { priority: rec.priority })}</Chip>
        <ConfidenceChip level={rec.confidence} />
        {decided ? (
          <Chip
            className={rec.status === "accepted" ? "border-pos text-pos" : "border-neg text-neg"}
          >
            {t(`status.${rec.status}`)}
          </Chip>
        ) : null}
        {!rec.active ? <Chip>{t("inactive")}</Chip> : null}
      </div>
      <h3 className="font-condensed text-lg leading-tight font-semibold">{rec.title}</h3>
      <p className="text-sm text-ink-2">{rec.why}</p>
      <p className="text-sm">
        <span className="font-medium">{t("actionLabel")} </span>
        {rec.action}
      </p>
      <p className="flex flex-wrap gap-x-3 text-xs">
        {rec.template ? (
          <Link
            href="/routines?tab=templates"
            className="text-pri underline-offset-2 hover:underline"
          >
            {t("template", { name: rec.template.name })}
          </Link>
        ) : null}
        {rec.routine ? (
          <Link
            href={`/routines/${rec.routine.id}`}
            className="text-pri underline-offset-2 hover:underline"
          >
            {t("routine", { name: rec.routine.name })}
          </Link>
        ) : null}
      </p>
      <details className="rounded-md border border-line px-3 py-2">
        <summary className="min-h-8 cursor-pointer text-xs font-medium text-ink-2">
          {t("evidence.title", { count: rec.evidence.length })}
        </summary>
        <div className="mt-2 overflow-x-auto">
          <EvidenceTable rows={rec.evidence} />
        </div>
      </details>
      {decided ? (
        <p className="text-xs text-ink-3">
          {t(`decidedBy.${rec.status}`, {
            name: rec.decided_by?.name ?? "—",
            date: rec.decided_at
              ? format.dateTime(new Date(rec.decided_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })
              : "—",
          })}
          {rec.reason ? ` · ${t("reasonLabel")} ${rec.reason}` : null}
        </p>
      ) : null}
      {canDecide ? (
        <div className="flex flex-wrap items-start gap-2">
          {decided ? (
            <form action={decideRecommendation}>
              <input type="hidden" name="fixtureId" value={fixtureId} />
              <input type="hidden" name="recommendationId" value={rec.id} />
              <input type="hidden" name="decision" value="suggested" />
              <button type="submit" className={btn}>
                {t("undo")}
              </button>
            </form>
          ) : (
            <>
              <form action={decideRecommendation}>
                <input type="hidden" name="fixtureId" value={fixtureId} />
                <input type="hidden" name="recommendationId" value={rec.id} />
                <input type="hidden" name="decision" value="accepted" />
                <button type="submit" className={btnPrimary}>
                  {t("accept")}
                </button>
              </form>
              <details className="group">
                <summary className={cn(btn, "cursor-pointer list-none")}>{t("reject")}</summary>
                <form action={decideRecommendation} className="mt-2 flex flex-col gap-2">
                  <input type="hidden" name="fixtureId" value={fixtureId} />
                  <input type="hidden" name="recommendationId" value={rec.id} />
                  <input type="hidden" name="decision" value="rejected" />
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    {t("reasonPrompt")}
                    <textarea
                      name="reason"
                      required
                      maxLength={1000}
                      rows={2}
                      className={cn(inputCls, "py-2")}
                    />
                  </label>
                  <button type="submit" className={btn}>
                    {t("rejectSubmit")}
                  </button>
                </form>
              </details>
            </>
          )}
        </div>
      ) : null}
    </article>
  );
}
