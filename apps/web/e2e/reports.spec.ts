import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 6 kabul kriterleri: rakip raporu ve maç planı PDF'i 15 sn içinde üretilir (A-71); LLM
 * brifingi sayı eşleştirme denetiminden geçer ve yalnız o zaman gösterilir (ADR-0013). E2E
 * ortamında model sahtedir (`KURGU_LLM_BACKEND=fake`); denetim gerçektir.
 */
const LIMIT_MS = 15_000;

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz6/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

const writer = () =>
  test.skip(
    test.info().project.name !== "desktop",
    "Paylaşılan demo durumunu yalnız bir proje yazar",
  );

async function openSamsunspor(page: Page) {
  await page.goto("/prep");
  const fixture = page.getByTestId("prep-fixtures").locator('[data-fixture-week="7"]');
  await expect(fixture).toContainText("Samsunspor");
  await fixture.click();
  await expect(page).toHaveURL(/\/prep\/[0-9a-f-]{36}$/);
}

/** Raporu ister, hazır olana kadar geçen süreyi ölçer ve PDF'i indirir. */
async function requestPdf(page: Page, type: "opponent" | "match_plan") {
  const previous = new URL(page.url()).searchParams.get("report");
  const started = Date.now();
  await page.getByTestId(`request-${type}`).click();
  await page.waitForURL((url) => {
    const report = url.searchParams.get("report");
    return report !== null && report !== previous;
  });
  const id = new URL(page.url()).searchParams.get("report");
  const row = page.locator(`#report-${id}`);
  await expect(row).toHaveAttribute("data-type", type);
  await expect(row).toHaveAttribute("data-status", "ready", { timeout: LIMIT_MS });
  expect(Date.now() - started).toBeLessThan(LIMIT_MS);
  await expect(row).toContainText("Hazır");
  await expect(row).toContainText(/\d+ sayfa/);
  const href = await row.getByTestId("report-download").getAttribute("href");
  const response = await page.request.get(href!);
  expect(response.ok()).toBe(true);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  expect((await response.body()).subarray(0, 4).toString()).toBe("%PDF");
  return row;
}

test("opponent report and match plan PDFs are ready within 15 seconds", async ({ page }) => {
  await signIn(page, "sp-coach");
  await openSamsunspor(page);
  const opponent = await requestPdf(page, "opponent");
  await expect(opponent).toContainText("Rakip raporu");
  await expect(opponent).toContainText("SAM–TS");
  const plan = await requestPdf(page, "match_plan");
  await expect(plan).toContainText("Maç planı");
  await page.locator("#reports").scrollIntoViewIfNeeded();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "prep-reports");

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Raporlar", level: 1 })).toBeVisible();
  await expect(page.getByTestId("report-fixture")).toBeVisible();
  await expect(page.getByTestId("report").first()).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "reports");
});

test("briefing is shown only after its numbers match the records", async ({ page }) => {
  writer();
  await signIn(page, "sp-coach");
  await openSamsunspor(page);
  await page.getByTestId("generate-briefing").click();
  await expect(page).toHaveURL(/#briefing$/);
  await expect(page.getByTestId("briefing-error")).toHaveCount(0);
  const briefing = page.getByTestId("briefing");
  await expect(briefing).toContainText("Samsunspor maçı");
  await expect(page.getByTestId("briefing-label")).toContainText("sayılar kayıtla eşleşti");
  await page.locator("#briefing").scrollIntoViewIfNeeded();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "briefing");
});

test("a viewer reads the briefing but cannot generate one", async ({ page }) => {
  await signIn(page, "viewer");
  await openSamsunspor(page);
  await expect(page.locator("#briefing")).toBeVisible();
  await expect(page.getByTestId("generate-briefing")).toHaveCount(0);
});

test("an admin can turn the briefing off and on", async ({ page, browser }) => {
  writer();
  await signIn(page, "admin");
  await page.goto("/admin");
  await page.getByRole("link", { name: /Yapay zekâ brifingi/ }).click();
  await expect(page).toHaveURL(/\/admin\/llm$/);
  await expect(page.getByTestId("llm-usage")).toContainText("/ 200");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "admin-llm");

  const enabled = page.getByTestId("llm-enabled");
  try {
    await enabled.uncheck();
    await page.getByTestId("llm-save").click();
    await expect(page.getByText("Ayarlar kaydedildi.")).toBeVisible();
    await expect(page.getByTestId("llm-enabled")).not.toBeChecked();

    const coach = await browser.newPage();
    await signIn(coach, "sp-coach");
    await openSamsunspor(coach);
    await coach.getByTestId("generate-briefing").click();
    await expect(coach.getByTestId("briefing-error")).toContainText("kulüp ayarlarında kapalı");
    await coach.close();
  } finally {
    await page.goto("/admin/llm");
    await page.getByTestId("llm-enabled").check();
    await page.getByTestId("llm-save").click();
    await expect(page.getByTestId("llm-enabled")).toBeChecked();
  }
});
