import { ROUTES, canSee, isActive, routeByKey } from "./routes";

describe("routes", () => {
  it("covers every route in SPEC §13.1", () => {
    expect(ROUTES.map((r) => r.href)).toEqual([
      "/",
      "/prep",
      "/opponents",
      "/league",
      "/routines",
      "/live",
      "/video",
      "/reports",
      "/performance",
      "/me",
      "/admin",
      "/methodology",
    ]);
  });

  it("hides live tagging from a viewer", () => {
    const viewer = new Set(["read_analysis"]);
    expect(canSee(routeByKey("live"), viewer)).toBe(false);
    expect(canSee(routeByKey("overview"), viewer)).toBe(true);
  });

  it("always shows league, profile and methodology", () => {
    const none = new Set<string>();
    expect(ROUTES.filter((r) => canSee(r, none)).map((r) => r.key)).toEqual([
      "league",
      "me",
      "methodology",
    ]);
  });

  it("marks nested paths as active but not the root", () => {
    expect(isActive("/prep", "/prep/abc")).toBe(true);
    expect(isActive("/", "/prep")).toBe(false);
    expect(isActive("/", "/")).toBe(true);
  });
});
