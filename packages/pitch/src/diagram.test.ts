import { describe, expect, it } from "vitest";
import vectors from "../diagram.vectors.json";
import {
  type Diagram,
  clampToBoard,
  controlPoint,
  diffDiagrams,
  emptyDiagram,
  interpolate,
  keyframe,
  mirrorDiagram,
  mirrorSide,
  nextId,
  pointOnCurve,
  roleLabel,
  ROLES,
  snap,
} from "./diagram";

const sample = vectors.sample as unknown as Diagram;

describe("controlPoint (shared vectors)", () => {
  it.each(vectors.control_points)("$from → $to, curve $curve", (c) => {
    const p = controlPoint(c.from as [number, number], c.to as [number, number], c.curve);
    expect(p[0]).toBeCloseTo(c.control[0]!, 6);
    expect(p[1]).toBeCloseTo(c.control[1]!, 6);
  });

  it("starts and ends the curve on the line endpoints", () => {
    expect(pointOnCurve([90, 30], [100, 40], 0.3, 0)).toEqual([90, 30]);
    expect(pointOnCurve([90, 30], [100, 40], 0.3, 1)).toEqual([100, 40]);
  });
});

describe("mirrorDiagram", () => {
  it("matches the Python mirror", () => {
    expect(mirrorDiagram(sample)).toEqual(vectors.mirrored);
  });

  it("is its own inverse", () => {
    expect(mirrorDiagram(mirrorDiagram(sample))).toEqual(sample);
  });

  it("swaps the side", () => {
    expect(mirrorSide("left")).toBe("right");
    expect(mirrorSide("right")).toBe("left");
    expect(mirrorSide(null)).toBeNull();
  });

  it("keeps a mirrored curve bending to the mirrored side", () => {
    const line = sample.lines[0]!;
    const m = mirrorDiagram(sample).lines[0]!;
    const c = controlPoint(line.from, line.to, line.curve);
    const cm = controlPoint(m.from, m.to, m.curve);
    expect(cm[0]).toBeCloseTo(c[0], 6);
    expect(cm[1]).toBeCloseTo(68 - c[1], 6);
  });
});

describe("keyframe and interpolate", () => {
  it.each(vectors.keyframes)("keyframe $index matches Python", (k) => {
    const snapshot = keyframe(sample, k.index);
    expect(snapshot.positions).toEqual(k.positions);
    expect(snapshot.ball).toEqual(k.ball);
  });

  it("interpolates linearly between keyframes", () => {
    const mid = interpolate(sample, 0.5);
    expect(mid.positions.p2![0]).toBeCloseTo(89, 6);
    expect(mid.positions.p2![1]).toBeCloseTo(39.5, 6);
    expect(mid.positions.p3).toEqual([103.5, 34]);
  });

  it("clamps time to the available frames", () => {
    expect(interpolate(sample, 99)).toEqual(keyframe(sample, 2));
    expect(interpolate(sample, -1)).toEqual(keyframe(sample, 0));
  });
});

describe("diffDiagrams", () => {
  it("reports no change for the same diagram", () => {
    const d = diffDiagrams(sample, sample);
    expect(d.playersMoved).toEqual([]);
    expect(d.linesChanged).toEqual([]);
    expect(d.playersAdded).toEqual([]);
  });

  it("lists moved, changed, added and removed elements", () => {
    const next: Diagram = {
      ...sample,
      players: [
        { ...sample.players[0]!, x: 101 },
        { ...sample.players[1]!, role: "decoy" },
        { id: "p9", team: "own", role: "blocker", x: 90, y: 30 },
      ],
      lines: sample.lines.slice(1).map((l) => (l.id === "l2" ? { ...l, curve: 0.2 } : l)),
    };
    const d = diffDiagrams(sample, next);
    expect(d.playersMoved).toEqual(["p1"]);
    expect(d.playersChanged).toEqual(["p2"]);
    expect(d.playersAdded).toEqual(["p9"]);
    expect(d.playersRemoved).toEqual(["p3"]);
    expect(d.linesRemoved).toEqual(["l1"]);
    expect(d.linesChanged).toEqual(["l2"]);
  });
});

describe("helpers", () => {
  it("snaps to the grid", () => {
    expect(snap(97.26, 0.5)).toBe(97.5);
    expect(snap(97.26, 1)).toBe(97);
    expect(snap(97.26, 0)).toBe(97.26);
  });

  it("keeps points on the half pitch", () => {
    expect(clampToBoard([40, -3])).toEqual([52.5, 0]);
    expect(clampToBoard([110, 70])).toEqual([105, 68]);
  });

  it("finds the next free id", () => {
    expect(nextId("p", ["p1", "p2", "p4"])).toBe("p3");
    expect(nextId("l", [])).toBe("l1");
  });

  it("creates an empty v1 diagram", () => {
    expect(emptyDiagram()).toEqual({
      schema: 1,
      players: [],
      lines: [],
      zones: [],
      ball: null,
      frames: [],
    });
  });

  it("labels roles in both languages and falls back to the id", () => {
    expect(roleLabel("own", "taker", "tr")).toBe("Kullanan");
    expect(roleLabel("own", "taker", "en")).toBe("Taker");
    expect(roleLabel("own", "unknown_role", "tr")).toBe("unknown_role");
    expect(ROLES.opponent.some((r) => r.id === "gk")).toBe(true);
  });
});
