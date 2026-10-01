import { describe, expect, it } from "vitest";
import { PITCH, ZONES } from "./index";

describe("pitch geometry", () => {
  it("uses the canonical 105 x 68 pitch", () => {
    expect(PITCH.length).toBe(105);
    expect(PITCH.width).toBe(68);
    expect(PITCH.goal_center).toEqual([105, 34]);
  });

  it("places posts symmetrically around the goal center", () => {
    const [a, b] = PITCH.posts_y;
    expect((a + b) / 2).toBeCloseTo(34, 5);
    expect(b - a).toBeCloseTo(7.32, 5);
  });

  it("defines all seven delivery zones", () => {
    expect(ZONES.map((z) => z.code)).toEqual(["NP", "C6", "FP", "PS", "ED", "SH", "OT"]);
  });
});
