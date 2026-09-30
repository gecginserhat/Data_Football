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

/** Teslim hedef bölgeleri (SPEC §3.3). Sınıflandırma mantığı Faz 1'de eklenir. */
export const ZONES: readonly ZoneDefinition[] = zonesJson.zones as ZoneDefinition[];

export const ZONES_VERSION: number = zonesJson.version;
