/** Açık tema renk tokenları (SPEC §13.3). CSS değişkenleriyle aynı değerlerdir. */
export const colors = {
  bg: "#F2F4F1",
  surface: "#FFFFFF",
  ink: "#0F1B16",
  ink2: "#44524B",
  ink3: "#63706A",
  line: "#E0E5E0",
  brand: "#0E3B2E",
  pri: "#0E3B2E",
  accent: "#E3A008",
  pos: "#1B7348",
  neg: "#B94C16",
  def: "#2F6FB3",
  turf: "#17513A",
} as const;

export type ColorToken = keyof typeof colors;
