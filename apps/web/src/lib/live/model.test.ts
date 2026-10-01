import { describe, expect, it } from "vitest";
import {
  INITIAL_CLOCK,
  OUTCOME_KEYS,
  clockSeconds,
  formatClock,
  parseClock,
  setClock,
  setPeriod,
  toggleClock,
} from "./model";

describe("live model", () => {
  it("maps 1-8 to the eight outcomes in SPEC order", () => {
    expect(OUTCOME_KEYS["1"]).toBe("goal");
    expect(OUTCOME_KEYS["6"]).toBe("cleared");
    expect(OUTCOME_KEYS["8"]).toBe("counter_conceded");
    expect(OUTCOME_KEYS["9"]).toBeUndefined();
  });

  it("formats and parses the match clock", () => {
    expect(formatClock(754.9)).toBe("12:34");
    expect(formatClock(5400)).toBe("90:00");
    expect(parseClock("67:30")).toBe(4050);
    expect(parseClock("45")).toBe(2700);
    expect(parseClock("12:75")).toBeNull();
    expect(parseClock("abc")).toBeNull();
  });

  it("runs, pauses and jumps the clock per period", () => {
    const started = toggleClock(INITIAL_CLOCK, 1_000);
    expect(clockSeconds(started, 61_000)).toBe(60);
    const paused = toggleClock(started, 61_000);
    expect(clockSeconds(paused, 999_000)).toBe(60);
    expect(clockSeconds(setClock(paused, 600, 0), 5_000)).toBe(600);
    const second = setPeriod(paused, 2);
    expect(second).toEqual({ period: 2, baseS: 2700, startedAt: null });
  });
});
