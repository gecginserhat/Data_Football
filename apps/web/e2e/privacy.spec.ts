import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 8 KVKK akışları (ADR-0019, A-92): oyuncu kendi rızasını ve haklarını görür; performans ekibi
 * rızayı geri çeker, rızasız iyi oluş kaydının reddedildiğini görür, ıslak imzalı rızayı kaydeder ve
 * silme talebi açar; yönetici talebi reddeder, saklama sürelerini ve envanteri görür.
 * Yazan adımlar yalnız 16 numaralı örnek oyuncuyu kullanır; başka testler ona dokunmaz.
 */

const writer = () =>
  test.skip(
    test.info().project.name !== "desktop",
    "Paylaşılan demo durumunu yalnız bir proje yazar",
  );

const SIXTEEN = "16 · Örnek oyuncu 16";

test("a player sees their consent, the consent text and their data rights", async ({ page }) => {
  await signIn(page, "player");
  await page.goto("/me");
  const panel = page.getByTestId("privacy-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("consent-status")).toHaveAttribute("data-state", "active");
  await panel.getByText(/Rıza metnini oku/).click();
  await expect(panel.getByTestId("consent-text")).toContainText("açık rıza");
  await expect(panel.getByTestId("export-link")).toHaveAttribute(
    "href",
    /\/api\/privacy\/export\/[0-9a-f-]{36}$/,
  );
  const download = page.waitForEvent("download");
  await panel.getByTestId("export-link").click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.json$/);
  await expectNoSeriousA11yViolations(page);
});

async function openSixteen(page: Page) {
  await page.goto("/performance");
  await page.getByRole("link", { name: SIXTEEN }).first().click();
  await expect(page).toHaveURL(/\/performance\/players\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("privacy-panel")).toBeVisible();
}

test("staff withdraw consent, wellness is refused, paper consent is recorded and erasure is requested", async ({
  page,
  browser,
}) => {
  writer();
  await signIn(page, "performance");
  await openSixteen(page);
  const status = page.getByTestId("consent-status");
  if ((await status.getAttribute("data-state")) === "active") {
    await page.getByTestId("consent-withdraw").click();
    await expect(page.getByText("Rıza geri çekildi.")).toBeVisible();
  }
  await expect(status).toHaveAttribute("data-state", "none");

  await page.getByTestId("wellness-save").click();
  await expect(page.getByText("Bu oyuncu için iyi oluş rızası yok.")).toBeVisible();

  await page.getByTestId("consent-reference").fill("E2E-form-16");
  await page.getByTestId("consent-paper").click();
  await expect(page.getByText("Rıza kaydedildi.")).toBeVisible();
  await expect(status).toHaveAttribute("data-state", "active");
  await expect(status).toContainText("E2E-form-16");
  await expectNoSeriousA11yViolations(page);

  if (await page.getByTestId("erasure-form").isVisible()) {
    await page.getByTestId("erasure-form").locator("textarea").fill("E2E talebi");
    await page.getByTestId("erasure-submit").click();
    await expect(page.getByText("Silme talebi yöneticiye iletildi.")).toBeVisible();
  }
  await expect(page.getByTestId("erasure-open")).toBeVisible();

  const context = await browser.newContext();
  const admin = await context.newPage();
  await signIn(admin, "admin");
  await admin.goto("/admin");
  await admin.getByRole("link", { name: /Kişisel veriler/ }).click();
  await expect(admin).toHaveURL(/\/admin\/privacy$/);
  await expect(admin.getByTestId("privacy-inventory")).toContainText("İyi oluş");
  await expect(admin.getByTestId("privacy-inventory")).toContainText("Özel nitelikli");
  const request = admin
    .getByTestId("privacy-request")
    .filter({ hasText: "Örnek oyuncu 16" })
    .and(admin.locator('[data-status="open"]'));
  await expect(request).toHaveCount(1);
  await request.locator('input[name="note"]').fill("E2E: sözleşme süresince saklanır");
  await request.getByTestId("request-reject").click();
  await expect(admin.getByText("Talep reddedildi.")).toBeVisible();

  const retention = admin.getByTestId("retention-form");
  await retention.locator('input[name="wellness_days"]').fill("730");
  await admin.getByTestId("retention-save").click();
  await expect(admin.getByText("Saklama süreleri kaydedildi.")).toBeVisible();
  await expectNoSeriousA11yViolations(admin);
  await context.close();

  await page.reload();
  await expect(page.getByTestId("erasure-form")).toBeVisible();
});
