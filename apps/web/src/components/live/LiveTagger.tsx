"use client";

import { TeamBadge, cn } from "@kurgu/ui";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { deviceId, liveDb, type LocalTag } from "@/lib/live/db";
import {
  INITIAL_CLOCK,
  OUTCOMES,
  OUTCOME_KEYS,
  SP_TYPES,
  TEAM_KEYS,
  TYPE_KEYS,
  UNDO_MS,
  clockSeconds,
  formatClock,
  parseClock,
  setClock,
  setPeriod,
  toggleClock,
  type ClockState,
  type FirstContact,
  type Outcome,
  type Side,
  type SpType,
} from "@/lib/live/model";
import { addTag, deleteTag, httpTransport, syncOnce } from "@/lib/live/sync";
import { useLive, useNow, useOnline } from "./useLive";

export interface LiveRoutine {
  id: string;
  name: string;
  sp_type: SpType;
}

interface Team {
  code: string;
  name: string;
}

interface Props {
  fixtureId: string;
  home: Team;
  away: Team;
  ownSide: Side | null;
  routines: LiveRoutine[];
}

const SYNC_INTERVAL_MS = 5000;
const PERIODS = [1, 2, 3, 4];
const TYPE_SHORTCUT: Record<SpType, string> = { corner: "C", free_kick: "F", throw_in: "T" };

function clockKey(fixtureId: string) {
  return `kurgu-live-clock:${fixtureId}`;
}

function loadClock(fixtureId: string): ClockState {
  try {
    const raw = localStorage.getItem(clockKey(fixtureId));
    return raw ? { ...INITIAL_CLOCK, ...(JSON.parse(raw) as ClockState) } : INITIAL_CLOCK;
  } catch {
    return INITIAL_CLOCK;
  }
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}

export function LiveTagger({ fixtureId, home, away, ownSide, routines }: Props) {
  const t = useTranslations("live");
  const tA = useTranslations("analysis");
  const format = useFormatter();
  const db = useMemo(() => liveDb(), []);
  const [device] = useState(() => deviceId());
  const online = useOnline();
  const now = useNow();

  const [spType, setSpType] = useState<SpType>("corner");
  const [team, setTeam] = useState<Side>(ownSide ?? "home");
  const [routineId, setRoutineId] = useState("");
  const [contact, setContact] = useState<FirstContact | null>(null);
  const [clock, setClockState] = useState<ClockState>(() => loadClock(fixtureId));
  const [clockInput, setClockInput] = useState("");
  const [lastOwn, setLastOwn] = useState<{ id: string; at: number } | null>(null);
  const [announce, setAnnounce] = useState("");
  const [syncState, setSyncState] = useState<"idle" | "syncing" | "error">("idle");
  const [confirming, setConfirming] = useState<string | null>(null);
  const routineRef = useRef<HTMLSelectElement>(null);
  const syncTimer = useRef<number | null>(null);

  const updateClock = useCallback(
    (next: ClockState) => {
      setClockState(next);
      try {
        localStorage.setItem(clockKey(fixtureId), JSON.stringify(next));
      } catch {
        // Saat yalnızca bu oturumda tutulur.
      }
    },
    [fixtureId],
  );

  const tags = useLive(
    async () => {
      const rows = await db.tags.where("fixtureId").equals(fixtureId).toArray();
      return rows
        .filter((r) => !r.deleted)
        .sort(
          (a, b) =>
            b.payload.period - a.payload.period ||
            b.payload.clock_s - a.payload.clock_s ||
            b.createdAt - a.createdAt,
        );
    },
    [db, fixtureId],
    [] as LocalTag[],
  );
  const pending = useLive(
    () => db.tags.where({ fixtureId, pending: 1 }).count(),
    [db, fixtureId],
    0,
  );
  const meta = useLive(() => db.meta.get(fixtureId), [db, fixtureId], undefined);

  const runSync = useCallback(async () => {
    if (!device || !navigator.onLine) return;
    setSyncState("syncing");
    try {
      await syncOnce(db, httpTransport, fixtureId, device);
      setSyncState("idle");
    } catch {
      setSyncState("error");
    }
  }, [db, device, fixtureId]);

  const scheduleSync = useCallback(() => {
    if (syncTimer.current !== null) window.clearTimeout(syncTimer.current);
    syncTimer.current = window.setTimeout(() => void runSync(), 300);
  }, [runSync]);

  useEffect(() => {
    if (!online) return;
    const first = window.setTimeout(() => void runSync(), 0);
    const id = window.setInterval(() => void runSync(), SYNC_INTERVAL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [online, runSync]);

  const ownTeam = team === ownSide;
  const routineOptions = routines.filter((r) => r.sp_type === spType);
  const seconds = clockSeconds(clock, now);
  const teams: Record<Side, Team> = { home, away };

  const commit = useCallback(
    async (outcome: Outcome) => {
      if (!device) return;
      const routine = ownTeam && routineId ? routineId : null;
      const tag = await addTag(
        db,
        fixtureId,
        {
          sp_type: spType,
          team,
          outcome,
          period: clock.period,
          clock_s: Math.round(clockSeconds(clock, Date.now())),
          ...(routine ? { routine_id: routine } : {}),
          ...(contact ? { first_contact: contact } : {}),
        },
        device,
      );
      setLastOwn({ id: tag.id, at: Date.now() });
      setRoutineId("");
      setContact(null);
      setAnnounce(
        t("saved", {
          type: tA(`spType.${spType}`),
          team: teams[team].code,
          outcome: tA(`outcome.${outcome}`),
          clock: formatClock(tag.payload.clock_s),
        }),
      );
      scheduleSync();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [db, device, fixtureId, spType, team, routineId, contact, clock, ownTeam, scheduleSync],
  );

  const undo = useCallback(async () => {
    if (!lastOwn || Date.now() - lastOwn.at > UNDO_MS) return;
    await deleteTag(db, lastOwn.id, device);
    setLastOwn(null);
    setAnnounce(t("undone"));
    scheduleSync();
  }, [db, device, lastOwn, scheduleSync, t]);

  const remove = useCallback(
    async (id: string) => {
      if (confirming !== id) {
        setConfirming(id);
        return;
      }
      setConfirming(null);
      await deleteTag(db, id, device);
      if (lastOwn?.id === id) setLastOwn(null);
      scheduleSync();
    },
    [confirming, db, device, lastOwn, scheduleSync],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) return;
      const key = event.key.toLowerCase();
      if (TYPE_KEYS[key]) {
        setSpType(TYPE_KEYS[key]);
        setRoutineId("");
      } else if (TEAM_KEYS[key]) {
        setTeam(TEAM_KEYS[key]);
        setRoutineId("");
      } else if (OUTCOME_KEYS[key]) {
        void commit(OUTCOME_KEYS[key]);
      } else if (key === "r") {
        routineRef.current?.focus();
      } else if (key === "z") {
        void undo();
      } else {
        return;
      }
      event.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [commit, undo]);

  const undoLeft = lastOwn ? Math.ceil((UNDO_MS - (now - lastOwn.at)) / 1000) : 0;
  const routineName = (id?: string | null) => routines.find((r) => r.id === id)?.name;

  return (
    <div className="flex flex-col gap-4" data-testid="live-tagger">
      <div
        className="sticky top-0 z-10 -mx-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-bg/95 px-4 py-2 text-sm backdrop-blur"
        data-testid="live-status"
        data-session={meta?.sessionId ?? undefined}
      >
        <span
          className={cn(
            "inline-flex items-center gap-2 rounded-full px-3 py-1 font-medium",
            online ? "bg-pos text-brand-ink" : "bg-neg text-brand-ink",
          )}
          data-online={online}
        >
          <span aria-hidden="true">{online ? "●" : "○"}</span>
          {online ? t("online") : t("offline")}
        </span>
        <span data-testid="live-pending" data-count={pending} className="tabular-nums">
          {t("pending", { count: pending })}
        </span>
        <span className="text-ink-3">
          {syncState === "syncing"
            ? t("syncing")
            : syncState === "error" && online
              ? t("syncError")
              : meta?.lastSyncAt
                ? t("lastSync", {
                    time: format.dateTime(new Date(meta.lastSyncAt), { timeStyle: "medium" }),
                  })
                : t("neverSynced")}
        </span>
        <button
          type="button"
          onClick={() => void runSync()}
          disabled={!online || syncState === "syncing"}
          className="ml-auto min-h-11 rounded-md border border-line bg-surface px-3 disabled:opacity-50"
        >
          {t("syncNow")}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-5">
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium text-ink-2">{t("clock")}</legend>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="min-w-24 font-condensed text-4xl font-semibold tabular-nums"
                data-testid="live-clock"
                aria-live="off"
              >
                {formatClock(seconds)}
              </span>
              <button
                type="button"
                onClick={() => updateClock(toggleClock(clock, Date.now()))}
                className="min-h-14 rounded-md bg-pri px-4 font-medium text-brand-ink"
              >
                {clock.startedAt === null ? t("clockStart") : t("clockPause")}
              </button>
              <div role="group" aria-label={t("period")} className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    aria-pressed={clock.period === p}
                    onClick={() => updateClock(setPeriod(clock, p))}
                    className={cn(
                      "min-h-14 min-w-14 rounded-md border px-2 text-sm",
                      clock.period === p
                        ? "border-pri bg-pri text-brand-ink"
                        : "border-line bg-surface",
                    )}
                  >
                    {t(`periodShort.${p}`)}
                  </button>
                ))}
              </div>
              <form
                className="flex items-center gap-1"
                onSubmit={(event) => {
                  event.preventDefault();
                  const parsed = parseClock(clockInput);
                  if (parsed !== null) {
                    updateClock(setClock(clock, parsed, Date.now()));
                    setClockInput("");
                  }
                }}
              >
                <label className="sr-only" htmlFor="live-clock-input">
                  {t("clockSet")}
                </label>
                <input
                  id="live-clock-input"
                  inputMode="numeric"
                  placeholder="mm:ss"
                  value={clockInput}
                  onChange={(e) => setClockInput(e.target.value)}
                  className="min-h-14 w-24 rounded-md border border-line bg-surface px-2 tabular-nums"
                />
                <button
                  type="submit"
                  className="min-h-14 rounded-md border border-line bg-surface px-3"
                >
                  {t("clockSet")}
                </button>
              </form>
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink-2">{t("type")}</legend>
            <div className="grid grid-cols-3 gap-2">
              {SP_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  aria-pressed={spType === type}
                  onClick={() => {
                    setSpType(type);
                    setRoutineId("");
                  }}
                  className={cn(
                    "flex min-h-14 items-center justify-center gap-2 rounded-md border px-2 font-medium",
                    spType === type ? "border-pri bg-pri text-brand-ink" : "border-line bg-surface",
                  )}
                >
                  {tA(`spType.${type}`)}
                  <kbd className="text-xs opacity-70">{TYPE_SHORTCUT[type]}</kbd>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink-2">{t("team")}</legend>
            <div className="grid grid-cols-2 gap-2">
              {(["home", "away"] as const).map((side) => (
                <button
                  key={side}
                  type="button"
                  aria-pressed={team === side}
                  onClick={() => {
                    setTeam(side);
                    setRoutineId("");
                  }}
                  className={cn(
                    "flex min-h-14 items-center justify-center gap-2 rounded-md border px-2 font-medium",
                    team === side ? "border-pri bg-pri text-brand-ink" : "border-line bg-surface",
                  )}
                >
                  <TeamBadge code={teams[side].code} name={teams[side].name} />
                  <span className="truncate">{teams[side].name}</span>
                  {side === ownSide ? (
                    <span className="rounded bg-accent px-1 text-xs text-accent-ink">
                      {t("own")}
                    </span>
                  ) : null}
                  <kbd className="text-xs opacity-70">{side === "home" ? "H" : "A"}</kbd>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label htmlFor="live-routine" className="text-sm font-medium text-ink-2">
                {t("routine")} <kbd className="text-xs opacity-70">R</kbd>
              </label>
              <select
                id="live-routine"
                ref={routineRef}
                value={routineId}
                disabled={!ownTeam || routineOptions.length === 0}
                onChange={(e) => setRoutineId(e.target.value)}
                className="min-h-14 rounded-md border border-line bg-surface px-2 disabled:opacity-60"
              >
                <option value="">{t("noRoutine")}</option>
                {routineOptions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-ink-3">
                {!ownTeam
                  ? t("routineOwnOnly")
                  : routineOptions.length === 0
                    ? t("routineNone")
                    : null}
              </p>
            </div>
            <fieldset>
              <legend className="mb-1 text-sm font-medium text-ink-2">{t("firstContact")}</legend>
              <div className="grid grid-cols-3 gap-1">
                {([null, "attack", "defense"] as const).map((value) => (
                  <button
                    key={value ?? "none"}
                    type="button"
                    aria-pressed={contact === value}
                    onClick={() => setContact(value)}
                    className={cn(
                      "min-h-14 rounded-md border px-1 text-sm",
                      contact === value
                        ? "border-pri bg-pri text-brand-ink"
                        : "border-line bg-surface",
                    )}
                  >
                    {t(`contact.${value ?? "none"}`)}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink-2">{t("outcome")}</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="live-outcomes">
              {OUTCOMES.map((outcome, index) => (
                <button
                  key={outcome}
                  type="button"
                  data-outcome={outcome}
                  disabled={!device}
                  onClick={() => void commit(outcome)}
                  className={cn(
                    "flex min-h-16 flex-col items-center justify-center rounded-md border-2 px-2 text-center font-medium",
                    outcome === "goal"
                      ? "border-pos bg-pos text-brand-ink"
                      : outcome === "counter_conceded"
                        ? "border-neg bg-surface text-ink"
                        : "border-line bg-surface",
                  )}
                >
                  <span>{tA(`outcome.${outcome}`)}</span>
                  <kbd className="text-xs opacity-70">{index + 1}</kbd>
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-ink-3">{t("hint")}</p>
          </fieldset>
        </div>

        <section aria-labelledby="live-list" className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h2 id="live-list" className="font-condensed text-lg font-semibold">
              {t("list", { count: tags.length })}
            </h2>
            {lastOwn && undoLeft > 0 ? (
              <button
                type="button"
                onClick={() => void undo()}
                className="min-h-11 rounded-md bg-accent px-3 font-medium text-accent-ink"
                data-testid="live-undo"
              >
                {t("undo", { seconds: undoLeft })}
              </button>
            ) : null}
          </div>
          <p role="status" aria-live="polite" className="sr-only">
            {announce}
          </p>
          {tags.length === 0 ? (
            <p className="rounded-md border border-dashed border-line p-4 text-sm text-ink-2">
              {t("empty")}
            </p>
          ) : (
            <ol className="flex flex-col gap-2" data-testid="live-tags">
              {tags.map((tag) => (
                <li
                  key={tag.id}
                  data-tag-id={tag.id}
                  data-pending={tag.pending}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-surface p-2 text-sm"
                >
                  <span className="w-20 font-condensed text-base tabular-nums">
                    {formatClock(tag.payload.clock_s)}
                    <span className="ml-1 text-xs text-ink-3">
                      {t(`periodShort.${tag.payload.period}`)}
                    </span>
                  </span>
                  <TeamBadge
                    code={teams[tag.payload.team]?.code ?? "?"}
                    name={teams[tag.payload.team]?.name ?? ""}
                  />
                  <span>{tA(`spType.${tag.payload.sp_type}`)}</span>
                  <span className="font-medium">{tA(`outcome.${tag.payload.outcome}`)}</span>
                  {tag.payload.routine_id ? (
                    <span className="text-ink-2">
                      {routineName(tag.payload.routine_id) ?? t("routine")}
                    </span>
                  ) : null}
                  <span
                    className={cn(
                      "ml-auto rounded px-2 py-0.5 text-xs",
                      tag.error
                        ? "bg-neg text-brand-ink"
                        : tag.pending
                          ? "bg-accent text-accent-ink"
                          : "bg-bg text-ink-2",
                    )}
                  >
                    {tag.error
                      ? t("rejected", { reason: tag.error })
                      : tag.pending
                        ? t("statusPending")
                        : t("statusSynced")}
                  </span>
                  <button
                    type="button"
                    onClick={() => void remove(tag.id)}
                    className="min-h-11 rounded-md border border-line px-3 text-xs"
                  >
                    {confirming === tag.id ? t("confirmDelete") : t("delete")}
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
