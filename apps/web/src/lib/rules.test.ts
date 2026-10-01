import { describe, expect, it } from "vitest";
import { applyEdits, conditionsOf, editsFromForm, type RuleJson } from "./rules";

const rule: RuleJson = {
  id: "DEF_X",
  area: "defense",
  priority: 2,
  enabled: true,
  title: "x",
  when: {
    all: [
      { subject: "opponent", metric: "corners_per_match", op: "rank_lte", value: 3 },
      {
        any: [
          { subject: "club", metric: "aerial_win_pct", op: "rank_gte", value: 12 },
          { not: { subject: "league", metric: "x", op: "eq", value: true } },
        ],
      },
    ],
  },
};

describe("conditionsOf", () => {
  it("walks all/any/not depth first", () => {
    expect(conditionsOf(rule.when).map((c) => c.metric)).toEqual([
      "corners_per_match",
      "aerial_win_pct",
      "x",
    ]);
  });
});

describe("applyEdits", () => {
  it("changes values, priority and enabled without mutating input", () => {
    const edited = applyEdits([rule], {
      enabled: { DEF_X: false },
      priority: { DEF_X: 1 },
      values: { DEF_X: [4, null, 5] },
    })[0]!;
    expect(edited.enabled).toBe(false);
    expect(edited.priority).toBe(1);
    expect(conditionsOf(edited.when).map((c) => c.value)).toEqual([4, 12, true]);
    expect(conditionsOf(rule.when)[0]?.value).toBe(3);
  });
});

describe("editsFromForm", () => {
  it("reads only rules present in the form", () => {
    const form = new FormData();
    form.set("present:DEF_X", "1");
    form.set("priority:DEF_X", "3");
    form.set("value:DEF_X:0", "2,5");
    form.set("value:DEF_X:1", "");
    const edits = editsFromForm(form, [rule, { ...rule, id: "OTHER" }]);
    expect(edits.enabled).toEqual({ DEF_X: false });
    expect(edits.priority).toEqual({ DEF_X: 3 });
    expect(edits.values.DEF_X).toEqual([2.5, null, null]);
    expect(edits.values.OTHER).toBeUndefined();
  });
});
