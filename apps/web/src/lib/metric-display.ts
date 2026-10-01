/**
 * Metriklerin gösterim bilgisi: birim, biçim ve profil grubu. Formül yoktur; değerler API'den
 * gelir. Etiketler `messages/*.json` içindeki `metrics.<id>` anahtarlarındadır.
 */

export type MetricUnit =
  "goals" | "xg" | "diff" | "ratio" | "per_match" | "per_set_piece" | "per_100";
export type MetricGroup = "attack" | "defence" | "other";

export interface MetricMeta {
  unit: MetricUnit;
  group: MetricGroup;
}

export const METRIC_META: Record<string, MetricMeta> = {
  set_piece_goals: { unit: "goals", group: "attack" },
  set_piece_xg: { unit: "xg", group: "attack" },
  set_piece_goal_share: { unit: "ratio", group: "attack" },
  set_piece_goals_minus_xg: { unit: "diff", group: "attack" },
  set_piece_goals_per_match: { unit: "per_match", group: "attack" },
  set_pieces_per_match: { unit: "per_match", group: "attack" },
  corners_per_match: { unit: "per_match", group: "attack" },
  goals_per_100_corners: { unit: "per_100", group: "attack" },
  first_contact_win_pct: { unit: "ratio", group: "attack" },
  shots_per_set_piece: { unit: "ratio", group: "attack" },
  xg_per_set_piece: { unit: "per_set_piece", group: "attack" },
  second_phase_xg_share: { unit: "ratio", group: "attack" },
  headed_goals: { unit: "goals", group: "attack" },
  direct_fk_goals: { unit: "goals", group: "attack" },
  set_piece_goals_against: { unit: "goals", group: "defence" },
  first_contact_win_pct_def: { unit: "ratio", group: "defence" },
  aerial_win_pct: { unit: "ratio", group: "defence" },
  aerials_won_per_match: { unit: "per_match", group: "defence" },
  clearances_per_match: { unit: "per_match", group: "defence" },
  fouls_committed_per_match: { unit: "per_match", group: "defence" },
  fouls_won_per_match: { unit: "per_match", group: "other" },
  fast_break_goals: { unit: "goals", group: "other" },
};

/** Profil ve tablolarda gösterim sırası. */
export const METRIC_ORDER = Object.keys(METRIC_META);

const FORMATS: Record<MetricUnit, Intl.NumberFormatOptions> = {
  goals: { maximumFractionDigits: 0 },
  xg: { minimumFractionDigits: 1, maximumFractionDigits: 1 },
  diff: { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" },
  ratio: { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 },
  per_match: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  per_set_piece: { minimumFractionDigits: 3, maximumFractionDigits: 3 },
  per_100: { minimumFractionDigits: 1, maximumFractionDigits: 1 },
};

export type NumberFormatter = (value: number, options: Intl.NumberFormatOptions) => string;

export function metricFormat(id: string): Intl.NumberFormatOptions {
  return FORMATS[METRIC_META[id]?.unit ?? "xg"];
}

export function formatMetric(format: NumberFormatter, id: string, value: number): string {
  const options = metricFormat(id);
  // Sayım metriklerinde içe aktarımdan kesirli değer gelebilir; o zaman bir ondalık gösterilir.
  if (METRIC_META[id]?.unit === "goals" && !Number.isInteger(value)) {
    return format(value, { maximumFractionDigits: 1 });
  }
  return format(value, options);
}

/** Kaynak dizesinden rozet anahtarı: tohum, olay verisi, kulüp kaydı ya da sağlayıcı. */
export function sourceKey(source: string): "seed" | "events" | "import" | "provider" {
  if (source.startsWith("seed")) return "seed";
  if (source === "events") return "events";
  if (source === "import") return "import";
  return "provider";
}
