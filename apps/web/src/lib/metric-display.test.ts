import { describe, expect, it } from "vitest";
import { METRIC_META, formatMetric, sourceKey } from "./metric-display";
import tr from "../../messages/tr.json";
import en from "../../messages/en.json";

const nf = (locale: string) => (v: number, o: Intl.NumberFormatOptions) =>
  new Intl.NumberFormat(locale, o).format(v);

describe("metric display", () => {
  it("formats by unit in Turkish", () => {
    const f = nf("tr");
    expect(formatMetric(f, "set_piece_goal_share", 0.2044)).toBe("%20,4");
    expect(formatMetric(f, "set_piece_goals", 15)).toBe("15");
    expect(formatMetric(f, "set_piece_xg", 15.4)).toBe("15,4");
    expect(formatMetric(f, "set_piece_goals_minus_xg", 2.8)).toBe("+2,8");
    expect(formatMetric(f, "corners_per_match", 4.6)).toBe("4,60");
  });

  it("maps sources to badge keys", () => {
    expect(sourceKey("seed:super_lig.json")).toBe("seed");
    expect(sourceKey("import")).toBe("import");
    expect(sourceKey("events")).toBe("events");
    expect(sourceKey("statsbomb_open")).toBe("provider");
  });

  it("has a label for every metric in both languages", () => {
    for (const id of Object.keys(METRIC_META)) {
      expect(tr.analysis.metrics).toHaveProperty(id);
      expect(en.analysis.metrics).toHaveProperty(id);
    }
  });
});
