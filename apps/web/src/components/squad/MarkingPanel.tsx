import { DemoBadge, EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import type { Loaded } from "@/lib/analysis";
import type { Marking, MarkingRow, SquadPlayer, Target } from "@/lib/squad";
import { addTarget, deleteTarget, recomputeMarking, saveMarking } from "@/lib/squad-actions";
import { AerialValue } from "./AerialValue";

/**
 * Duran top markajı (SPEC §7.3, ADR-0015): rakip hedefleri, Macar algoritmasının önerisi, elle
 * düzeltme ve sürümlü kayıt. Öneri her açılışta API'de yeniden hesaplanır.
 */
export async function MarkingPanel({
  marking,
  fixtureId,
  teamId,
  canDecide,
  canEditSquad,
  zonalParam,
  message,
}: {
  marking: Loaded<Marking>;
  fixtureId: string;
  teamId: string;
  canDecide: boolean;
  canEditSquad: boolean;
  /** URL'deki alan oyuncuları; verilmişse seçimler öneriye döner. */
  zonalParam: string | undefined;
  message: string | undefined;
}) {
  const t = await getTranslations("marking");
  const format = await getFormatter();
  if (marking.status !== "ok") {
    return (
      <Section id="marking" title={t("title")}>
        <NotLoaded result={marking} />
      </Section>
    );
  }
  const { targets, squad, suggestion, saved, zonal } = marking.data;
  const byId = new Map(squad.map((p) => [p.id, p]));
  const targetById = new Map(targets.map((x) => [x.id, x]));
  const outfield = squad.filter((p) => p.position !== "GK");
  const zonalSet = new Set(zonal);
  const useSaved = zonalParam === undefined && saved != null;
  const savedRows = new Map((saved?.rows ?? []).map((r) => [r.target_id, r]));
  // Kayıttan sonra eklenen hedefler öneriyle başlar.
  const chosen = (row: MarkingRow) => {
    const stored = useSaved ? savedRows.get(row.target_id) : undefined;
    return stored ? (stored.marker_id ?? null) : row.suggested_marker_id;
  };
  const formKey = `${zonalParam ?? "saved"}-${saved?.version ?? 0}`;
  const demo = squad.some((p) => p.is_demo);

  return (
    <Section
      id="marking"
      title={t("title")}
      action={
        canEditSquad ? (
          <Link href="/admin/squad" className="text-sm text-pri underline-offset-2 hover:underline">
            {t("editSquad")}
          </Link>
        ) : null
      }
    >
      <p className="mb-3 max-w-3xl text-sm text-ink-2">{t("intro")}</p>
      {message ? <Notice code={message} /> : null}

      <h3 className="mb-2 font-condensed text-base font-semibold">{t("targets")}</h3>
      {targets.length === 0 ? (
        <EmptyState title={t("noTargetsTitle")} description={t("noTargets")} />
      ) : (
        <TargetTable targets={targets} fixtureId={fixtureId} canDecide={canDecide} />
      )}
      {canDecide ? (
        <details className="mt-3" open={targets.length === 0}>
          <summary className="min-h-11 cursor-pointer py-2 text-sm text-pri">
            {t("addTarget")}
          </summary>
          <TargetForm fixtureId={fixtureId} teamId={teamId} />
        </details>
      ) : null}

      <h3 className="mb-2 mt-6 flex flex-wrap items-center gap-2 font-condensed text-base font-semibold">
        {t("assignment")}
        {demo ? <DemoBadge label={t("demoSquad")} /> : null}
      </h3>
      {squad.length === 0 ? (
        <EmptyState title={t("noSquadTitle")} description={t("noSquad")} />
      ) : targets.length === 0 ? (
        <p className="text-sm text-ink-3">{t("needTargets")}</p>
      ) : (
        <form key={formKey} action={saveMarking} data-testid="marking-form">
          <input type="hidden" name="fixtureId" value={fixtureId} />
          <input type="hidden" name="baseVersion" value={marking.data.versions} />
          <fieldset className="mb-4" disabled={!canDecide}>
            <legend className="mb-1 text-sm font-medium">{t("zonal")}</legend>
            <p className="mb-2 text-xs text-ink-3">{t("zonalHelp")}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {outfield.map((p) => (
                <label key={p.id} className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="zonal"
                    value={p.id}
                    defaultChecked={zonalSet.has(p.id)}
                    className="size-5"
                    data-testid={`zonal-${p.shirt_number ?? p.id}`}
                  />
                  {playerName(p)}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full min-w-max text-left text-sm" data-testid="marking-table">
              <caption className="sr-only">{t("assignment")}</caption>
              <thead className="border-b border-line text-xs text-ink-3">
                <tr>
                  <th scope="col" className="px-3 py-2">
                    {t("target")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    {t("threat")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("suggested")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("marker")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {suggestion.map((row) => {
                  const target = targetById.get(row.target_id);
                  const suggested = row.suggested_marker_id
                    ? byId.get(row.suggested_marker_id)
                    : undefined;
                  const savedRow = savedRows.get(row.target_id);
                  const label = target ? targetName(target) : row.target_id;
                  return (
                    <tr
                      key={row.target_id}
                      className="border-b border-line align-top last:border-0"
                      data-testid="marking-row"
                      data-target={target?.name}
                    >
                      <th scope="row" className="px-3 py-2 font-medium">
                        {label}
                      </th>
                      <td className="px-3 py-2 text-right">
                        <AerialValue score={target?.threat} />
                      </td>
                      <td className="px-3 py-2" data-testid="marking-suggested">
                        {suggested ? (
                          <span className="flex flex-col">
                            <span>{playerName(suggested)}</span>
                            <span className="text-xs text-ink-3 tabular-nums">
                              {t("gap", {
                                value: format.number(row.gap ?? 0, {
                                  signDisplay: "exceptZero",
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                }),
                              })}
                            </span>
                          </span>
                        ) : (
                          <span className="text-ink-3">{t("unmarked")}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {canDecide ? (
                          <>
                            <label className="sr-only" htmlFor={`marker-${row.target_id}`}>
                              {t("markerFor", { target: label })}
                            </label>
                            <select
                              id={`marker-${row.target_id}`}
                              name={`target:${row.target_id}`}
                              defaultValue={chosen(row) ?? ""}
                              className={inputCls}
                              data-testid="marking-select"
                            >
                              <option value="">{t("unmarked")}</option>
                              {outfield.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {playerName(p)}
                                </option>
                              ))}
                            </select>
                          </>
                        ) : (
                          <span>
                            {(() => {
                              const id = chosen(row);
                              const p = id ? byId.get(id) : undefined;
                              return p ? playerName(p) : t("unmarked");
                            })()}
                          </span>
                        )}
                        {useSaved && savedRow?.overridden ? (
                          <span
                            className="ml-2 inline-flex items-center rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium"
                            data-testid="marking-overridden"
                          >
                            {t("overridden")}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink-3">{t("costHelp")}</p>

          {canDecide ? (
            <div className="mt-4 flex flex-col gap-3">
              <label className="flex max-w-xl flex-col gap-1 text-sm">
                {t("note")}
                <input
                  name="note"
                  maxLength={400}
                  defaultValue={useSaved ? (saved?.note ?? "") : ""}
                  className={inputCls}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <PendingButton
                  className={btnPrimary}
                  pendingLabel={t("saving")}
                  testId="marking-save"
                >
                  {t("save")}
                </PendingButton>
                <button
                  type="submit"
                  formAction={recomputeMarking}
                  className={btn}
                  data-testid="marking-recompute"
                >
                  {t("recompute")}
                </button>
              </div>
            </div>
          ) : null}
        </form>
      )}
      {saved ? (
        <p className="mt-3 text-xs text-ink-3" data-testid="marking-saved">
          {t("savedInfo", {
            version: saved.version,
            by: saved.created_by?.name ?? "—",
            at: format.dateTime(new Date(saved.created_at), {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: "Europe/Istanbul",
            }),
            count: saved.overridden,
          })}
        </p>
      ) : (
        <p className="mt-3 text-xs text-ink-3">{t("notSaved")}</p>
      )}
    </Section>
  );
}

function playerName(p: SquadPlayer): string {
  return p.shirt_number ? `${p.shirt_number} · ${p.name}` : p.name;
}

function targetName(p: Target): string {
  return p.shirt_number ? `${p.shirt_number} · ${p.name}` : p.name;
}

async function Notice({ code }: { code: string }) {
  const t = await getTranslations("marking");
  if (code === "saved") {
    return (
      <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
        {t("savedNotice")}
      </p>
    );
  }
  return (
    <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
      {t.has(`errors.${code}`) ? t(`errors.${code}`) : t("errors.generic", { code })}
    </p>
  );
}

async function TargetTable({
  targets,
  fixtureId,
  canDecide,
}: {
  targets: Target[];
  fixtureId: string;
  canDecide: boolean;
}) {
  const t = await getTranslations("marking");
  const format = await getFormatter();
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-max text-left text-sm" data-testid="target-table">
        <caption className="sr-only">{t("targets")}</caption>
        <thead className="border-b border-line text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-3 py-2">
              {t("target")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("height")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("aerialPct")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("spGoals")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("threat")}
            </th>
            {canDecide ? (
              <th scope="col" className="px-3 py-2">
                <span className="sr-only">{t("remove")}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {targets.map((x) => (
            <tr key={x.id} className="border-b border-line last:border-0" data-testid="target-row">
              <th scope="row" className="px-3 py-2 font-medium">
                {targetName(x)}
                {x.notes ? (
                  <span className="block text-xs font-normal text-ink-3">{x.notes}</span>
                ) : null}
              </th>
              <td className="px-3 py-2 text-right tabular-nums">
                {x.height_cm ? t("cm", { value: x.height_cm }) : "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {x.aerial_win_pct == null
                  ? "—"
                  : format.number(x.aerial_win_pct, {
                      style: "percent",
                      maximumFractionDigits: 0,
                    })}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{x.sp_goals ?? "—"}</td>
              <td className="px-3 py-2 text-right">
                <AerialValue score={x.threat} />
              </td>
              {canDecide ? (
                <td className="px-3 py-2">
                  <form action={deleteTarget}>
                    <input type="hidden" name="fixtureId" value={fixtureId} />
                    <input type="hidden" name="targetId" value={x.id} />
                    <PendingButton className={btn} pendingLabel={t("saving")}>
                      {t("remove")}
                      <span className="sr-only"> {x.name}</span>
                    </PendingButton>
                  </form>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 text-xs text-ink-3">{t("source")}</p>
    </div>
  );
}

async function TargetForm({ fixtureId, teamId }: { fixtureId: string; teamId: string }) {
  const t = await getTranslations("marking");
  return (
    <form
      action={addTarget}
      className="mt-2 grid max-w-2xl gap-3 sm:grid-cols-3"
      data-testid="target-form"
    >
      <input type="hidden" name="fixtureId" value={fixtureId} />
      <input type="hidden" name="teamId" value={teamId} />
      <label className="flex flex-col gap-1 text-sm sm:col-span-2">
        {t("name")}
        <input name="name" required maxLength={120} className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("shirt")}
        <input name="shirt_number" type="number" min={1} max={99} className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("heightCm")}
        <input name="height_cm" type="number" min={150} max={215} className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("aerialPctInput")}
        <input name="aerial_win_pct" type="number" min={0} max={100} className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("spGoals")}
        <input name="sp_goals" type="number" min={0} max={50} className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-sm sm:col-span-3">
        {t("notes")}
        <input name="notes" maxLength={400} className={inputCls} />
      </label>
      <div>
        <PendingButton className={btnPrimary} pendingLabel={t("saving")} testId="target-add">
          {t("addTargetButton")}
        </PendingButton>
      </div>
    </form>
  );
}
