import zonesJson from "../zones.json";

export type ZoneCode = "NP" | "C6" | "FP" | "PS" | "ED" | "SH" | "OT";

export interface PitchGeometry {
  length: number;
  width: number;
  goal_center: [number, number];
  posts_y: [number, number];
  six_yard_box: { x_min: number; y_min: number; y_max: number };
  penalty_box: { x_min: number; y_min: number; y_max: number };
  penalty_spot: [number, number];
  arc_radius: number;
}

export interface ZoneDefinition {
  code: ZoneCode;
  name_tr: string;
  x_min?: number;
  x_max?: number;
  y_min?: number;
  y_max?: number;
  y_min_inclusive?: boolean;
  y_max_inclusive?: boolean;
  rule?: string;
  corner_distance_max?: number;
}

/** Kanonik saha ölçüleri (SPEC §4): 105 × 68 m, hücum edilen kale x = 105. */
export const PITCH: PitchGeometry = zonesJson.pitch as PitchGeometry;

/** Teslim hedef bölgeleri (SPEC §3.3), dosyadaki öncelik sırasıyla. */
export const ZONES: readonly ZoneDefinition[] = zonesJson.zones as ZoneDefinition[];

export const ZONES_VERSION: number = zonesJson.version;

/**
 * Teslim tarafına göre normalize y (SPEC §3.3): teslim y ≤ 34 tarafından ise `y`,
 * değilse `68 − y`. Python karşılığı: `kurgu_analytics.setpieces.zones.normalize_y`.
 */
export function normalizeY(y: number, deliveryY: number, width: number = PITCH.width): number {
  return deliveryY <= width / 2 ? y : width - y;
}

function inBox(z: ZoneDefinition, x: number, y: number): boolean {
  const xMin = z.x_min ?? -Infinity;
  const xMax = z.x_max ?? Infinity;
  const yMin = z.y_min ?? -Infinity;
  const yMax = z.y_max ?? Infinity;
  if (x < xMin || x >= xMax) return false;
  if (y < yMin || (y === yMin && z.y_min_inclusive === false)) return false;
  return !(y > yMax || (y === yMax && z.y_max_inclusive !== true));
}

function inPenaltyBox(x: number, y: number): boolean {
  const pb = PITCH.penalty_box;
  return x >= pb.x_min && x <= PITCH.length && y >= pb.y_min && y <= pb.y_max;
}

/**
 * Teslimin hedef bölgesi: bitiş noktası (x, y) ve teslimin başladığı y, kanonik metre.
 * Bölgeler sırayla denenir, ilk eşleşen kazanır. Python ile aynı test vektörlerinden geçer
 * (`zones.vectors.json`).
 */
export function classifyZone(x: number, y: number, deliveryY: number): ZoneCode {
  const yn = normalizeY(y, deliveryY);
  for (const z of ZONES) {
    if (z.rule === undefined) {
      if (inBox(z, x, yn)) return z.code;
    } else if (z.rule === "outside_penalty_box_within_corner_distance") {
      const max = z.corner_distance_max ?? 0;
      if (!inPenaltyBox(x, yn) && Math.hypot(PITCH.length - x, yn) <= max) return z.code;
    } else if (z.rule === "fallback") {
      return z.code;
    }
  }
  return "OT";
}
