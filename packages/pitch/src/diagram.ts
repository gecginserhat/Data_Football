import rolesJson from "../roles.json";

/**
 * Rutin diyagramı v1 (ADR-0008, A-39). Koordinatlar kanonik metre (SPEC §4): hücum edilen kale
 * x = 105, y = 0 hücum eden takımın sağ taç çizgisi. Python karşılığı:
 * `kurgu_analytics.reports.diagram`; ikisi `diagram.vectors.json` ile aynı sonuçları verir.
 */

export type Point = [number, number];
export type DiagramTeam = "own" | "opponent";
export type LineKind = "run" | "ball_path" | "screen";

export interface DiagramPlayer {
  id: string;
  team: DiagramTeam;
  role: string;
  number?: number | null;
  label?: string | null;
  x: number;
  y: number;
}

export interface DiagramLine {
  id: string;
  kind: LineKind;
  from: Point;
  to: Point;
  curve: number;
  player_id?: string | null;
}

export interface DiagramZone {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  label?: string | null;
}

export interface DiagramFrame {
  id: string;
  positions: Record<string, Point>;
  ball?: Point | null;
  duration_ms: number;
}

export interface Diagram {
  schema: 1;
  players: DiagramPlayer[];
  lines: DiagramLine[];
  zones: DiagramZone[];
  ball?: Point | null;
  frames: DiagramFrame[];
}

export const PITCH_LENGTH = 105;
export const PITCH_WIDTH = 68;
/** Editörün gösterdiği yarım saha (A-45). */
export const HALF_PITCH_X_MIN = 52.5;
export const DEFAULT_FRAME_MS = 1000;

export function emptyDiagram(): Diagram {
  return { schema: 1, players: [], lines: [], zones: [], ball: null, frames: [] };
}

const round = (v: number, digits = 2): number => {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
};

/**
 * İkinci dereceden Bézier kontrol noktası: orta nokta + curve × (−dy, dx). Pozitif kavis gidiş
 * yönünün soluna (+90°) bükülür; büyüklük çizgi uzunluğuyla orantılıdır (şablon dosyası notu).
 */
export function controlPoint(from: Point, to: Point, curve: number): Point {
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  return [(from[0] + to[0]) / 2 - curve * dy, (from[1] + to[1]) / 2 + curve * dx];
}

/** Bézier eğrisi üzerinde t ∈ [0, 1] noktası. */
export function pointOnCurve(from: Point, to: Point, curve: number, t: number): Point {
  const c = controlPoint(from, to, curve);
  const u = 1 - t;
  return [
    u * u * from[0] + 2 * u * t * c[0] + t * t * to[0],
    u * u * from[1] + 2 * u * t * c[1] + t * t * to[1],
  ];
}

/** Bitişteki teğet yönü (ok başı ve perdeleme çizgisi için), birim vektör. */
export function endTangent(from: Point, to: Point, curve: number): Point {
  const c = controlPoint(from, to, curve);
  let dx = to[0] - c[0];
  let dy = to[1] - c[1];
  if (Math.hypot(dx, dy) < 1e-9) {
    dx = to[0] - from[0];
    dy = to[1] - from[1];
  }
  const len = Math.hypot(dx, dy) || 1;
  return [dx / len, dy / len];
}

export function mirrorPoint(p: Point): Point {
  return [p[0], round(PITCH_WIDTH - p[1], 4)];
}

/**
 * Sol / sağ varyasyon: y → 68 − y. Ayna yönü tersine çevirdiği için kavisin işareti de döner;
 * böylece çizgi aynı tarafa değil, aynadaki tarafa bükülür.
 */
export function mirrorDiagram(d: Diagram): Diagram {
  return {
    ...d,
    players: d.players.map((p) => ({ ...p, y: round(PITCH_WIDTH - p.y, 4) })),
    lines: d.lines.map((l) => ({
      ...l,
      from: mirrorPoint(l.from),
      to: mirrorPoint(l.to),
      curve: l.curve === 0 ? 0 : -l.curve,
    })),
    zones: d.zones.map((z) => ({ ...z, y: round(PITCH_WIDTH - z.y - z.h, 4) })),
    ball: d.ball ? mirrorPoint(d.ball) : d.ball,
    frames: d.frames.map((f) => ({
      ...f,
      positions: Object.fromEntries(
        Object.entries(f.positions).map(([id, p]) => [id, mirrorPoint(p)]),
      ),
      ball: f.ball ? mirrorPoint(f.ball) : f.ball,
    })),
  };
}

export function mirrorSide(side: "left" | "right" | null): "left" | "right" | null {
  if (side === null) return null;
  return side === "left" ? "right" : "left";
}

/** Izgaraya hizalama; `step` metre. */
export function snap(v: number, step: number): number {
  return step > 0 ? round(Math.round(v / step) * step, 4) : v;
}

export function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Noktayı editörün yarım sahasına sığdırır (A-45). */
export function clampToBoard(p: Point): Point {
  return [clamp(p[0], HALF_PITCH_X_MIN, PITCH_LENGTH), clamp(p[1], 0, PITCH_WIDTH)];
}

export interface Snapshot {
  positions: Record<string, Point>;
  ball: Point | null;
}

/**
 * Anahtar karedeki konumlar: 0 başlangıç dizilişi; k. kare, önceki karelerin üstüne yalnızca
 * kendi değiştirdiği oyuncuları ve topu yazar.
 */
export function keyframe(d: Diagram, index: number): Snapshot {
  const positions: Record<string, Point> = {};
  for (const p of d.players) positions[p.id] = [p.x, p.y];
  let ball: Point | null = d.ball ?? null;
  const last = Math.min(index, d.frames.length);
  for (let i = 0; i < last; i++) {
    const f = d.frames[i]!;
    for (const [id, pos] of Object.entries(f.positions)) {
      if (id in positions) positions[id] = pos;
    }
    if (f.ball) ball = f.ball;
  }
  return { positions, ball };
}

/**
 * Animasyon anı: `t` ∈ [0, kare sayısı]; tam sayılar anahtar kareler, arası doğrusal
 * enterpolasyon.
 */
export function interpolate(d: Diagram, t: number): Snapshot {
  const max = d.frames.length;
  const tt = clamp(t, 0, max);
  const i = Math.floor(tt);
  const frac = tt - i;
  const a = keyframe(d, i);
  if (frac === 0 || i >= max) return a;
  const b = keyframe(d, i + 1);
  const lerp = (p: Point, q: Point): Point => [
    p[0] + (q[0] - p[0]) * frac,
    p[1] + (q[1] - p[1]) * frac,
  ];
  const positions: Record<string, Point> = {};
  for (const [id, p] of Object.entries(a.positions)) positions[id] = lerp(p, b.positions[id] ?? p);
  const ball = a.ball && b.ball ? lerp(a.ball, b.ball) : (b.ball ?? a.ball);
  return { positions, ball };
}

export interface DiagramDiff {
  playersAdded: string[];
  playersRemoved: string[];
  playersMoved: string[];
  playersChanged: string[];
  linesAdded: string[];
  linesRemoved: string[];
  linesChanged: string[];
  zonesAdded: string[];
  zonesRemoved: string[];
  zonesChanged: string[];
  framesBefore: number;
  framesAfter: number;
}

const samePoint = (a: Point, b: Point, tol = 0.05): boolean =>
  Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;

/** İki sürüm arasındaki fark, öğe kimliklerine göre (konum toleransı 5 cm). */
export function diffDiagrams(a: Diagram, b: Diagram): DiagramDiff {
  const byId = <T extends { id: string }>(xs: T[]) => new Map(xs.map((x) => [x.id, x]));
  const pa = byId(a.players);
  const pb = byId(b.players);
  const la = byId(a.lines);
  const lb = byId(b.lines);
  const za = byId(a.zones);
  const zb = byId(b.zones);
  const added = <T>(x: Map<string, T>, y: Map<string, T>) => [...y.keys()].filter((k) => !x.has(k));
  const removed = <T>(x: Map<string, T>, y: Map<string, T>) =>
    [...x.keys()].filter((k) => !y.has(k));
  const both = <T>(x: Map<string, T>, y: Map<string, T>) => [...y.keys()].filter((k) => x.has(k));

  const playersMoved: string[] = [];
  const playersChanged: string[] = [];
  for (const id of both(pa, pb)) {
    const p = pa.get(id)!;
    const q = pb.get(id)!;
    if (!samePoint([p.x, p.y], [q.x, q.y])) playersMoved.push(id);
    if (
      p.team !== q.team ||
      p.role !== q.role ||
      (p.number ?? null) !== (q.number ?? null) ||
      (p.label ?? null) !== (q.label ?? null)
    ) {
      playersChanged.push(id);
    }
  }
  const linesChanged = both(la, lb).filter((id) => {
    const p = la.get(id)!;
    const q = lb.get(id)!;
    return (
      p.kind !== q.kind ||
      !samePoint(p.from, q.from) ||
      !samePoint(p.to, q.to) ||
      Math.abs(p.curve - q.curve) > 1e-6 ||
      (p.player_id ?? null) !== (q.player_id ?? null)
    );
  });
  const zonesChanged = both(za, zb).filter((id) => {
    const p = za.get(id)!;
    const q = zb.get(id)!;
    return (
      !samePoint([p.x, p.y], [q.x, q.y]) ||
      !samePoint([p.w, p.h], [q.w, q.h]) ||
      (p.label ?? null) !== (q.label ?? null)
    );
  });
  return {
    playersAdded: added(pa, pb),
    playersRemoved: removed(pa, pb),
    playersMoved,
    playersChanged,
    linesAdded: added(la, lb),
    linesRemoved: removed(la, lb),
    linesChanged,
    zonesAdded: added(za, zb),
    zonesRemoved: removed(za, zb),
    zonesChanged,
    framesBefore: a.frames.length,
    framesAfter: b.frames.length,
  };
}

/** Kullanılmayan ilk kimlik: `prefix` + sayı (p1, p2, …). */
export function nextId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  let i = 1;
  while (used.has(`${prefix}${i}`)) i++;
  return `${prefix}${i}`;
}

export interface RoleDefinition {
  id: string;
  phase: "attack" | "defence";
  tr: string;
  en: string;
}

export const ROLES: { own: readonly RoleDefinition[]; opponent: readonly RoleDefinition[] } = {
  own: rolesJson.own as RoleDefinition[],
  opponent: rolesJson.opponent as RoleDefinition[],
};

/** Rolün görünen adı; sözlükte yoksa kimliğin kendisi. */
export function roleLabel(team: DiagramTeam, role: string, locale: string): string {
  const def = ROLES[team].find((r) => r.id === role);
  if (!def) return role;
  return locale.startsWith("en") ? def.en : def.tr;
}
