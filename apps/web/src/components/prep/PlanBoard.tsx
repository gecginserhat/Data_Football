import { cn, EmptyState } from "@kurgu/ui";
import { useFormatter, useTranslations } from "next-intl";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import type { Plan, PlanItem, Prep } from "@/lib/prep";
import { addPlanItem, createPlan, deletePlanItem, updatePlanItem } from "@/lib/prep-actions";

type UserRef = Prep["assignees"][number];

function Hidden({ fixtureId, itemId }: { fixtureId: string; itemId?: string }) {
  return (
    <>
      <input type="hidden" name="fixtureId" value={fixtureId} />
      {itemId ? <input type="hidden" name="itemId" value={itemId} /> : null}
    </>
  );
}

export function CreatePlan({ fixtureId, canMark }: { fixtureId: string; canMark: boolean }) {
  const t = useTranslations("prep.plan");
  return (
    <div className="flex flex-col gap-3">
      <EmptyState title={t("emptyTitle")} description={canMark ? t("empty") : t("emptyRead")} />
      {canMark ? (
        <form action={createPlan} className="flex flex-wrap items-end gap-3">
          <Hidden fixtureId={fixtureId} />
          <fieldset className="flex flex-wrap gap-3">
            <legend className="mb-1 text-xs text-ink-2">{t("template")}</legend>
            {(["standard", "congested"] as const).map((tpl) => (
              <label key={tpl} className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="template"
                  value={tpl}
                  defaultChecked={tpl === "standard"}
                  className="size-5"
                />
                <span>
                  {t(`templates.${tpl}`)}
                  <span className="block text-xs text-ink-3">{t(`templateHint.${tpl}`)}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <button type="submit" className={btnPrimary} data-testid="create-plan">
            {t("create")}
          </button>
        </form>
      ) : null}
    </div>
  );
}

function Item({
  item,
  fixtureId,
  canMark,
  assignees,
}: {
  item: PlanItem;
  fixtureId: string;
  canMark: boolean;
  assignees: UserRef[];
}) {
  const t = useTranslations("prep.plan");
  const done = item.status === "done";
  return (
    <li
      id={`item-${item.id}`}
      data-testid="plan-item"
      data-status={item.status}
      className="flex scroll-mt-20 flex-col gap-2 rounded-md border border-line bg-surface p-3"
    >
      <div className="flex items-start gap-3">
        {canMark ? (
          <form action={updatePlanItem}>
            <Hidden fixtureId={fixtureId} itemId={item.id} />
            <input type="hidden" name="status" value={done ? "todo" : "done"} />
            <button
              type="submit"
              aria-label={
                done ? t("markTodo", { title: item.title }) : t("markDone", { title: item.title })
              }
              aria-pressed={done}
              className={cn(
                "flex size-11 shrink-0 items-center justify-center rounded-md border text-lg",
                done ? "border-pos bg-pos text-brand-ink" : "border-line bg-surface",
              )}
            >
              {done ? "✓" : ""}
            </button>
          </form>
        ) : (
          <span aria-hidden className="w-6 shrink-0 pt-0.5 text-center">
            {done ? "✓" : "○"}
          </span>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className={cn("text-sm font-medium", done && "text-ink-3 line-through")}>
            {item.title}
            {done ? <span className="sr-only"> ({t("doneLabel")})</span> : null}
          </p>
          {item.detail ? <p className="text-xs text-ink-2">{item.detail}</p> : null}
          <p className="flex flex-wrap gap-x-2 text-xs text-ink-3">
            {item.recommendation_id ? <span>{t("fromRecommendation")}</span> : null}
            {item.routine ? <span>{t("routine", { name: item.routine.name })}</span> : null}
            {item.done_by ? <span>{t("doneBy", { name: item.done_by.name ?? "—" })}</span> : null}
          </p>
        </div>
      </div>
      {canMark ? (
        <div className="flex items-center gap-2 pl-14">
          <form action={updatePlanItem} className="flex min-w-0 flex-1 items-center gap-2">
            <Hidden fixtureId={fixtureId} itemId={item.id} />
            <label className="flex min-w-0 flex-1">
              <span className="sr-only">{t("assignee")}</span>
              <select
                name="assigneeId"
                defaultValue={item.assignee?.id ?? ""}
                className={cn(inputCls, "w-full min-w-0")}
              >
                <option value="">{t("unassigned")}</option>
                {assignees.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name ?? u.id}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className={btn}>
              {t("assign")}
            </button>
          </form>
          <form action={deletePlanItem}>
            <Hidden fixtureId={fixtureId} itemId={item.id} />
            <button type="submit" className={btn} aria-label={t("remove", { title: item.title })}>
              {t("removeShort")}
            </button>
          </form>
        </div>
      ) : item.assignee ? (
        <p className="pl-9 text-xs text-ink-2">
          {t("assignee")}: {item.assignee.name}
        </p>
      ) : null}
    </li>
  );
}

export function PlanBoard({
  plan,
  fixtureId,
  canMark,
  assignees,
  routines,
}: {
  plan: Plan;
  fixtureId: string;
  canMark: boolean;
  assignees: UserRef[];
  routines: Prep["routines"];
}) {
  const t = useTranslations("prep.plan");
  const format = useFormatter();
  const pct = plan.total ? Math.round((plan.done / plan.total) * 100) : 0;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="flex justify-between text-sm">
          <span>{t(`templates.${plan.template}`)}</span>
          <span className="tabular-nums" data-testid="plan-progress">
            {t("progress", { done: plan.done, total: plan.total })}
          </span>
        </p>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={plan.total}
          aria-valuenow={plan.done}
          aria-label={t("progressLabel")}
          className="h-2 overflow-hidden rounded-full bg-line"
        >
          <div className="h-full bg-pos" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {plan.days.map((day) => {
          const items = plan.items.filter((i) => i.md_code === day.md_code);
          return (
            <li key={day.md_code} className="flex flex-col gap-2" data-md={day.md_code}>
              <h3 className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-condensed text-lg font-semibold">{day.md_code}</span>
                <span className="text-xs text-ink-2 tabular-nums">
                  {day.date
                    ? format.dateTime(new Date(`${day.date}T12:00:00Z`), {
                        weekday: "short",
                        day: "numeric",
                        month: "short",
                        timeZone: "Europe/Istanbul",
                      })
                    : t("dateTbd")}
                </span>
                <span className="text-xs text-ink-3">{day.focus}</span>
              </h3>
              {items.length ? (
                <ul className="flex flex-col gap-2">
                  {items.map((item) => (
                    <Item
                      key={item.id}
                      item={item}
                      fixtureId={fixtureId}
                      canMark={canMark}
                      assignees={assignees}
                    />
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-ink-3">{t("noItems")}</p>
              )}
            </li>
          );
        })}
      </ol>
      {canMark ? (
        <details className="rounded-lg border border-line bg-surface p-3">
          <summary className="cursor-pointer text-sm font-medium">{t("add")}</summary>
          <form action={addPlanItem} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Hidden fixtureId={fixtureId} />
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              {t("day")}
              <select name="mdCode" className={inputCls} defaultValue={plan.days[0]?.md_code}>
                {plan.days.map((d) => (
                  <option key={d.md_code} value={d.md_code}>
                    {d.md_code}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-2 sm:col-span-1 lg:col-span-3">
              {t("title")}
              <input name="title" required maxLength={200} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-2 sm:col-span-2 lg:col-span-4">
              {t("detail")}
              <input name="detail" maxLength={2000} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              {t("assignee")}
              <select name="assigneeId" className={inputCls} defaultValue="">
                <option value="">{t("unassigned")}</option>
                {assignees.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name ?? u.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              {t("routineField")}
              <select name="routineId" className={inputCls} defaultValue="">
                <option value="">{t("noRoutine")}</option>
                {routines.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button type="submit" className={btnPrimary}>
                {t("addSubmit")}
              </button>
            </div>
          </form>
        </details>
      ) : null}
    </div>
  );
}
