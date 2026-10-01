/**
 * Hazırlık ekranlarının gösterim yardımcıları: kanıt metriklerinin etiket anahtarı ve biçimi.
 * Değerler API'den gelir; burada hesap yapılmaz.
 */
import { formatMetric, METRIC_META, type NumberFormatter } from "./metric-display";

/** Kural dosyasındaki ad → metrik adı (A-47, `kurgu_analytics.recs.METRIC_ALIASES` ile aynı). */
export const METRIC_ALIASES: Record<string, string> = {
  set_piece_goals_per_100_corners_approx: "goals_per_100_corners",
};

/** Lig metrikleri dışındaki kanıt metrikleri (rutin ve kulübün kendi kaydı, A-46). */
export const LOG_METRICS = [
  "uses",
  "shots",
  "goals",
  "xg",
  "set_pieces",
  "shot_rate",
  "shot_rate_posterior",
  "first_contact_rate",
] as const;

const LOG_RATIOS = new Set(["shot_rate", "shot_rate_posterior", "first_contact_rate"]);

export function canonicalMetric(metric: string): string {
  return METRIC_ALIASES[metric] ?? metric;
}

/** Çeviri anahtarı: lig metrikleri `analysis.metrics.<id>.label`, diğerleri `prep.metric.<id>`. */
export function metricLabelKey(metric: string): string {
  const id = canonicalMetric(metric);
  if (id in METRIC_META) return `analysis.metrics.${id}.label`;
  if ((LOG_METRICS as readonly string[]).includes(id)) return `prep.metric.${id}`;
  return "";
}

export function formatEvidence(format: NumberFormatter, metric: string, value: number): string {
  const id = canonicalMetric(metric);
  if (id in METRIC_META) return formatMetric(format, id, value);
  if (LOG_RATIOS.has(id)) {
    return format(value, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  if (id === "xg") return format(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return format(value, { maximumFractionDigits: 1 });
}

/** Eşik gösterimi: sıra işlemlerinde "≤ 3." biçimi, diğerlerinde işlem ve değer. */
export const OP_SYMBOL: Record<string, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  rank_lte: "≤",
  rank_gte: "≥",
  pctl_gte: "≥",
  pctl_lte: "≤",
  exists: "∃",
};
