import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/**
 * Faz 8 performans bütçeleri (SPEC §17, A-93): sayfa başına ilk yüklemede ≤ 200 KB sıkıştırılmış
 * JavaScript ve yavaş 4G + 4× yavaş işlemci altında LCP ≤ 2,5 sn. Ölçüm tablet projesinde,
 * Lighthouse'un mobil ayarlarıyla (150 ms gecikme, 1,6 Mbit/sn, 4× CPU) yapılır. Sonuçlar
 * test notlarına yazılır ve `docs/validation/performance.md` içinde özetlenir.
 */

const JS_BUDGET = 200 * 1024;
const LCP_BUDGET = 2_500;

type Route = string | { list: string; pattern: string };

const PLAN: Record<string, Route[]> = {
  "sp-coach": [
    "/",
    "/league",
    { list: "/opponents", pattern: "/opponents/" },
    "/prep",
    { list: "/prep", pattern: "/prep/" },
    "/routines",
    { list: "/routines", pattern: "/routines/" },
    "/live",
    "/video",
    "/reports",
  ],
  performance: ["/performance"],
};

async function resolve(page: Page, route: Route): Promise<string> {
  if (typeof route === "string") return route;
  await page.goto(route.list);
  const href = await page.locator(`main a[href^="${route.pattern}"]`).first().getAttribute("href");
  expect(href, route.pattern).toBeTruthy();
  return href!.split("#")[0]!;
}

async function measure(page: Page, url: string): Promise<{ js: number; lcp: number }> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (1.6 * 1024 * 1024) / 8,
    uploadThroughput: (750 * 1024) / 8,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  try {
    await page.goto(url, { waitUntil: "load" });
    await expect(page.locator("main h1").first()).toBeVisible();
    return await page.evaluate(
      () =>
        new Promise<{ js: number; lcp: number }>((done) => {
          const js = performance
            .getEntriesByType("resource")
            .filter((e) => (e as PerformanceResourceTiming).initiatorType === "script")
            .reduce((sum, e) => sum + (e as PerformanceResourceTiming).encodedBodySize, 0);
          new PerformanceObserver((list) => {
            const entries = list.getEntries();
            done({ js, lcp: entries[entries.length - 1]!.startTime });
          }).observe({ type: "largest-contentful-paint", buffered: true });
        }),
    );
  } finally {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
    });
    await cdp.detach();
  }
}

for (const [user, routes] of Object.entries(PLAN)) {
  test(`${user} pages stay within the JS and LCP budgets`, async ({ page }) => {
    test.skip(test.info().project.name !== "tablet", "Bütçeler mobil ayarlarla ölçülür");
    await signIn(page, user);
    const over: string[] = [];
    for (const route of routes) {
      const url = await resolve(page, route);
      const { js, lcp } = await measure(page, url);
      const label = typeof route === "string" ? route : `${route.pattern}[id]`;
      test.info().annotations.push({
        type: "budget",
        description: `${label} js=${(js / 1024).toFixed(1)}KB lcp=${Math.round(lcp)}ms`,
      });
      if (js > JS_BUDGET) over.push(`${label}: JS ${(js / 1024).toFixed(1)} KB`);
      if (lcp > LCP_BUDGET) over.push(`${label}: LCP ${Math.round(lcp)} ms`);
    }
    expect(over).toEqual([]);
  });
}
