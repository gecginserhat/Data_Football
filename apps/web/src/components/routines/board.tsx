/**
 * Rutin tahtasının SVG parçaları (SPEC §13.2). Çizim düzlemi metre cinsindendir: hücum edilen
 * kale üstte, yatay eksen 68 − y (y = 0 hücum eden takımın sağ taç çizgisi sağda), dikey eksen
 * 105 − x. Hook kullanılmaz; sunucu ve istemci bileşenlerinde aynı çizim kullanılır.
 */
import {
  type Diagram,
  type DiagramLine,
  type DiagramPlayer,
  type DiagramZone,
  type Point,
  controlPoint,
  endTangent,
  HALF_PITCH_X_MIN,
  keyframe,
  PITCH_LENGTH,
  PITCH_WIDTH,
  type Snapshot,
} from "@kurgu/pitch";

export const BOARD_MARGIN = 2.5;
export const PLAYER_RADIUS = 1.25;

export function toSvg(p: Point): [number, number] {
  return [PITCH_WIDTH - p[1], PITCH_LENGTH - p[0]];
}

export function fromSvg(sx: number, sy: number): Point {
  return [PITCH_LENGTH - sy, PITCH_WIDTH - sx];
}

/** `x_min`'den kaleye kadar görünen alanın viewBox'ı. */
export function viewBox(xMin: number = HALF_PITCH_X_MIN): string {
  const m = BOARD_MARGIN;
  return `${-m} ${-m} ${PITCH_WIDTH + 2 * m} ${PITCH_LENGTH - xMin + 2 * m}`;
}

const STROKE = 0.22;

export function PitchMarkings({ xMin = HALF_PITCH_X_MIN }: { xMin?: number }) {
  const bottom = PITCH_LENGTH - xMin;
  const half = PITCH_LENGTH - HALF_PITCH_X_MIN;
  const arcHalf = Math.sqrt(9.15 ** 2 - 5.5 ** 2);
  const common = { fill: "none", stroke: "var(--board-line)", strokeWidth: STROKE };
  return (
    <g aria-hidden="true">
      <rect
        x={-BOARD_MARGIN}
        y={-BOARD_MARGIN}
        width={PITCH_WIDTH + 2 * BOARD_MARGIN}
        height={bottom + 2 * BOARD_MARGIN}
        fill="var(--board-turf)"
      />
      <path
        d={`M0 ${bottom + BOARD_MARGIN} V0 H${PITCH_WIDTH} V${bottom + BOARD_MARGIN}`}
        {...common}
      />
      {xMin <= HALF_PITCH_X_MIN ? (
        <>
          <line x1={0} y1={half} x2={PITCH_WIDTH} y2={half} {...common} />
          <path d={`M${34 - 9.15} ${half} A9.15 9.15 0 0 1 ${34 + 9.15} ${half}`} {...common} />
        </>
      ) : null}
      <rect x={13.84} y={0} width={40.32} height={16.5} {...common} />
      <rect x={24.84} y={0} width={18.32} height={5.5} {...common} />
      <rect x={30.34} y={-1.2} width={7.32} height={1.2} {...common} />
      <circle cx={34} cy={11} r={0.3} fill="var(--board-line)" />
      <path d={`M${34 - arcHalf} 16.5 A9.15 9.15 0 0 0 ${34 + arcHalf} 16.5`} {...common} />
      <path d="M0 1 A1 1 0 0 0 1 0" {...common} />
      <path d={`M${PITCH_WIDTH - 1} 0 A1 1 0 0 0 ${PITCH_WIDTH} 1`} {...common} />
    </g>
  );
}

function arrowHead(tip: [number, number], dir: [number, number], size = 1.1): string {
  const [ux, uy] = dir;
  const bx = tip[0] - ux * size;
  const by = tip[1] - uy * size;
  const w = size * 0.45;
  return `${tip[0]},${tip[1]} ${bx - uy * w},${by + ux * w} ${bx + uy * w},${by - ux * w}`;
}

export const LINE_STYLE = {
  run: { stroke: "var(--board-own)", width: 0.32, dash: undefined },
  ball_path: { stroke: "var(--board-ball)", width: 0.28, dash: "1.1 0.7" },
  screen: { stroke: "var(--ink-2)", width: 0.36, dash: undefined },
} as const;

/** Çizginin SVG yolu ve uç geometrisi. */
export function lineGeometry(line: DiagramLine) {
  const from = toSvg(line.from);
  const to = toSvg(line.to);
  const c = toSvg(controlPoint(line.from, line.to, line.curve));
  const [tx, ty] = endTangent(line.from, line.to, line.curve);
  // Kanonikten SVG'ye yön dönüşümü: (dx, dy) → (−dy, −dx).
  const dir: [number, number] = [-ty, -tx];
  return {
    from,
    to,
    control: c,
    dir,
    d: `M${from[0]} ${from[1]} Q${c[0]} ${c[1]} ${to[0]} ${to[1]}`,
  };
}

export function LineShape({ line, dimmed = false }: { line: DiagramLine; dimmed?: boolean }) {
  const style = LINE_STYLE[line.kind];
  const g = lineGeometry(line);
  const [ux, uy] = g.dir;
  return (
    <g opacity={dimmed ? 0.35 : 1}>
      <path
        d={g.d}
        fill="none"
        stroke={style.stroke}
        strokeWidth={style.width}
        strokeDasharray={style.dash}
        strokeLinecap="round"
      />
      {line.kind === "screen" ? (
        <line
          x1={g.to[0] - uy * 1.3}
          y1={g.to[1] + ux * 1.3}
          x2={g.to[0] + uy * 1.3}
          y2={g.to[1] - ux * 1.3}
          stroke={style.stroke}
          strokeWidth={0.5}
        />
      ) : (
        <polygon points={arrowHead(g.to, g.dir)} fill={style.stroke} />
      )}
    </g>
  );
}

export function ZoneShape({ zone }: { zone: DiagramZone }) {
  const [sx, sy] = toSvg([zone.x + zone.w, zone.y + zone.h]);
  return (
    <g>
      <rect
        x={sx}
        y={sy}
        width={zone.h}
        height={zone.w}
        fill="var(--accent)"
        fillOpacity={0.22}
        stroke="var(--accent)"
        strokeWidth={0.18}
      />
      {zone.label ? (
        <text
          x={sx + zone.h / 2}
          y={sy + zone.w / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={1.4}
          fill="var(--ink-2)"
        >
          {zone.label}
        </text>
      ) : null}
    </g>
  );
}

export function PlayerShape({
  player,
  at,
  gkLabel = "K",
}: {
  player: DiagramPlayer;
  at: Point;
  gkLabel?: string;
}) {
  const [cx, cy] = toSvg(at);
  const own = player.team === "own";
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={PLAYER_RADIUS}
        fill={own ? "var(--board-own)" : "var(--surface)"}
        stroke={own ? "var(--surface)" : "var(--board-opp)"}
        strokeWidth={own ? 0.18 : 0.3}
      />
      {own && player.number != null ? (
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={1.35}
          fontWeight={700}
          fill="var(--board-own-ink)"
        >
          {player.number}
        </text>
      ) : null}
      {!own && player.role === "gk" ? (
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={1.1}
          fontWeight={700}
          fill="var(--board-opp)"
        >
          {gkLabel}
        </text>
      ) : null}
      {player.label ? (
        <text
          x={cx}
          y={cy + PLAYER_RADIUS + 1.2}
          textAnchor="middle"
          fontSize={1.1}
          fill="var(--ink)"
        >
          {player.label}
        </text>
      ) : null}
    </g>
  );
}

export function BallShape({ at }: { at: Point }) {
  const [cx, cy] = toSvg(at);
  return (
    <circle
      cx={cx}
      cy={cy}
      r={0.65}
      fill="var(--surface)"
      stroke="var(--board-ball)"
      strokeWidth={0.22}
    />
  );
}

/** Salt okunur tahta: kütüphane önizlemesi, sürüm karşılaştırma. */
export function BoardView({
  diagram,
  xMin = HALF_PITCH_X_MIN,
  snapshot,
  label,
  gkLabel,
  className,
}: {
  diagram: Diagram;
  xMin?: number;
  snapshot?: Snapshot;
  label: string;
  gkLabel?: string;
  className?: string;
}) {
  const state = snapshot ?? keyframe(diagram, 0);
  return (
    <svg viewBox={viewBox(xMin)} role="img" aria-label={label} className={className}>
      <PitchMarkings xMin={xMin} />
      {diagram.zones.map((z) => (
        <ZoneShape key={z.id} zone={z} />
      ))}
      {diagram.lines.map((l) => (
        <LineShape key={l.id} line={l} />
      ))}
      {diagram.players.map((p) => (
        <PlayerShape
          key={p.id}
          player={p}
          at={state.positions[p.id] ?? [p.x, p.y]}
          gkLabel={gkLabel}
        />
      ))}
      {state.ball ? <BallShape at={state.ball} /> : null}
    </svg>
  );
}
