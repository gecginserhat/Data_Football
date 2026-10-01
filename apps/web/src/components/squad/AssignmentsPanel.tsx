import { roleLabel } from "@kurgu/pitch";
import { EmptyState } from "@kurgu/ui";
import { getLocale, getTranslations } from "next-intl/server";
import { NotLoaded, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { BoardView } from "@/components/routines/board";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import type { Loaded } from "@/lib/analysis";
import { toDiagram, type Routine } from "@/lib/routines";
import type { Assignments, SquadPlayer } from "@/lib/squad";
import { pickRoutine, saveAssignments } from "@/lib/squad-actions";

interface Slot {
  diagram_player_id: string;
  role: string;
  number?: number | null;
  label?: string | null;
  squad_player_id?: string | null;
}

interface Card {
  routine_id: string;
  name: string;
  version: number;
  sources: string[];
  slots: Slot[];
  assigned_version?: number | null;
  diagram?: Routine["version"]["diagram"];
}

/**
 * Rutin rol atamaları (A-87): kabul edilen öneri ve plan maddelerinin rutinlerinde her rol bir
 * kadro oyuncusuna atanır. Oyuncu görevini `/me` görev kartında görür.
 */
export async function AssignmentsPanel({
  assignments,
  squad,
  routines,
  picked,
  fixtureId,
  canDecide,
  message,
}: {
  assignments: Loaded<Assignments>;
  squad: SquadPlayer[];
  routines: { id: string; name: string }[];
  picked: Routine | null;
  fixtureId: string;
  canDecide: boolean;
  message: string | undefined;
}) {
  const t = await getTranslations("assignments");
  if (assignments.status !== "ok") {
    return (
      <Section id="assignments" title={t("title")}>
        <NotLoaded result={assignments} />
      </Section>
    );
  }
  const cards: Card[] = assignments.data.routines.map((r) => ({ ...r }));
  if (picked && !cards.some((c) => c.routine_id === picked.id)) {
    cards.push({
      routine_id: picked.id,
      name: picked.name,
      version: picked.current_version,
      sources: [],
      diagram: picked.version.diagram,
      slots: (picked.version.diagram.players ?? [])
        .filter((p) => p.team === "own")
        .map((p) => ({ diagram_player_id: p.id, role: p.role, number: p.number, label: p.label })),
    });
  }
  const available = routines.filter((r) => !cards.some((c) => c.routine_id === r.id));
  return (
    <Section id="assignments" title={t("title")}>
      <p className="mb-3 max-w-3xl text-sm text-ink-2">{t("intro")}</p>
      {message ? (
        message === "saved" ? (
          <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
            {t("saved")}
          </p>
        ) : (
          <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
            {t.has(`errors.${message}`)
              ? t(`errors.${message}`)
              : t("errors.generic", { code: message })}
          </p>
        )
      ) : null}
      {cards.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {cards.map((card) => (
            <RoutineCard
              key={card.routine_id}
              card={card}
              squad={squad}
              fixtureId={fixtureId}
              canDecide={canDecide}
            />
          ))}
        </div>
      )}
      {canDecide && available.length ? (
        <form action={pickRoutine} className="mt-4 flex flex-wrap items-end gap-2">
          <input type="hidden" name="fixtureId" value={fixtureId} />
          <label className="flex flex-col gap-1 text-sm">
            {t("addRoutine")}
            <select name="routineId" className={inputCls} data-testid="assign-pick">
              {available.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className={btn}>
            {t("show")}
          </button>
        </form>
      ) : null}
    </Section>
  );
}

async function RoutineCard({
  card,
  squad,
  fixtureId,
  canDecide,
}: {
  card: Card;
  squad: SquadPlayer[];
  fixtureId: string;
  canDecide: boolean;
}) {
  const t = await getTranslations("assignments");
  const locale = await getLocale();
  const byId = new Map(squad.map((p) => [p.id, p]));
  const stale = card.assigned_version != null && card.assigned_version < card.version;
  return (
    <article
      className="rounded-lg border border-line bg-surface p-4"
      data-testid="assign-card"
      data-routine={card.name}
    >
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-condensed text-base font-semibold">{card.name}</h3>
          <p className="text-xs text-ink-3">
            {t("version", { version: card.version })}
            {card.sources.length ? ` · ${card.sources.join(" · ")}` : ""}
          </p>
        </div>
        {stale ? (
          <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium">
            {t("stale", { version: card.assigned_version ?? 0 })}
          </span>
        ) : null}
      </header>
      {card.diagram ? (
        <BoardView
          diagram={toDiagram(card.diagram)}
          label={t("diagram", { name: card.name })}
          className="mb-3 w-40"
        />
      ) : null}
      {card.slots.length === 0 ? (
        <p className="text-sm text-ink-3">{t("noRoles")}</p>
      ) : (
        <form action={saveAssignments} className="flex flex-col gap-2">
          <input type="hidden" name="fixtureId" value={fixtureId} />
          <input type="hidden" name="routineId" value={card.routine_id} />
          {card.slots.map((slot) => {
            const role = `${roleLabel("own", slot.role, locale)}${slot.number ? ` (${slot.number})` : ""}${slot.label ? ` · ${slot.label}` : ""}`;
            const current = slot.squad_player_id ? byId.get(slot.squad_player_id) : undefined;
            return (
              <div
                key={slot.diagram_player_id}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <label
                  htmlFor={`slot-${card.routine_id}-${slot.diagram_player_id}`}
                  className="text-sm"
                >
                  {role}
                </label>
                {canDecide ? (
                  <select
                    id={`slot-${card.routine_id}-${slot.diagram_player_id}`}
                    name={`slot:${slot.diagram_player_id}`}
                    defaultValue={slot.squad_player_id ?? ""}
                    className={inputCls}
                    data-testid={`slot-${slot.role}`}
                  >
                    <option value="">{t("unassigned")}</option>
                    {squad.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.shirt_number ? `${p.shirt_number} · ${p.name}` : p.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="text-sm">{current?.name ?? t("unassigned")}</span>
                )}
              </div>
            );
          })}
          {canDecide ? (
            <div className="mt-1">
              <PendingButton className={btnPrimary} pendingLabel={t("saving")} testId="assign-save">
                {t("save")}
              </PendingButton>
            </div>
          ) : null}
        </form>
      )}
    </article>
  );
}
