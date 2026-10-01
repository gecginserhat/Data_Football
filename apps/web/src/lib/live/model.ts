/**
 * Canlı kayıt modeli (SPEC §13.2, A-58). API'deki `TagPayload` ile aynı alanlar; tarayıcıda
 * çevrimdışı tutulur ve senkronizasyonda olduğu gibi gönderilir.
 */

export const SP_TYPES = ["corner", "free_kick", "throw_in"] as const;
export type SpType = (typeof SP_TYPES)[number];

export const OUTCOMES = [
  "goal",
  "shot_on_target",
  "shot_off_target",
  "shot_blocked",
  "first_contact_no_shot",
  "cleared",
  "possession_retained",
  "counter_conceded",
] as const;
export type Outcome = (typeof OUTCOMES)[number];

export type Side = "home" | "away";
export type FirstContact = "attack" | "defense";

export interface TagPayload {
  sp_type: SpType;
  team: Side;
  outcome: Outcome;
  period: number;
  clock_s: number;
  routine_id?: string | null;
  first_contact?: FirstContact | null;
  side?: "left" | "right" | null;
  note?: string;
}

/** Kısayollar (A-58): C/F/T tür, H/A takım, 1-8 sonuç, R rutin. */
export const TYPE_KEYS: Record<string, SpType> = { c: "corner", f: "free_kick", t: "throw_in" };
export const TEAM_KEYS: Record<string, Side> = { h: "home", a: "away" };
export const OUTCOME_KEYS: Record<string, Outcome> = Object.fromEntries(
  OUTCOMES.map((o, i) => [String(i + 1), o]),
);

/** Geri alma süresi (SPEC §13.2: son kayıt 10 sn içinde geri alınabilir). */
export const UNDO_MS = 10_000;

/** Maç saati: devre ve devre başlangıcından bu yana saniye (devre 2 = 45:00'ten başlar). */
export const PERIOD_START_S: Record<number, number> = { 1: 0, 2: 2700, 3: 5400, 4: 6300, 5: 7200 };

export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** "67:30" ya da "67" → saniye; geçersizse null. */
export function parseClock(text: string): number | null {
  const match = /^\s*(\d{1,3})(?::([0-5]\d))?\s*$/.exec(text);
  if (!match) return null;
  const seconds = Number(match[1]) * 60 + Number(match[2] ?? 0);
  return seconds <= 10_800 ? seconds : null;
}

/** Maç saati (SPEC §13.2: manuel ya da çalışan saat). `startedAt` doluysa saat işler. */
export interface ClockState {
  period: number;
  baseS: number;
  startedAt: number | null;
}

export const INITIAL_CLOCK: ClockState = { period: 1, baseS: 0, startedAt: null };

export function clockSeconds(clock: ClockState, now: number): number {
  const running = clock.startedAt === null ? 0 : (now - clock.startedAt) / 1000;
  return Math.min(10_800, clock.baseS + Math.max(0, running));
}

export function toggleClock(clock: ClockState, now: number): ClockState {
  return clock.startedAt === null
    ? { ...clock, startedAt: now }
    : { ...clock, baseS: clockSeconds(clock, now), startedAt: null };
}

export function setClock(clock: ClockState, seconds: number, now: number): ClockState {
  return { ...clock, baseS: seconds, startedAt: clock.startedAt === null ? null : now };
}

export function setPeriod(clock: ClockState, period: number): ClockState {
  return { period, baseS: PERIOD_START_S[period] ?? 0, startedAt: null };
}
