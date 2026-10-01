import { useFormatter, useTranslations } from "next-intl";
import type { PlayerLoad } from "@/lib/performance";

/**
 * Oyuncu yük grafikleri (SPEC §8.2). Grafikler ek görünümdür: aynı sayılar altındaki tablolarda
 * metin olarak da yazar. Renk tek başına anlam taşımaz; seriler çizgi biçimi ve göstergeyle ayrılır.
 */

const W = 640;
const H = 220;
const PAD_L = 44;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;

function niceMax(top: number): { max: number; step: number } {
  if (top <= 0) return { max: 1, step: 1 };
  const raw = top / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  return { max: Math.ceil(top / step) * step, step };
}

function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

function Axis({
  max,
  step,
  sy,
  format,
}: {
  max: number;
  step: number;
  sy: (v: number) => number;
  format: (v: number) => string;
}) {
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  return (
    <g fontSize="11" className="text-ink-3">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={PAD_L} x2={W - PAD_R} y1={sy(v)} y2={sy(v)} stroke="var(--line)" />
          <text x={PAD_L - 6} y={sy(v) + 4} textAnchor="end" fill="currentColor">
            {format(v)}
          </text>
        </g>
      ))}
    </g>
  );
}

function Legend({ items }: { items: { label: string; swatch: React.ReactNode }[] }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <svg width="22" height="10" aria-hidden="true">
            {i.swatch}
          </svg>
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** Günlük sRPE çubukları, akut ve kronik EWMA çizgileri. */
export function LoadChart({ days }: { days: PlayerLoad["days"] }) {
  const t = useTranslations("performance.chart");
  const format = useFormatter();
  if (days.length === 0) return null;
  const top = Math.max(...days.flatMap((d) => [d.load, d.acute, d.chronic]));
  const { max, step } = niceMax(top);
  const band = (W - PAD_L - PAD_R) / days.length;
  const sx = (i: number) => PAD_L + band * i + band / 2;
  const sy = (v: number) => H - PAD_B - (v / max) * (H - PAD_T - PAD_B);
  const line = (key: "acute" | "chronic") =>
    days.map((d, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(d[key]).toFixed(1)}`).join("");
  const labelEvery = Math.max(1, Math.ceil(days.length / 8));
  return (
    <figure className="rounded-lg border border-line bg-surface p-4" data-testid="load-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("loadLabel")} className="w-full">
        <Axis max={max} step={step} sy={sy} format={(v) => format.number(v)} />
        {days.map((d, i) => (
          <rect
            key={d.date}
            x={sx(i) - band * 0.35}
            width={band * 0.7}
            y={sy(d.load)}
            height={Math.max(0, H - PAD_B - sy(d.load))}
            fill="var(--pri)"
            fillOpacity={0.35}
          >
            <title>{`${shortDate(d.date)}: ${format.number(d.load)} AU`}</title>
          </rect>
        ))}
        <path
          d={line("chronic")}
          fill="none"
          stroke="var(--ink-2)"
          strokeWidth={2}
          strokeDasharray="5 4"
        />
        <path d={line("acute")} fill="none" stroke="var(--accent)" strokeWidth={2.25} />
        {days.map((d, i) =>
          i % labelEvery === 0 ? (
            <text
              key={d.date}
              x={sx(i)}
              y={H - 8}
              fontSize="11"
              textAnchor="middle"
              className="fill-ink-3"
            >
              {shortDate(d.date)}
            </text>
          ) : null,
        )}
      </svg>
      <Legend
        items={[
          {
            label: t("daily"),
            swatch: <rect x="2" y="1" width="18" height="8" fill="var(--pri)" fillOpacity={0.35} />,
          },
          {
            label: t("acute"),
            swatch: <line x1="1" x2="21" y1="5" y2="5" stroke="var(--accent)" strokeWidth="2.25" />,
          },
          {
            label: t("chronic"),
            swatch: (
              <line
                x1="1"
                x2="21"
                y1="5"
                y2="5"
                stroke="var(--ink-2)"
                strokeWidth="2"
                strokeDasharray="5 4"
              />
            ),
          },
        ]}
      />
    </figure>
  );
}

/** Hooper indeksi (4-28, yüksek = kötü). */
export function HooperChart({ points }: { points: PlayerLoad["hooper"] }) {
  const t = useTranslations("performance.chart");
  const format = useFormatter();
  if (points.length === 0) return null;
  const min = 4;
  const max = 28;
  const n = points.length;
  const sx = (i: number) => PAD_L + (n === 1 ? 0.5 : i / (n - 1)) * (W - PAD_L - PAD_R);
  const sy = (v: number) => H - PAD_B - ((v - min) / (max - min)) * (H - PAD_T - PAD_B);
  const path = points.map(
    (p, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(p.value).toFixed(1)}`,
  );
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  return (
    <figure className="rounded-lg border border-line bg-surface p-4" data-testid="hooper-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("hooperLabel")} className="w-full">
        <g fontSize="11" className="text-ink-3">
          {[4, 10, 16, 22, 28].map((v) => (
            <g key={v}>
              <line x1={PAD_L} x2={W - PAD_R} y1={sy(v)} y2={sy(v)} stroke="var(--line)" />
              <text x={PAD_L - 6} y={sy(v) + 4} textAnchor="end" fill="currentColor">
                {v}
              </text>
            </g>
          ))}
        </g>
        <path d={path.join("")} fill="none" stroke="var(--pri)" strokeWidth={2} />
        {points.map((p, i) => (
          <circle key={p.date} cx={sx(i)} cy={sy(p.value)} r={3} fill="var(--pri)">
            <title>{`${shortDate(p.date)}: ${p.value}${p.z != null ? ` (z ${format.number(p.z, { maximumFractionDigits: 1 })})` : ""}`}</title>
          </circle>
        ))}
        {points.map((p, i) =>
          i % labelEvery === 0 ? (
            <text
              key={p.date}
              x={sx(i)}
              y={H - 8}
              fontSize="11"
              textAnchor="middle"
              className="fill-ink-3"
            >
              {shortDate(p.date)}
            </text>
          ) : null,
        )}
      </svg>
      <p className="mt-2 text-xs text-ink-3">{t("hooperHelp")}</p>
    </figure>
  );
}

/** Haftalık sıçrama ve kafa vuruşu; uyarı haftaları işaretli. */
export function WeeklyChart({
  weeks,
  alerts,
}: {
  weeks: PlayerLoad["weeks"];
  alerts: PlayerLoad["alerts"];
}) {
  const t = useTranslations("performance.chart");
  const format = useFormatter();
  if (weeks.length === 0) return null;
  const flagged = new Set(alerts.map((a) => `${a.week}:${a.metric}`));
  const { max, step } = niceMax(Math.max(...weeks.flatMap((w) => [w.jumps, w.headers])));
  const band = (W - PAD_L - PAD_R) / weeks.length;
  const bar = band * 0.32;
  const sy = (v: number) => H - PAD_B - (v / max) * (H - PAD_T - PAD_B);
  return (
    <figure className="rounded-lg border border-line bg-surface p-4" data-testid="weekly-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("weeklyLabel")} className="w-full">
        <Axis max={max} step={step} sy={sy} format={(v) => format.number(v)} />
        {weeks.map((w, i) => {
          const x = PAD_L + band * i + band / 2;
          return (
            <g key={w.week}>
              {(["jumps", "headers"] as const).map((metric, j) => {
                const value = w[metric];
                const alert = flagged.has(`${w.week}:${metric}`);
                return (
                  <g key={metric}>
                    <rect
                      x={x - bar + j * bar}
                      width={bar - 2}
                      y={sy(value)}
                      height={Math.max(0, H - PAD_B - sy(value))}
                      fill={metric === "jumps" ? "var(--pri)" : "var(--ink-3)"}
                      stroke={alert ? "var(--neg)" : "none"}
                      strokeWidth={alert ? 2 : 0}
                    >
                      <title>{`${t(metric)} ${shortDate(w.week)}: ${value}`}</title>
                    </rect>
                    {alert ? (
                      <text
                        x={x - bar + j * bar + (bar - 2) / 2}
                        y={sy(value) - 4}
                        fontSize="12"
                        fontWeight="700"
                        textAnchor="middle"
                        fill="var(--neg)"
                      >
                        !
                      </text>
                    ) : null}
                  </g>
                );
              })}
              <text x={x} y={H - 8} fontSize="11" textAnchor="middle" className="fill-ink-3">
                {shortDate(w.week)}
              </text>
            </g>
          );
        })}
      </svg>
      <Legend
        items={[
          {
            label: t("jumps"),
            swatch: <rect x="2" y="1" width="18" height="8" fill="var(--pri)" />,
          },
          {
            label: t("headers"),
            swatch: <rect x="2" y="1" width="18" height="8" fill="var(--ink-3)" />,
          },
          {
            label: t("alertWeek"),
            swatch: (
              <rect
                x="2"
                y="1"
                width="18"
                height="8"
                fill="none"
                stroke="var(--neg)"
                strokeWidth="2"
              />
            ),
          },
        ]}
      />
    </figure>
  );
}
