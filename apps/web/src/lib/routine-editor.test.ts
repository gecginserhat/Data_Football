import { type Diagram, emptyDiagram, keyframe } from "@kurgu/pitch";
import { describe, expect, it } from "vitest";
import {
  addFrame,
  addLine,
  addPlayer,
  addZone,
  type EditorDoc,
  mirror,
  moveLine,
  movePlayer,
  moveZone,
  nextNumber,
  nudge,
  removeFrame,
  removeSelection,
  sameDoc,
  setBall,
  setFrameDuration,
  toPayload,
  updateLine,
  updatePlayer,
} from "./routine-editor";

function doc(diagram: Diagram = emptyDiagram()): EditorDoc {
  return { name: "Arka direk", side: "right", notes: "", whenToUse: "", diagram };
}

function withTaker(): EditorDoc {
  return addPlayer(doc(), "own", "taker", [104, 1]).doc;
}

describe("players", () => {
  it("adds numbered own players and unnumbered opponents", () => {
    let d = withTaker();
    d = addPlayer(d, "own", "target", [88, 40]).doc;
    const opp = addPlayer(d, "opponent", "gk", [103.5, 34]);
    expect(opp.id).toBe("p3");
    const players = opp.doc.diagram.players;
    expect(players.map((p) => p.number)).toEqual([1, 2, null]);
    expect(nextNumber(opp.doc.diagram, "own")).toBe(3);
  });

  it("keeps new players on the half pitch", () => {
    const { doc: d } = addPlayer(doc(), "own", "taker", [30, 80]);
    expect(d.diagram.players[0]).toMatchObject({ x: 52.5, y: 68 });
  });

  it("moves attached run starts with the player in the base frame", () => {
    let d = addPlayer(doc(), "own", "target", [88, 40]).doc;
    d = addLine(d, "run", [88.5, 40.5], [99, 38]).doc;
    expect(d.diagram.lines[0]).toMatchObject({ player_id: "p1", from: [88, 40] });
    d = movePlayer(d, "p1", [86, 41]);
    expect(d.diagram.players[0]).toMatchObject({ x: 86, y: 41 });
    expect(d.diagram.lines[0]!.from).toEqual([86, 41]);
  });

  it("moves players only inside the selected frame", () => {
    let d = addPlayer(doc(), "own", "target", [88, 40]).doc;
    d = addFrame(d).doc;
    d = movePlayer(d, "p1", [95, 38], 1);
    expect(d.diagram.players[0]).toMatchObject({ x: 88, y: 40 });
    expect(keyframe(d.diagram, 1).positions.p1).toEqual([95, 38]);
  });

  it("updates role, number and label", () => {
    const d = updatePlayer(withTaker(), "p1", { role: "thrower", number: 7, label: "Uğurcan" });
    expect(d.diagram.players[0]).toMatchObject({ role: "thrower", number: 7, label: "Uğurcan" });
  });

  it("nudges within the pitch", () => {
    expect(nudge([104.8, 0.2], 0.5, -0.5)).toEqual([105, 0]);
    expect(nudge([90, 30], -0.5, 2)).toEqual([89.5, 32]);
  });
});

describe("lines", () => {
  it("does not attach ball paths to players", () => {
    const d = addLine(withTaker(), "ball_path", [104, 1], [100, 30]).doc;
    expect(d.diagram.lines[0]).toMatchObject({
      kind: "ball_path",
      player_id: null,
      from: [104, 1],
    });
  });

  it("moves a whole line and detaches it from its player", () => {
    let d = addPlayer(doc(), "own", "target", [88, 40]).doc;
    d = addLine(d, "screen", [88, 40], [92, 40]).doc;
    d = moveLine(d, "l1", 1, -2);
    expect(d.diagram.lines[0]).toMatchObject({ from: [89, 38], to: [93, 38], player_id: null });
  });

  it("limits a line move at the pitch edge", () => {
    let d = addLine(doc(), "ball_path", [104, 1], [100, 30]).doc;
    d = moveLine(d, "l1", 5, -5);
    expect(d.diagram.lines[0]).toMatchObject({ from: [105, 0], to: [101, 29] });
  });

  it("changes the curve and endpoints", () => {
    let d = addLine(doc(), "run", [90, 30], [95, 30]).doc;
    d = updateLine(d, "l1", { curve: -0.3, to: [96, 31] });
    expect(d.diagram.lines[0]).toMatchObject({ curve: -0.3, to: [96, 31] });
  });
});

describe("zones and ball", () => {
  it("adds a zone from any two corners and ignores tiny drags", () => {
    const { doc: d, id } = addZone(doc(), [105, 31.5], [97, 20], "NP");
    expect(id).toBe("z1");
    expect(d.diagram.zones[0]).toEqual({ id: "z1", x: 97, y: 20, w: 8, h: 11.5, label: "NP" });
    expect(addZone(doc(), [90, 30], [90.5, 30.5]).id).toBeNull();
  });

  it("keeps zones inside the pitch when moved", () => {
    let d = addZone(doc(), [97, 20], [105, 31.5]).doc;
    d = moveZone(d, "z1", 5, -30);
    expect(d.diagram.zones[0]).toMatchObject({ x: 97, y: 0 });
  });

  it("sets the ball at start and per frame", () => {
    let d = setBall(doc(), [104.5, 0.5]);
    d = addFrame(d).doc;
    d = setBall(d, [100, 30], 1);
    expect(d.diagram.ball).toEqual([104.5, 0.5]);
    expect(keyframe(d.diagram, 1).ball).toEqual([100, 30]);
  });
});

describe("selection removal", () => {
  it("removes a player and cleans its references", () => {
    let d = addPlayer(doc(), "own", "target", [88, 40]).doc;
    d = addLine(d, "run", [88, 40], [99, 38]).doc;
    d = addFrame(d).doc;
    d = movePlayer(d, "p1", [95, 38], 1);
    d = removeSelection(d, { kind: "player", id: "p1" });
    expect(d.diagram.players).toEqual([]);
    expect(d.diagram.lines[0]!.player_id).toBeNull();
    expect(d.diagram.frames[0]!.positions).toEqual({});
  });

  it("removes lines, zones and the ball", () => {
    let d = addLine(doc(), "run", [90, 30], [95, 30]).doc;
    d = addZone(d, [97, 20], [105, 31.5]).doc;
    d = setBall(d, [104, 1]);
    d = removeSelection(d, { kind: "line", id: "l1" });
    d = removeSelection(d, { kind: "zone", id: "z1" });
    d = removeSelection(d, { kind: "ball" });
    expect(d.diagram.lines).toEqual([]);
    expect(d.diagram.zones).toEqual([]);
    expect(d.diagram.ball).toBeNull();
  });
});

describe("mirror", () => {
  it("mirrors the diagram and swaps the side", () => {
    const d = mirror(withTaker());
    expect(d.side).toBe("left");
    expect(d.diagram.players[0]).toMatchObject({ x: 104, y: 67 });
    expect(mirror(d)).toEqual(withTaker());
  });
});

describe("frames", () => {
  it("adds, retimes and removes frames", () => {
    let d = addFrame(doc()).doc;
    const second = addFrame(d);
    expect(second.index).toBe(2);
    d = setFrameDuration(second.doc, 2, 50);
    expect(d.diagram.frames[1]!.duration_ms).toBe(200);
    d = removeFrame(d, 1);
    expect(d.diagram.frames.map((f) => f.id)).toEqual(["f2"]);
  });
});

describe("payload", () => {
  it("detects changes and builds the PUT body", () => {
    const a = withTaker();
    expect(sameDoc(a, withTaker())).toBe(true);
    expect(sameDoc(a, mirror(a))).toBe(false);
    expect(toPayload({ ...a, name: "  Kısa  " }, 3, "  ")).toMatchObject({
      base_version: 3,
      name: "Kısa",
      side: "right",
      message: null,
      when_to_use: "",
    });
  });
});
