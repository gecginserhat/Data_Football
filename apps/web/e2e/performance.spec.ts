import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 7 kabul kriterleri (SPEC §19): sRPE, Hooper ve EWMA; sıçrama ve kafa vuruşu uyarıları; rol
 * izinleri; Macar algoritmasıyla gelen markaj önerisinin elle düzeltilip kaydedilmesi.
 * Geliştirme kimlikleri demo kiracısına `is_demo` bir kadro ve son 6 haftanın yükünü ekler;
 * 4 numaralı örnek oyuncunun bu haftaki sıçrama sayısı uyarı eşiğini aşar.
 */

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz7/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

const writer = () =>
  test.skip(
    test.info().project.name !== "desktop",
    "Paylaşılan demo durumunu yalnız bir proje yazar",
  );

const SPIKE = "4 · Örnek oyuncu 4";

test("performance staff see team load, alerts and enter a session and wellness", async ({
  page,
}) => {
  await signIn(page, "performance");
  await page.goto("/performance");
  await expect(page.getByRole("heading", { name: "Performans", level: 1 })).toBeVisible();
  const table = page.getByTestId("load-table");
  await expect(table.getByTestId("load-row")).toHaveCount(16);
  await expect(table.getByTestId("demo-badge").first()).toHaveText("Örnek veri");
  const alert = page.getByTestId("alert").filter({ hasText: SPIKE });
  await expect(alert.first()).toHaveAttribute("data-metric", "jumps");
  await expect(alert.first()).toContainText("eşik");
  await expect(page.getByText("tanı değildir").first()).toBeVisible();
  await expect(page.getByTestId("acwr-note")).toContainText("karar aracı değildir");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "performance");

  await page.getByRole("link", { name: SPIKE }).first().click();
  await expect(page).toHaveURL(/\/performance\/players\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(SPIKE);
  await expect(page.getByTestId("load-chart")).toBeVisible();
  await expect(page.getByTestId("weekly-chart")).toBeVisible();
  await expect(page.getByTestId("hooper-chart")).toBeVisible();
  await expect(page.getByTestId("player-alerts")).toContainText("sıçrama");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "player-load");
});

test("a session and a wellness entry are saved", async ({ page }) => {
  writer();
  await signIn(page, "performance");
  await page.goto("/performance#session");
  const form = page.getByTestId("session-form");
  await form.locator('input[name="title"]').fill("E2E seansı");
  for (const shirt of ["3", "5"]) {
    await form.getByTestId(`session-include-${shirt}`).check();
    await form.getByTestId(`session-rpe-${shirt}`).fill("6.5");
    await form.getByTestId(`session-minutes-${shirt}`).fill("70");
    await form.getByTestId(`session-jumps-${shirt}`).fill("12");
  }
  await page.getByTestId("session-save").click();
  await expect(page.getByText("Seans kaydedildi.")).toBeVisible();
  const latest = page.getByTestId("session").filter({ hasText: "E2E seansı" }).first();
  // sRPE = 6,5 × 70 = 455 AU.
  await expect(latest).toContainText("2 oyuncu · ort. sRPE 455");

  const wellness = page.getByTestId("wellness-form");
  await wellness.getByTestId("wellness-player").selectOption({ label: "5 · Örnek oyuncu 5" });
  await wellness.getByTestId("wellness-sleep").selectOption("2");
  await wellness.getByTestId("wellness-soreness").selectOption("6");
  await page.getByTestId("wellness-save").click();
  await expect(page.getByText("İyi oluş kaydedildi.")).toBeVisible();
  await expect(
    page.getByTestId("load-row").filter({ hasText: "5 · Örnek oyuncu 5" }),
  ).toContainText(
    // Hooper = 2 + 4 + 4 + 6.
    "16",
  );
});

test("an admin sees only the team summary", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/performance");
  await expect(page.getByTestId("load-summary")).toBeVisible();
  await expect(page.getByText("yalnız takım özeti")).toBeVisible();
  await expect(page.getByTestId("load-table")).toHaveCount(0);
  await expect(page.getByTestId("alerts")).toHaveCount(0);
  await expect(page.getByTestId("wellness-form")).toHaveCount(0);
  await shot(page, "performance-admin");
});

test("a set-piece coach cannot open sports science data", async ({ page }) => {
  await signIn(page, "sp-coach");
  await page.goto("/performance");
  await expect(page.getByText("Bu sayfaya erişiminiz yok")).toBeVisible();
  await expect(page.getByTestId("load-summary")).toHaveCount(0);
});

test("a player sees only their own load and enters their wellness", async ({ page }) => {
  await signIn(page, "player");
  await page.goto("/performance");
  await expect(page).toHaveURL(/\/performance\/players\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(SPIKE);
  await expect(page.getByTestId("load-chart")).toBeVisible();
  await expectNoSeriousA11yViolations(page);

  await page.goto("/me");
  await expect(page.getByRole("heading", { name: "Bugünkü iyi oluşum" })).toBeVisible();
  await expect(page.getByTestId("wellness-player")).toHaveCount(0);
  await expectNoSeriousA11yViolations(page);
  await shot(page, "me-player");
  if (test.info().project.name === "desktop") {
    await page.getByTestId("wellness-save").click();
    await expect(page.getByText("İyi oluş kaydedildi.")).toBeVisible();
  }
});

async function openSamsunspor(page: Page) {
  await page.goto("/prep");
  const fixture = page.getByTestId("prep-fixtures").locator('[data-fixture-week="7"]');
  await expect(fixture).toContainText("Samsunspor");
  await fixture.click();
  await expect(page).toHaveURL(/\/prep\/[0-9a-f-]{36}$/);
}

test("the marking suggestion is corrected by hand, saved and shown on the player's card", async ({
  page,
  browser,
}) => {
  writer();
  await signIn(page, "sp-coach");

  // Rol ataması için kütüphaneye bir rutin ekle.
  await page.goto("/routines?tab=templates");
  const template = page.getByTestId("template-list").locator("[data-template]").first();
  const routineName = (await template.locator("h2").textContent())!.trim();
  await template.getByRole("button", { name: "Kütüphaneye ekle" }).click();
  await expect(page).toHaveURL(/\/routines\/[0-9a-f-]{36}\?created=1$/);
  const routineId = new URL(page.url()).pathname.split("/").pop()!;

  await openSamsunspor(page);
  const prepUrl = page.url();
  // Önceki çalıştırmaların hedeflerini temizle.
  const targets = page.getByTestId("target-row");
  for (let n = await targets.count(); n > 0; n -= 1) {
    await targets.first().getByRole("button", { name: /Çıkar/ }).click();
    await expect(targets).toHaveCount(n - 1);
  }
  for (const [name, shirt, height, aerial, goals] of [
    ["Hedef 9", "9", "196", "70", "3"],
    ["Hedef 4", "4", "189", "", ""],
    ["Hedef 15", "15", "182", "", ""],
  ]) {
    const details = page.getByText("Hedef oyuncu ekle");
    if (!(await page.getByTestId("target-form").isVisible())) await details.click();
    const form = page.getByTestId("target-form");
    await form.locator('input[name="name"]').fill(name!);
    await form.locator('input[name="shirt_number"]').fill(shirt!);
    await form.locator('input[name="height_cm"]').fill(height!);
    if (aerial) await form.locator('input[name="aerial_win_pct"]').fill(aerial);
    if (goals) await form.locator('input[name="sp_goals"]').fill(goals);
    await page.getByTestId("target-add").click();
    await expect(page.getByTestId("target-row").filter({ hasText: name! })).toBeVisible();
  }

  const rows = page.getByTestId("marking-row");
  await expect(rows).toHaveCount(3);
  // En yüksek tehdit ilk satırda; önerilen markaj oyuncusu savunmacıdır.
  await expect(rows.first()).toHaveAttribute("data-target", "Hedef 9");
  await expect(rows.first().getByTestId("marking-suggested")).toContainText("Örnek oyuncu");
  const last = rows.last().getByTestId("marking-select");
  await expect(last).not.toHaveValue("");
  await last.selectOption("");
  await page.getByTestId("marking-save").click();
  await expect(page.getByText("Markaj kaydedildi.")).toBeVisible();
  await expect(page.getByTestId("marking-overridden")).toHaveCount(1);
  await expect(page.getByTestId("marking-saved")).toContainText("1 satır elle değiştirildi");

  // Yeniden açınca elle yapılan seçim durur.
  await page.goto(prepUrl);
  await expect(page.getByTestId("marking-row").last().getByTestId("marking-select")).toHaveValue(
    "",
  );
  await page.locator("#marking").scrollIntoViewIfNeeded();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "marking");

  // Alan savunmasına alınan oyuncu öneriden çıkar.
  const topSuggested = (await rows.first().getByTestId("marking-suggested").textContent())!;
  const shirt = topSuggested.split(" · ")[0]!.trim();
  await page.getByTestId(`zonal-${shirt}`).check();
  await page.getByTestId("marking-recompute").click();
  await expect(page).toHaveURL(/zonal=/);
  await expect(
    page.getByTestId("marking-row").first().getByTestId("marking-suggested"),
  ).not.toContainText(`${shirt} · `);

  // Rol ataması: rutini seç, rolü 4 numaraya ver.
  await page.goto(prepUrl);
  await page.getByTestId("assign-pick").selectOption(routineId);
  await page.getByRole("button", { name: "Rolleri göster" }).click();
  const card = page
    .getByTestId("assign-card")
    .filter({ has: page.locator(`input[name="routineId"][value="${routineId}"]`) });
  await expect(card).toBeVisible();
  await card.locator("select").first().selectOption({ label: SPIKE });
  await card.getByTestId("assign-save").click();
  await expect(page.getByText("Atamalar kaydedildi.")).toBeVisible();
  await page.locator("#assignments").scrollIntoViewIfNeeded();
  await shot(page, "assignments");

  // Oyuncu görev kartını görür.
  const context = await browser.newContext({ locale: "tr-TR" });
  const player = await context.newPage();
  await signIn(player, "player");
  await player.goto("/me");
  const cardOnMe = player.getByTestId("task-card").filter({ hasText: "Samsunspor" });
  await expect(
    cardOnMe.locator(`[data-testid="card-routine"][data-routine="${routineId}"]`),
  ).toBeVisible();
  const routineCard = cardOnMe.locator(`[data-testid="card-routine"][data-routine="${routineId}"]`);
  await expect(routineCard).toContainText(routineName);
  await expect(routineCard.getByTestId("board-highlight")).toBeAttached();
  await expectNoSeriousA11yViolations(player);
  await shot(player, "me-cards");
  await context.close();
});

test("a viewer reads the marking but cannot change it", async ({ page }) => {
  await signIn(page, "viewer");
  await openSamsunspor(page);
  await expect(page.locator("#marking")).toBeVisible();
  await expect(page.getByTestId("marking-save")).toHaveCount(0);
  await expect(page.getByTestId("target-form")).toHaveCount(0);
  await expect(page.getByTestId("assign-save")).toHaveCount(0);
});

test("the squad page edits players and shows aerial capacity", async ({ page }) => {
  await signIn(page, "sp-coach");
  await page.goto("/admin");
  await page.getByRole("link", { name: /Kadro/ }).click();
  await expect(page).toHaveURL(/\/admin\/squad$/);
  const row = page.getByTestId("squad-row").filter({ hasText: "Örnek oyuncu 3" });
  await expect(row).toContainText("191 cm");
  await expect(row).toContainText("boy, hava topu, sıçrama");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "squad");
});
