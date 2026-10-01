"use client";

import { cn } from "@kurgu/ui";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useActionState, useEffect } from "react";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { ruleSetAction, type RulesState } from "@/lib/prep-actions";
import { OP_SYMBOL } from "@/lib/prep-display";
import { conditionsOf, isEditable, isRankOp, type RuleJson } from "@/lib/rules";

const AREAS = ["attack", "defense", "balance", "season"] as const;

export interface FixtureOption {
  id: string;
  label: string;
}

/**
 * Kural seti düzenleyicisi (A-51): eşik, öncelik, açık/kapalı. Taslak bir maçta denenir
 * (kaydetmez), sonra yeni kulüp sürümü olarak yayımlanır.
 */
export function RuleEditor({
  rules,
  baseVersion,
  fixtures,
  metricLabels,
}: {
  rules: RuleJson[];
  baseVersion: number;
  fixtures: FixtureOption[];
  metricLabels: Record<string, string>;
}) {
  const t = useTranslations("rules");
  const tPrep = useTranslations("prep");
  const router = useRouter();
  const [state, action, pending] = useActionState<RulesState, FormData>(ruleSetAction, {
    status: "idle",
  });
  useEffect(() => {
    if (state.status === "published") router.refresh();
  }, [state, router]);

  return (
    <form action={action} className="flex flex-col gap-6" data-testid="rule-editor">
      <input type="hidden" name="rules" value={JSON.stringify(rules)} />
      <input type="hidden" name="baseVersion" value={baseVersion} />
      {AREAS.map((area) => {
        const inArea = rules.filter((r) => r.area === area);
        if (!inArea.length) return null;
        return (
          <fieldset key={area} className="flex flex-col gap-2">
            <legend className="mb-2 font-condensed text-lg font-semibold">
              {tPrep(`area.${area}`)}
            </legend>
            {inArea.map((rule) => (
              <div
                key={rule.id}
                className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
                data-rule={rule.id}
              >
                <input type="hidden" name={`present:${rule.id}`} value="1" />
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex min-h-11 items-center gap-2 text-sm font-medium">
                    <input
                      type="checkbox"
                      name={`enabled:${rule.id}`}
                      defaultChecked={rule.enabled !== false}
                      className="size-5"
                    />
                    <span>{rule.title}</span>
                  </label>
                  <span className="text-xs text-ink-3">{rule.id}</span>
                  <label className="ml-auto flex items-center gap-2 text-xs text-ink-2">
                    {t("priority")}
                    <input
                      type="number"
                      name={`priority:${rule.id}`}
                      min={1}
                      max={9}
                      step={1}
                      defaultValue={rule.priority}
                      className={cn(inputCls, "w-16")}
                    />
                  </label>
                </div>
                <ul className="flex flex-col gap-1 text-sm">
                  {conditionsOf(rule.when).map((c, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2">
                      <span className="text-ink-3">{tPrep(`subject.${c.subject}`)}</span>
                      <span>{metricLabels[c.metric] ?? c.metric}</span>
                      <span className="text-ink-2">
                        {isRankOp(c.op)
                          ? t("rankOp", { op: OP_SYMBOL[c.op] ?? c.op })
                          : (OP_SYMBOL[c.op] ?? c.op)}
                      </span>
                      {isEditable(c) ? (
                        <input
                          type="number"
                          name={`value:${rule.id}:${i}`}
                          defaultValue={c.value as number}
                          step={isRankOp(c.op) ? 1 : "any"}
                          min={isRankOp(c.op) ? 1 : undefined}
                          aria-label={t("threshold", {
                            metric: metricLabels[c.metric] ?? c.metric,
                          })}
                          className={cn(inputCls, "w-24 tabular-nums")}
                        />
                      ) : (
                        <span className="tabular-nums">{String(c.value ?? "")}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </fieldset>
        );
      })}

      <div className="sticky bottom-0 flex flex-col gap-3 rounded-lg border border-line bg-surface p-3 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            {t("dryRunFixture")}
            <select name="fixtureId" className={inputCls} defaultValue={fixtures[0]?.id}>
              {fixtures.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            name="intent"
            value="preview"
            className={btn}
            disabled={pending || fixtures.length === 0}
            data-testid="dry-run"
          >
            {t("dryRun")}
          </button>
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-ink-2">
            {t("message")}
            <input name="message" maxLength={200} className={inputCls} />
          </label>
          <button
            type="submit"
            name="intent"
            value="publish"
            className={btnPrimary}
            disabled={pending}
            data-testid="publish-rules"
          >
            {t("publish")}
          </button>
        </div>
        <Result state={state} />
      </div>
    </form>
  );
}

function Result({ state }: { state: RulesState }) {
  const t = useTranslations("rules");
  const tPrep = useTranslations("prep");
  if (state.status === "idle") return null;
  if (state.status === "published") {
    return (
      <p role="status" className="text-sm text-pos">
        {t("published", { version: state.version })}
      </p>
    );
  }
  if (state.status === "unchanged") {
    return (
      <p role="status" className="text-sm text-ink-2">
        {t("unchanged")}
      </p>
    );
  }
  if (state.status === "conflict") {
    return (
      <p role="alert" className="text-sm text-neg">
        {t("conflict", { version: state.currentVersion ?? "?" })}
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className="text-sm text-neg">
        <p>{t("error", { code: state.code })}</p>
        {state.details.length ? (
          <ul className="list-disc pl-5 text-xs">
            {state.details.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  const fired = state.results.filter((r) => r.status === "fired");
  return (
    <div role="status" className="flex flex-col gap-2" data-testid="dry-run-results">
      <p className="text-sm font-medium">
        {t("dryRunSummary", {
          fixture: state.fixtureLabel,
          fired: fired.length,
          shown: state.results.filter((r) => r.shown).length,
        })}
      </p>
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-3">
            <tr>
              <th scope="col" className="py-1 pr-2 font-medium">
                {t("col.rule")}
              </th>
              <th scope="col" className="py-1 pr-2 font-medium">
                {t("col.status")}
              </th>
              <th scope="col" className="py-1 pr-2 font-medium">
                {t("col.confidence")}
              </th>
              <th scope="col" className="py-1 font-medium">
                {t("col.title")}
              </th>
            </tr>
          </thead>
          <tbody>
            {state.results.map((r, i) => (
              <tr
                key={`${r.rule_id}:${r.routine?.id ?? i}`}
                className="border-t border-line align-top"
                data-rule={r.rule_id}
                data-status={r.status}
              >
                <td className="py-1 pr-2">{r.rule_id}</td>
                <td className="py-1 pr-2">
                  {t(`ruleStatus.${r.status}`)}
                  {r.shown ? ` · ${t("shown")}` : ""}
                </td>
                <td className="py-1 pr-2">
                  {r.confidence ? tPrep(`confidence.${r.confidence}`) : "—"}
                </td>
                <td className="py-1">
                  {r.title}
                  {r.routine ? <span className="text-ink-3"> · {r.routine.name}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
