import { useFormatter, useTranslations } from "next-intl";
import type { TeamMetrics } from "@/lib/analysis";

const W = 560;
const H = 360;
const PAD = 44;

/**
 * Duran top xG – gol dağılımı (SPEC §13.1 /league). Köşegen gol = xG çizgisidir; üstündekiler
 * beklenenden fazla gol atmıştır. Aynı sayılar tabloda da yer aldığından grafik ek bir görünümdür.
 */
export function ScatterPlot({ items, clubId }: { items: TeamMetrics[]; clubId: string | null }) {
  const t = useTranslations("analysis.scatter");
  const format = useFormatter();
  const points = items
    .map((i) => ({
      team: i.team,
      x: i.values.set_piece_xg?.value,
      y: i.values.set_piece_goals?.value,
    }))
    .filter(
      (p): p is { team: TeamMetrics["team"]; x: number; y: number } =>
        p.x !== undefined && p.y !== undefined,
    );
  if (points.length < 2) return null;
  const top = Math.max(...points.flatMap((p) => [p.x, p.y]));
  const step = top <= 10 ? 2 : top <= 25 ? 5 : 10;
  const max = Math.ceil((top + step / 2) / step) * step;
  const sx = (v: number) => PAD + (v / max) * (W - 2 * PAD);
  const sy = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step);
  const labels = placeLabels(points.map((p) => ({ x: sx(p.x), y: sy(p.y), text: p.team.code })));

  return (
    <figure className="rounded-lg border border-line bg-surface p-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby="scatter-title scatter-desc"
        className="h-auto w-full"
      >
        <title id="scatter-title">{t("title")}</title>
        <desc id="scatter-desc">{t("description")}</desc>
        {ticks.map((v) => (
          <g key={v} className="text-ink-3" fontSize="11">
            <line x1={sx(0)} x2={sx(max)} y1={sy(v)} y2={sy(v)} stroke="var(--line)" />
            <text x={PAD - 8} y={sy(v) + 4} textAnchor="end" fill="currentColor">
              {format.number(v)}
            </text>
            <text x={sx(v)} y={H - PAD + 16} textAnchor="middle" fill="currentColor">
              {format.number(v)}
            </text>
          </g>
        ))}
        <line
          x1={sx(0)}
          y1={sy(0)}
          x2={sx(max)}
          y2={sy(max)}
          stroke="var(--ink-3)"
          strokeDasharray="4 4"
        />
        <text x={sx(max) - 4} y={sy(max) + 14} textAnchor="end" fontSize="11" fill="var(--ink-2)">
          {t("diagonal")}
        </text>
        <text x={W / 2} y={H - 6} textAnchor="middle" fontSize="12" fill="var(--ink-2)">
          {t("x")}
        </text>
        <text
          x={12}
          y={H / 2}
          textAnchor="middle"
          fontSize="12"
          fill="var(--ink-2)"
          transform={`rotate(-90 12 ${H / 2})`}
        >
          {t("y")}
        </text>
        {points.map((p, i) => {
          const club = p.team.id === clubId;
          const label = labels[i]!;
          return (
            <g key={p.team.id}>
              <circle
                cx={sx(p.x)}
                cy={sy(p.y)}
                r={club ? 7 : 5}
                fill={club ? "var(--accent)" : "var(--pri)"}
                stroke="var(--surface)"
                strokeWidth="1.5"
              />
              <text
                x={label.x}
                y={label.y}
                textAnchor={label.anchor}
                fontSize="10"
                fontWeight={club ? 700 : 500}
                fill="var(--ink)"
              >
                {p.team.code}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 text-xs text-ink-3">{t("caption")}</figcaption>
    </figure>
  );
}

interface Box {
  x: number;
  y: number;
  text: string;
}

/**
 * Takım kodlarını üst üste binmeyecek şekilde yerleştirir: her nokta için dört konumu sırayla dener
 * (sağ üst, sağ alt, sol üst, sol alt); hepsi doluysa en az çakışanı seçer.
 */
function placeLabels(points: Box[]): { x: number; y: number; anchor: "start" | "end" }[] {
  const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const width = (text: string) => text.length * 6.5;
  return points.map((p) => {
    const w = width(p.text);
    const options = [
      { x: p.x + 8, y: p.y - 6, anchor: "start" as const },
      { x: p.x + 8, y: p.y + 13, anchor: "start" as const },
      { x: p.x - 8, y: p.y - 6, anchor: "end" as const },
      { x: p.x - 8, y: p.y + 13, anchor: "end" as const },
    ];
    const box = (o: (typeof options)[number]) => ({
      x0: o.anchor === "start" ? o.x : o.x - w,
      x1: o.anchor === "start" ? o.x + w : o.x,
      y0: o.y - 10,
      y1: o.y + 2,
    });
    const overlaps = (b: ReturnType<typeof box>) =>
      placed.filter((q) => b.x0 < q.x1 && q.x0 < b.x1 && b.y0 < q.y1 && q.y0 < b.y1).length;
    const best = options.reduce((a, b) => (overlaps(box(b)) < overlaps(box(a)) ? b : a));
    placed.push(box(best));
    return best;
  });
}
