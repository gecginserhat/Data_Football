import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/**
 * Faz 8 kabul kriteri (SPEC §19): tüm sayfalarda axe taramasında ciddi ihlal yok. Her rol kendi
 * gördüğü sayfaları açık ve koyu temada tarar (A-94). Dinamik sayfaların ilk kaydı liste
 * sayfasındaki ilk bağlantıdan bulunur; `optional` olanlar kayıt yoksa atlanır. İhlaller sayfa sayfa toplanır, tek seferde raporlanır.
 */

type Route = string | { list: string; pattern: string; optional?: true };

const PLAN: Record<string, Route[]> = {
  "sp-coach": [
    "/",
    "/league",
    "/opponents",
    { list: "/opponents", pattern: "/opponents/" },
    "/prep",
    { list: "/prep", pattern: "/prep/" },
    "/routines",
    { list: "/routines", pattern: "/routines/" },
    "/live",
    { list: "/live", pattern: "/live/" },
    "/video",
    // Video kaydını pwa projesindeki video testi oluşturur; ayrıntı sayfasını o test de tarar.
    { list: "/video", pattern: "/video/", optional: true },
    "/reports",
    "/methodology",
    "/me",
  ],
  admin: [
    "/admin",
    "/admin/imports",
    { list: "/admin/imports", pattern: "/admin/imports/" },
    "/admin/rules",
    "/admin/llm",
    "/admin/squad",
    "/admin/privacy",
    "/admin/users",
    "/admin/audit",
  ],
  performance: ["/performance", { list: "/performance", pattern: "/performance/players/" }],
  player: ["/me"],
};

async function resolve(page: Page, route: Route): Promise<string | null> {
  if (typeof route === "string") return route;
  await page.goto(route.list);
  const href = await page
    .locator(`main a[href^="${route.pattern}"]`)
    .first()
    .getAttribute("href", { timeout: 5_000 })
    .catch(() => null);
  return href ? href.split("#")[0]! : null;
}

async function scan(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

for (const scheme of ["light", "dark"] as const) {
  test(`signin page has no serious violations (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/signin");
    expect(await scan(page)).toEqual([]);
  });

  for (const [user, routes] of Object.entries(PLAN)) {
    test(`${user} pages have no serious violations (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await signIn(page, user);
      const found: Record<string, string[]> = {};
      const missing: string[] = [];
      for (const route of routes) {
        const url = await resolve(page, route);
        if (!url) {
          if (typeof route !== "string" && route.optional) continue;
          missing.push(typeof route === "string" ? route : route.pattern);
          continue;
        }
        await page.goto(url);
        await expect(page.locator("main h1").first()).toBeVisible();
        await page.waitForLoadState("networkidle").catch(() => undefined);
        const violations = await scan(page);
        if (violations.length) found[url] = violations;
      }
      expect.soft(found).toEqual({});
      expect(missing, "dinamik sayfa için kayıt bulunamadı").toEqual([]);
    });
  }
}
