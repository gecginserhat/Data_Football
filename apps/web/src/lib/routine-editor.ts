/**
 * Rutin editörünün saf belge işlemleri (SPEC §13.2, ADR-0008). Her işlem yeni bir belge döner;
 * geri al / yinele geçmişi (zundo) bu belgeleri saklar. Geometri `@kurgu/pitch` içinde.
 */
import {
  type Diagram,
  type DiagramFrame,
  type DiagramLine,
  type DiagramPlayer,
  type DiagramTeam,
  type LineKind,
  type Point,
  clampToBoard,
  DEFAULT_FRAME_MS,
  mirrorDiagram,
  mirrorSide,
  nextId,
  PITCH_LENGTH,
  PITCH_WIDTH,
} from "@kurgu/pitch";

export type Side = "left" | "right";

export interface EditorDoc {
  name: string;
  side: Side | null;
  notes: string;
  whenToUse: string;
  diagram: Diagram;
}

export type Selection =
  | { kind: "player"; id: string }
  | { kind: "line"; id: string }
  | { kind: "zone"; id: string }
  | { kind: "ball" };

const MAX_PLAYERS = 30;
const MAX_LINES = 80;
const MAX_ZONES = 12;
const MAX_FRAMES = 20;
/** Koşu bu mesafe içinde başlıyorsa oyuncuya bağlanır (metre). */
export const ATTACH_DISTANCE = 2;

const r2 = (v: number) => Math.round(v * 100) / 100;
const pt = (p: Point): Point => {
  const [x, y] = clampToBoard(p);
  return [r2(x), r2(y)];
};
const withDiagram = (doc: EditorDoc, diagram: Diagram): EditorDoc => ({ ...doc, diagram });
const close = (a: Point, b: Point, tol = 0.05) =>
  Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;

export function nextNumber(diagram: Diagram, team: DiagramTeam): number | null {
  if (team !== "own") return null;
  const used = new Set(diagram.players.map((p) => p.number));
  for (let n = 1; n <= 99; n++) if (!used.has(n)) return n;
  return null;
}

export function addPlayer(
  doc: EditorDoc,
  team: DiagramTeam,
  role: string,
  at: Point,
): { doc: EditorDoc; id: string | null } {
  const d = doc.diagram;
  if (d.players.length >= MAX_PLAYERS) return { doc, id: null };
  const id = nextId(
    "p",
    d.players.map((p) => p.id),
  );
  const [x, y] = pt(at);
  const player: DiagramPlayer = { id, team, role, number: nextNumber(d, team), label: null, x, y };
  return { doc: withDiagram(doc, { ...d, players: [...d.players, player] }), id };
}

export function updatePlayer(
  doc: EditorDoc,
  id: string,
  changes: Partial<Pick<DiagramPlayer, "team" | "role" | "number" | "label">>,
): EditorDoc {
  const d = doc.diagram;
  return withDiagram(doc, {
    ...d,
    players: d.players.map((p) => (p.id === id ? { ...p, ...changes } : p)),
  });
}

/**
 * Oyuncuyu taşır. `frame` 0 ise başlangıç dizilişi: oyuncuya bağlı ve oyuncunun eski
 * konumundan başlayan çizgiler de birlikte taşınır. `frame` > 0 ise yalnızca o karenin konumu.
 */
export function movePlayer(doc: EditorDoc, id: string, to: Point, frame = 0): EditorDoc {
  const d = doc.diagram;
  const target = pt(to);
  if (frame > 0) {
    return withDiagram(doc, {
      ...d,
      frames: d.frames.map((f, i) =>
        i === frame - 1 ? { ...f, positions: { ...f.positions, [id]: target } } : f,
      ),
    });
  }
  const player = d.players.find((p) => p.id === id);
  if (!player) return doc;
  const old: Point = [player.x, player.y];
  return withDiagram(doc, {
    ...d,
    players: d.players.map((p) => (p.id === id ? { ...p, x: target[0], y: target[1] } : p)),
    lines: d.lines.map((l) =>
      l.player_id === id && close(l.from, old) ? { ...l, from: target } : l,
    ),
  });
}

export function nudge(point: Point, dx: number, dy: number): Point {
  return pt([point[0] + dx, point[1] + dy]);
}

export function addLine(
  doc: EditorDoc,
  kind: LineKind,
  from: Point,
  to: Point,
): { doc: EditorDoc; id: string | null } {
  const d = doc.diagram;
  if (d.lines.length >= MAX_LINES) return { doc, id: null };
  let start = pt(from);
  let owner: string | null = null;
  if (kind !== "ball_path") {
    let best = ATTACH_DISTANCE;
    for (const p of d.players) {
      if (p.team !== "own") continue;
      const dist = Math.hypot(p.x - start[0], p.y - start[1]);
      if (dist <= best) {
        best = dist;
        owner = p.id;
      }
    }
    const ownerPlayer = d.players.find((p) => p.id === owner);
    if (ownerPlayer) start = [ownerPlayer.x, ownerPlayer.y];
  }
  const id = nextId(
    "l",
    d.lines.map((l) => l.id),
  );
  const line: DiagramLine = { id, kind, from: start, to: pt(to), curve: 0, player_id: owner };
  return { doc: withDiagram(doc, { ...d, lines: [...d.lines, line] }), id };
}

export function updateLine(
  doc: EditorDoc,
  id: string,
  changes: Partial<Pick<DiagramLine, "kind" | "from" | "to" | "curve" | "player_id">>,
): EditorDoc {
  const d = doc.diagram;
  const fixed = { ...changes };
  if (fixed.from) fixed.from = pt(fixed.from);
  if (fixed.to) fixed.to = pt(fixed.to);
  return withDiagram(doc, {
    ...d,
    lines: d.lines.map((l) => (l.id === id ? { ...l, ...fixed } : l)),
  });
}

/** Çizgiyi bütün olarak kaydırır; sahadan taşacaksa kaydırma sınırlanır. */
export function moveLine(doc: EditorDoc, id: string, dx: number, dy: number): EditorDoc {
  const line = doc.diagram.lines.find((l) => l.id === id);
  if (!line) return doc;
  const xs = [line.from[0], line.to[0]];
  const ys = [line.from[1], line.to[1]];
  const cdx = Math.min(Math.max(dx, 52.5 - Math.min(...xs)), PITCH_LENGTH - Math.max(...xs));
  const cdy = Math.min(Math.max(dy, -Math.min(...ys)), PITCH_WIDTH - Math.max(...ys));
  return updateLine(doc, id, {
    from: [line.from[0] + cdx, line.from[1] + cdy],
    to: [line.to[0] + cdx, line.to[1] + cdy],
    player_id: cdx === 0 && cdy === 0 ? line.player_id : null,
  });
}

export function addZone(
  doc: EditorDoc,
  a: Point,
  b: Point,
  label: string | null = null,
): { doc: EditorDoc; id: string | null } {
  const d = doc.diagram;
  if (d.zones.length >= MAX_ZONES) return { doc, id: null };
  const [x1, y1] = pt(a);
  const [x2, y2] = pt(b);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);
  if (w < 1 || h < 1) return { doc, id: null };
  const id = nextId(
    "z",
    d.zones.map((z) => z.id),
  );
  const zone = { id, x: Math.min(x1, x2), y: Math.min(y1, y2), w: r2(w), h: r2(h), label };
  return { doc: withDiagram(doc, { ...d, zones: [...d.zones, zone] }), id };
}

export function moveZone(doc: EditorDoc, id: string, dx: number, dy: number): EditorDoc {
  const d = doc.diagram;
  return withDiagram(doc, {
    ...d,
    zones: d.zones.map((z) => {
      if (z.id !== id) return z;
      const x = Math.min(Math.max(z.x + dx, 52.5), PITCH_LENGTH - z.w);
      const y = Math.min(Math.max(z.y + dy, 0), PITCH_WIDTH - z.h);
      return { ...z, x: r2(x), y: r2(y) };
    }),
  });
}

export function updateZone(doc: EditorDoc, id: string, label: string | null): EditorDoc {
  const d = doc.diagram;
  return withDiagram(doc, {
    ...d,
    zones: d.zones.map((z) => (z.id === id ? { ...z, label } : z)),
  });
}

export function setBall(doc: EditorDoc, at: Point | null, frame = 0): EditorDoc {
  const d = doc.diagram;
  const ball = at ? pt(at) : null;
  if (frame > 0) {
    return withDiagram(doc, {
      ...d,
      frames: d.frames.map((f, i) => (i === frame - 1 ? { ...f, ball } : f)),
    });
  }
  return withDiagram(doc, { ...d, ball });
}

/** Seçili öğeyi siler. Oyuncu silinince bağlı çizgilerin bağı ve karelerdeki konumu kalkar. */
export function removeSelection(doc: EditorDoc, selection: Selection): EditorDoc {
  const d = doc.diagram;
  switch (selection.kind) {
    case "player":
      return withDiagram(doc, {
        ...d,
        players: d.players.filter((p) => p.id !== selection.id),
        lines: d.lines.map((l) => (l.player_id === selection.id ? { ...l, player_id: null } : l)),
        frames: d.frames.map((f) => {
          const positions = { ...f.positions };
          delete positions[selection.id];
          return { ...f, positions };
        }),
      });
    case "line":
      return withDiagram(doc, { ...d, lines: d.lines.filter((l) => l.id !== selection.id) });
    case "zone":
      return withDiagram(doc, { ...d, zones: d.zones.filter((z) => z.id !== selection.id) });
    case "ball":
      return withDiagram(doc, { ...d, ball: null });
  }
}

/** Sol / sağ varyasyon: çizim aynalanır, taraf değişir. */
export function mirror(doc: EditorDoc): EditorDoc {
  return { ...doc, side: mirrorSide(doc.side), diagram: mirrorDiagram(doc.diagram) };
}

export function addFrame(doc: EditorDoc): { doc: EditorDoc; index: number | null } {
  const d = doc.diagram;
  if (d.frames.length >= MAX_FRAMES) return { doc, index: null };
  const id = nextId(
    "f",
    d.frames.map((f) => f.id),
  );
  const frame: DiagramFrame = { id, positions: {}, ball: null, duration_ms: DEFAULT_FRAME_MS };
  return {
    doc: withDiagram(doc, { ...d, frames: [...d.frames, frame] }),
    index: d.frames.length + 1,
  };
}

export function removeFrame(doc: EditorDoc, index: number): EditorDoc {
  const d = doc.diagram;
  if (index < 1 || index > d.frames.length) return doc;
  return withDiagram(doc, { ...d, frames: d.frames.filter((_, i) => i !== index - 1) });
}

export function setFrameDuration(doc: EditorDoc, index: number, ms: number): EditorDoc {
  const d = doc.diagram;
  const duration = Math.min(10000, Math.max(200, Math.round(ms)));
  return withDiagram(doc, {
    ...d,
    frames: d.frames.map((f, i) => (i === index - 1 ? { ...f, duration_ms: duration } : f)),
  });
}

/** İki belge kaydedilecek içerik bakımından aynı mı (kaydedilmemiş değişiklik denetimi). */
export function sameDoc(a: EditorDoc, b: EditorDoc): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** API'ye gönderilecek gövde (`PUT /routines/{id}`). */
export function toPayload(doc: EditorDoc, baseVersion: number, message: string | null) {
  return {
    base_version: baseVersion,
    name: doc.name.trim(),
    side: doc.side,
    notes: doc.notes,
    when_to_use: doc.whenToUse,
    diagram: doc.diagram,
    message: message?.trim() ? message.trim() : null,
  };
}
